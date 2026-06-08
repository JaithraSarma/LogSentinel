"""
LogSentinel — AWS Lambda Remediation Playbook

This Lambda function is invoked by the LogSentinel API when an anomaly is
detected. It implements a decision tree to determine appropriate remediation
actions based on anomaly type and severity.

Deployment: Package this file with its requirements.txt and deploy to AWS Lambda.
Runtime: Python 3.10+
Handler: handler.lambda_handler
"""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Main Lambda entry point.

    Expected event payload:
    {
        "anomaly_type": "ERROR_RATE" | "LATENCY_SPIKE",
        "service_name": "auth-service",
        "severity": "WARNING" | "CRITICAL",
        "metric_value": 0.25,
        "threshold_value": 0.15,
        "window_size": 100,
        "window_start": "2026-06-07T12:00:00Z",
        "window_end": "2026-06-07T12:05:00Z",
        "details": { ... },
        "timestamp": "2026-06-07T12:05:01Z"
    }
    """
    logger.info("Remediation playbook invoked: %s", json.dumps(event))

    anomaly_type = event.get("anomaly_type", "UNKNOWN")
    service_name = event.get("service_name", "unknown")
    severity = event.get("severity", "WARNING")
    metric_value = event.get("metric_value", 0)
    threshold_value = event.get("threshold_value", 0)

    actions_taken = []
    recommendations = []

    # ===================================================================
    # Decision Tree
    # ===================================================================

    if anomaly_type == "ERROR_RATE":
        if severity == "CRITICAL":
            # Critical error rate — immediate action required
            actions_taken.append(
                {
                    "action": "RESTART_SIGNAL",
                    "target": service_name,
                    "reason": (
                        f"Critical error rate: {metric_value:.1%} "
                        f"(threshold: {threshold_value:.1%})"
                    ),
                }
            )
            actions_taken.append(
                {
                    "action": "ALERT_DISPATCH",
                    "channel": "pagerduty",
                    "priority": "P1",
                    "message": (
                        f"🚨 CRITICAL: {service_name} error rate at "
                        f"{metric_value:.1%} — restart signal sent"
                    ),
                }
            )
            recommendations.append("Investigate recent deployments or config changes")
            recommendations.append("Check downstream dependency health")
        else:
            # Warning-level error rate — alert only
            actions_taken.append(
                {
                    "action": "ALERT_DISPATCH",
                    "channel": "slack",
                    "priority": "P3",
                    "message": (
                        f"⚠️ WARNING: {service_name} error rate elevated to {metric_value:.1%}"
                    ),
                }
            )
            recommendations.append("Monitor for further degradation")

    elif anomaly_type == "LATENCY_SPIKE":
        if severity == "CRITICAL":
            # Critical latency — alert and recommend scaling
            actions_taken.append(
                {
                    "action": "ALERT_DISPATCH",
                    "channel": "pagerduty",
                    "priority": "P2",
                    "message": (
                        f"🐌 CRITICAL: {service_name} p95 latency at "
                        f"{metric_value:.0f}ms (threshold: {threshold_value:.0f}ms)"
                    ),
                }
            )
            actions_taken.append(
                {
                    "action": "SCALE_RECOMMENDATION",
                    "target": service_name,
                    "reason": "Critical latency spike detected",
                    "suggested_action": "Increase replica count or instance size",
                }
            )
            recommendations.append("Check database connection pool saturation")
            recommendations.append("Review slow query logs")
        else:
            # Warning-level latency
            actions_taken.append(
                {
                    "action": "ALERT_DISPATCH",
                    "channel": "slack",
                    "priority": "P4",
                    "message": (
                        f"⏱️ WARNING: {service_name} latency elevated (p95={metric_value:.0f}ms)"
                    ),
                }
            )
            recommendations.append("Monitor trend — may resolve after traffic subsides")

    else:
        actions_taken.append(
            {
                "action": "LOG_UNKNOWN",
                "message": f"Unknown anomaly type: {anomaly_type}",
            }
        )

    # ===================================================================
    # Response
    # ===================================================================

    response = {
        "status": "success",
        "service_name": service_name,
        "anomaly_type": anomaly_type,
        "severity": severity,
        "actions_taken": actions_taken,
        "recommendations": recommendations,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info("Remediation complete: %s", json.dumps(response))
    return response
