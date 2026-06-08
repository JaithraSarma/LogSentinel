"""
Remediation engine — dispatches remediation actions on anomaly detection.

Supports two modes:
- 'lambda': Invokes an AWS Lambda function with anomaly payload
- 'mock': Logs remediation intent without calling external services (for local dev)

Falls back to webhook POST if Lambda invocation fails and a webhook URL is configured.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.core.detector import AnomalyResult
from app.metrics import REMEDIATION_TRIGGERED_TOTAL

logger = logging.getLogger(__name__)


class RemediationEngine:
    """Handles automated remediation actions triggered by anomaly detection."""

    def __init__(self) -> None:
        self._http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Lazy-initialize the HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    def _build_payload(self, anomaly: AnomalyResult) -> dict[str, Any]:
        """Construct the remediation payload from an anomaly result."""
        return {
            "anomaly_type": anomaly.anomaly_type,
            "service_name": anomaly.service_name,
            "severity": anomaly.severity,
            "metric_value": anomaly.metric_value,
            "threshold_value": anomaly.threshold_value,
            "window_size": anomaly.window_size,
            "window_start": (anomaly.window_start.isoformat() if anomaly.window_start else None),
            "window_end": (anomaly.window_end.isoformat() if anomaly.window_end else None),
            "details": anomaly.details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def execute(self, anomaly: AnomalyResult) -> dict[str, Any]:
        """
        Execute the remediation playbook for a detected anomaly.

        Returns a dict with status, actions taken, and any response data.
        """
        if not settings.remediation_enabled:
            logger.info(
                "Remediation disabled — skipping for %s anomaly on %s",
                anomaly.anomaly_type,
                anomaly.service_name,
            )
            REMEDIATION_TRIGGERED_TOTAL.labels(service=anomaly.service_name, status="SKIPPED").inc()
            return {
                "status": "SKIPPED",
                "reason": "Remediation is disabled",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        payload = self._build_payload(anomaly)

        if settings.remediation_mode == "mock":
            return await self._execute_mock(anomaly, payload)
        elif settings.remediation_mode == "lambda":
            return await self._execute_lambda(anomaly, payload)
        else:
            logger.error("Unknown remediation mode: %s", settings.remediation_mode)
            return {"status": "FAILED", "reason": f"Unknown mode: {settings.remediation_mode}"}

    async def _execute_mock(
        self, anomaly: AnomalyResult, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Mock remediation — logs actions without calling external services."""
        actions = self._determine_actions(anomaly)

        logger.info(
            "[MOCK REMEDIATION] Service=%s Type=%s Severity=%s Actions=%s",
            anomaly.service_name,
            anomaly.anomaly_type,
            anomaly.severity,
            actions,
        )

        REMEDIATION_TRIGGERED_TOTAL.labels(service=anomaly.service_name, status="SUCCESS").inc()

        return {
            "status": "SUCCESS",
            "mode": "mock",
            "actions": actions,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _execute_lambda(
        self, anomaly: AnomalyResult, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Invoke AWS Lambda remediation function."""
        try:
            import boto3

            client = boto3.client(
                "lambda",
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id or None,
                aws_secret_access_key=settings.aws_secret_access_key or None,
            )

            response = client.invoke(
                FunctionName=settings.aws_lambda_function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload),
            )

            response_payload = json.loads(response["Payload"].read().decode("utf-8"))

            REMEDIATION_TRIGGERED_TOTAL.labels(service=anomaly.service_name, status="SUCCESS").inc()

            logger.info(
                "Lambda remediation successful for %s on %s: %s",
                anomaly.anomaly_type,
                anomaly.service_name,
                response_payload,
            )

            return {
                "status": "SUCCESS",
                "mode": "lambda",
                "lambda_response": response_payload,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(
                "Lambda invocation failed for %s on %s: %s",
                anomaly.anomaly_type,
                anomaly.service_name,
                str(e),
            )

            # Fallback to webhook if configured
            if settings.remediation_webhook_url:
                return await self._execute_webhook(anomaly, payload)

            REMEDIATION_TRIGGERED_TOTAL.labels(service=anomaly.service_name, status="FAILED").inc()

            return {
                "status": "FAILED",
                "mode": "lambda",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def _execute_webhook(
        self, anomaly: AnomalyResult, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Fallback: POST anomaly data to a webhook URL."""
        try:
            client = await self._get_http_client()
            response = await client.post(
                settings.remediation_webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

            REMEDIATION_TRIGGERED_TOTAL.labels(service=anomaly.service_name, status="SUCCESS").inc()

            logger.info(
                "Webhook remediation successful for %s on %s",
                anomaly.anomaly_type,
                anomaly.service_name,
            )

            return {
                "status": "SUCCESS",
                "mode": "webhook",
                "response_status": response.status_code,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error("Webhook fallback failed: %s", str(e))

            REMEDIATION_TRIGGERED_TOTAL.labels(service=anomaly.service_name, status="FAILED").inc()

            return {
                "status": "FAILED",
                "mode": "webhook",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def _determine_actions(self, anomaly: AnomalyResult) -> list[str]:
        """
        Decision tree for remediation actions based on anomaly type and severity.

        CRITICAL + ERROR_RATE  → restart signal + alert
        WARNING  + ERROR_RATE  → alert only
        CRITICAL + LATENCY     → alert + scale recommendation
        WARNING  + LATENCY     → alert only
        """
        actions = []

        if anomaly.anomaly_type == "ERROR_RATE":
            if anomaly.severity == "CRITICAL":
                actions.extend(
                    [
                        f"RESTART_SIGNAL: {anomaly.service_name}",
                        f"ALERT: Critical error rate ({anomaly.metric_value:.1%}) on {anomaly.service_name}",
                        f"PAGE_ONCALL: Immediate attention required for {anomaly.service_name}",
                    ]
                )
            else:
                actions.append(
                    f"ALERT: Elevated error rate ({anomaly.metric_value:.1%}) on {anomaly.service_name}"
                )

        elif anomaly.anomaly_type == "LATENCY_SPIKE":
            if anomaly.severity == "CRITICAL":
                actions.extend(
                    [
                        f"ALERT: Critical latency spike (p95={anomaly.metric_value:.0f}ms) on {anomaly.service_name}",
                        f"SCALE_RECOMMENDATION: Consider scaling {anomaly.service_name} horizontally",
                        f"PAGE_ONCALL: Latency degradation on {anomaly.service_name}",
                    ]
                )
            else:
                actions.append(
                    f"ALERT: Latency spike (p95={anomaly.metric_value:.0f}ms) on {anomaly.service_name}"
                )

        return actions

    async def close(self) -> None:
        """Clean up HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()


# Global remediation engine instance
remediation_engine = RemediationEngine()
