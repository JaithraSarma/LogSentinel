"""
Tests for the sliding window anomaly detection engine.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.detector import AnomalyDetector


@pytest.fixture
def detector():
    """Fresh detector instance for each test."""
    return AnomalyDetector()


@pytest.mark.asyncio
async def test_no_anomaly_on_normal_traffic(detector):
    """Test that normal traffic does not trigger anomalies."""
    now = datetime.now(timezone.utc)
    for i in range(20):
        result = await detector.analyze(
            timestamp=now + timedelta(seconds=i),
            service_name="test-service",
            level="INFO",
            latency_ms=100.0,
        )
    assert result.detected is False


@pytest.mark.asyncio
async def test_error_rate_anomaly_detection(detector):
    """Test that high error rate triggers an anomaly."""
    now = datetime.now(timezone.utc)
    detected = False

    # Send 20 entries — first 10 are INFO, then fill with errors
    for i in range(10):
        await detector.analyze(
            timestamp=now + timedelta(seconds=i),
            service_name="test-svc",
            level="INFO",
            latency_ms=50.0,
        )

    # Now send errors to push error rate above threshold (0.15)
    for i in range(10, 30):
        result = await detector.analyze(
            timestamp=now + timedelta(seconds=i),
            service_name="test-svc",
            level="ERROR",
            latency_ms=50.0,
        )
        if result.detected:
            detected = True
            assert result.anomaly_type == "ERROR_RATE"
            assert result.severity in ("WARNING", "CRITICAL")
            assert result.metric_value > 0
            break

    assert detected, "Error rate anomaly should have been detected"


@pytest.mark.asyncio
async def test_latency_spike_anomaly_detection(detector):
    """Test that high latency triggers an anomaly."""
    now = datetime.now(timezone.utc)
    detected = False

    # Send entries with normal latency first
    for i in range(10):
        await detector.analyze(
            timestamp=now + timedelta(seconds=i),
            service_name="latency-svc",
            level="INFO",
            latency_ms=100.0,
        )

    # Now send entries with very high latency
    for i in range(10, 25):
        result = await detector.analyze(
            timestamp=now + timedelta(seconds=i),
            service_name="latency-svc",
            level="INFO",
            latency_ms=5000.0,  # Way above the 2000ms threshold
        )
        if result.detected:
            detected = True
            assert result.anomaly_type == "LATENCY_SPIKE"
            break

    assert detected, "Latency spike anomaly should have been detected"


@pytest.mark.asyncio
async def test_cooldown_prevents_duplicate_alerts(detector):
    """Test that the cooldown period prevents rapid-fire anomalies."""
    now = datetime.now(timezone.utc)
    anomaly_count = 0

    # Pump enough entries to trigger anomaly, then keep pumping errors
    for i in range(50):
        result = await detector.analyze(
            timestamp=now + timedelta(seconds=i),
            service_name="cooldown-svc",
            level="ERROR",
            latency_ms=100.0,
        )
        if result.detected:
            anomaly_count += 1

    # Should detect at most 1 anomaly due to cooldown
    assert anomaly_count == 1, f"Expected exactly 1 anomaly due to cooldown, got {anomaly_count}"


@pytest.mark.asyncio
async def test_per_service_isolation(detector):
    """Test that different services have independent windows."""
    now = datetime.now(timezone.utc)

    # Send normal traffic for service A
    for i in range(15):
        await detector.analyze(
            timestamp=now + timedelta(seconds=i),
            service_name="service-a",
            level="INFO",
            latency_ms=50.0,
        )

    # Send error traffic for service B
    detected = False
    for i in range(15):
        result = await detector.analyze(
            timestamp=now + timedelta(seconds=i),
            service_name="service-b",
            level="ERROR",
            latency_ms=50.0,
        )
        if result.detected:
            detected = True
            assert result.service_name == "service-b"

    # Service B should have anomaly, not A
    stats_a = detector.get_window_stats("service-a")
    assert stats_a["error_rate"] == 0.0

    assert detected, "Service B should have detected an anomaly"


@pytest.mark.asyncio
async def test_window_size_enforcement(detector):
    """Test that the sliding window respects the maximum size."""
    now = datetime.now(timezone.utc)

    # Send more entries than window size (default 100)
    for i in range(150):
        await detector.analyze(
            timestamp=now + timedelta(seconds=i),
            service_name="window-svc",
            level="INFO",
            latency_ms=50.0,
        )

    stats = detector.get_window_stats("window-svc")
    assert stats["window_size"] <= 100


@pytest.mark.asyncio
async def test_minimum_entries_before_detection(detector):
    """Test that anomalies are not detected with too few entries."""
    now = datetime.now(timezone.utc)

    # Send only 5 errors — below minimum threshold for detection
    for i in range(5):
        result = await detector.analyze(
            timestamp=now + timedelta(seconds=i),
            service_name="small-svc",
            level="ERROR",
            latency_ms=5000.0,
        )

    assert result.detected is False, "Should not detect anomaly with too few entries"


@pytest.mark.asyncio
async def test_get_all_services(detector):
    """Test listing all tracked services."""
    now = datetime.now(timezone.utc)

    await detector.analyze(now, "svc-alpha", "INFO", 50.0)
    await detector.analyze(now, "svc-beta", "INFO", 50.0)
    await detector.analyze(now, "svc-gamma", "INFO", 50.0)

    services = detector.get_all_services()
    assert set(services) == {"svc-alpha", "svc-beta", "svc-gamma"}


@pytest.mark.asyncio
async def test_critical_severity_on_high_error_rate(detector):
    """Test that very high error rate triggers CRITICAL severity."""
    now = datetime.now(timezone.utc)

    # Minimum entries first
    for i in range(10):
        await detector.analyze(
            timestamp=now + timedelta(seconds=i),
            service_name="crit-svc",
            level="INFO",
            latency_ms=50.0,
        )

    # Now pump ALL errors to get error rate > 0.30 (2x threshold)
    detected = False
    for i in range(10, 50):
        result = await detector.analyze(
            timestamp=now + timedelta(seconds=i),
            service_name="crit-svc",
            level="ERROR",
            latency_ms=50.0,
        )
        if result.detected:
            detected = True
            # Error rate should be high enough for CRITICAL
            if result.metric_value >= 0.30:
                assert result.severity == "CRITICAL"
            break

    assert detected
