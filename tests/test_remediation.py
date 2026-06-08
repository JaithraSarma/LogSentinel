"""
Tests for the remediation engine.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.core.detector import AnomalyResult
from app.core.remediation import RemediationEngine


@pytest.fixture
def engine():
    """Fresh remediation engine for each test."""
    return RemediationEngine()


@pytest.fixture
def sample_anomaly():
    """A sample anomaly result for testing."""
    return AnomalyResult(
        detected=True,
        anomaly_type="ERROR_RATE",
        severity="WARNING",
        metric_value=0.25,
        threshold_value=0.15,
        window_size=100,
        window_start=datetime(2026, 6, 7, 12, 0, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 6, 7, 12, 5, 0, tzinfo=timezone.utc),
        service_name="test-service",
        details={"error_count": 25, "total_count": 100},
    )


@pytest.fixture
def critical_anomaly():
    """A critical severity anomaly for testing."""
    return AnomalyResult(
        detected=True,
        anomaly_type="ERROR_RATE",
        severity="CRITICAL",
        metric_value=0.45,
        threshold_value=0.15,
        window_size=100,
        window_start=datetime(2026, 6, 7, 12, 0, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 6, 7, 12, 5, 0, tzinfo=timezone.utc),
        service_name="test-service",
        details={"error_count": 45, "total_count": 100},
    )


@pytest.fixture
def latency_anomaly():
    """A latency spike anomaly for testing."""
    return AnomalyResult(
        detected=True,
        anomaly_type="LATENCY_SPIKE",
        severity="CRITICAL",
        metric_value=4500.0,
        threshold_value=2000.0,
        window_size=100,
        window_start=datetime(2026, 6, 7, 12, 0, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 6, 7, 12, 5, 0, tzinfo=timezone.utc),
        service_name="test-service",
        details={"p95_latency_ms": 4500.0},
    )


@pytest.mark.asyncio
async def test_remediation_disabled(engine, sample_anomaly):
    """Test that remediation is skipped when disabled."""
    with patch("app.core.remediation.settings") as mock_settings:
        mock_settings.remediation_enabled = False
        result = await engine.execute(sample_anomaly)

    assert result["status"] == "SKIPPED"
    assert "disabled" in result["reason"].lower()


@pytest.mark.asyncio
async def test_mock_remediation(engine, sample_anomaly):
    """Test mock remediation mode returns success with actions."""
    with patch("app.core.remediation.settings") as mock_settings:
        mock_settings.remediation_enabled = True
        mock_settings.remediation_mode = "mock"
        result = await engine.execute(sample_anomaly)

    assert result["status"] == "SUCCESS"
    assert result["mode"] == "mock"
    assert "actions" in result
    assert len(result["actions"]) > 0


@pytest.mark.asyncio
async def test_mock_remediation_critical(engine, critical_anomaly):
    """Test that critical anomalies produce restart + alert + page actions."""
    with patch("app.core.remediation.settings") as mock_settings:
        mock_settings.remediation_enabled = True
        mock_settings.remediation_mode = "mock"
        result = await engine.execute(critical_anomaly)

    assert result["status"] == "SUCCESS"
    actions = result["actions"]
    action_text = " ".join(actions)
    assert "RESTART_SIGNAL" in action_text
    assert "ALERT" in action_text
    assert "PAGE_ONCALL" in action_text


@pytest.mark.asyncio
async def test_mock_remediation_latency(engine, latency_anomaly):
    """Test that latency anomalies produce scale recommendation."""
    with patch("app.core.remediation.settings") as mock_settings:
        mock_settings.remediation_enabled = True
        mock_settings.remediation_mode = "mock"
        result = await engine.execute(latency_anomaly)

    assert result["status"] == "SUCCESS"
    actions = result["actions"]
    action_text = " ".join(actions)
    assert "SCALE_RECOMMENDATION" in action_text


@pytest.mark.asyncio
async def test_determine_actions_warning_error_rate(engine):
    """Test action determination for warning-level error rate."""
    anomaly = AnomalyResult(
        detected=True,
        anomaly_type="ERROR_RATE",
        severity="WARNING",
        metric_value=0.18,
        threshold_value=0.15,
        service_name="my-service",
    )
    actions = engine._determine_actions(anomaly)
    assert len(actions) == 1
    assert "ALERT" in actions[0]


@pytest.mark.asyncio
async def test_determine_actions_critical_error_rate(engine):
    """Test action determination for critical-level error rate."""
    anomaly = AnomalyResult(
        detected=True,
        anomaly_type="ERROR_RATE",
        severity="CRITICAL",
        metric_value=0.45,
        threshold_value=0.15,
        service_name="my-service",
    )
    actions = engine._determine_actions(anomaly)
    assert len(actions) == 3
    assert any("RESTART" in a for a in actions)
    assert any("PAGE_ONCALL" in a for a in actions)


@pytest.mark.asyncio
async def test_build_payload(engine, sample_anomaly):
    """Test that payload construction includes all required fields."""
    payload = engine._build_payload(sample_anomaly)
    assert payload["anomaly_type"] == "ERROR_RATE"
    assert payload["service_name"] == "test-service"
    assert payload["severity"] == "WARNING"
    assert payload["metric_value"] == 0.25
    assert payload["threshold_value"] == 0.15
    assert "timestamp" in payload


@pytest.mark.asyncio
async def test_engine_cleanup(engine):
    """Test that the engine cleans up resources properly."""
    await engine.close()
    # Should not raise even if no client was initialized
