"""
Sliding window anomaly detection engine.

Maintains an in-memory deque of recent log entries per service, bounded by
configurable window size and time duration. On each new log entry, it
computes error rate and p95 latency, compares against thresholds, and
returns an AnomalyResult if a threshold is breached.

NOTE: Window state is local to the process. Horizontal scaling requires
Redis-backed window state or a shared store — this is a deliberate
single-instance trade-off for the demo.
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.metrics import (
    ACTIVE_WINDOW_SIZE,
    ANOMALIES_DETECTED_TOTAL,
    ERROR_RATE_GAUGE,
    P95_LATENCY_GAUGE,
)

logger = logging.getLogger(__name__)


@dataclass
class WindowEntry:
    """A single entry in the sliding window."""

    timestamp: datetime
    level: str
    latency_ms: float | None
    service_name: str


@dataclass
class AnomalyResult:
    """Result of anomaly detection for a single log entry."""

    detected: bool = False
    anomaly_type: str | None = None  # ERROR_RATE or LATENCY_SPIKE
    severity: str | None = None  # WARNING or CRITICAL
    metric_value: float = 0.0
    threshold_value: float = 0.0
    window_size: int = 0
    window_start: datetime | None = None
    window_end: datetime | None = None
    service_name: str = ""
    details: dict = field(default_factory=dict)


class ServiceWindow:
    """Sliding window state for a single service."""

    def __init__(self) -> None:
        self.entries: deque[WindowEntry] = deque()
        self.lock = asyncio.Lock()
        self.last_anomaly_time: datetime | None = None

    def _evict_expired(self, now: datetime) -> None:
        """Remove entries outside the time window."""
        cutoff = now - timedelta(seconds=settings.anomaly_window_time_seconds)
        while self.entries and self.entries[0].timestamp < cutoff:
            self.entries.popleft()
        # Also enforce max window size
        while len(self.entries) > settings.anomaly_window_size:
            self.entries.popleft()

    def calculate_error_rate(self) -> float:
        """Calculate the fraction of ERROR + FATAL entries in the window."""
        if not self.entries:
            return 0.0
        error_levels = {"ERROR", "FATAL"}
        error_count = sum(1 for e in self.entries if e.level in error_levels)
        return error_count / len(self.entries)

    def calculate_p95_latency(self) -> float:
        """Calculate the 95th percentile latency from entries with latency data."""
        latencies = sorted(e.latency_ms for e in self.entries if e.latency_ms is not None)
        if not latencies:
            return 0.0
        idx = int(len(latencies) * 0.95)
        idx = min(idx, len(latencies) - 1)
        return latencies[idx]

    def is_in_cooldown(self, now: datetime) -> bool:
        """Check if we're in the post-anomaly cooldown period."""
        if self.last_anomaly_time is None:
            return False
        elapsed = (now - self.last_anomaly_time).total_seconds()
        return elapsed < settings.anomaly_cooldown_seconds


class AnomalyDetector:
    """
    Per-service sliding window anomaly detector.

    Thread-safe via asyncio locks. Each service gets its own independent
    sliding window, preventing cross-service interference.
    """

    def __init__(self) -> None:
        self._windows: dict[str, ServiceWindow] = {}
        self._global_lock = asyncio.Lock()

    async def _get_window(self, service_name: str) -> ServiceWindow:
        """Get or create the sliding window for a service."""
        if service_name not in self._windows:
            async with self._global_lock:
                # Double-check after acquiring lock
                if service_name not in self._windows:
                    self._windows[service_name] = ServiceWindow()
        return self._windows[service_name]

    async def analyze(
        self,
        timestamp: datetime,
        service_name: str,
        level: str,
        latency_ms: float | None,
    ) -> AnomalyResult:
        """
        Feed a new log entry into the detector and check for anomalies.

        Returns an AnomalyResult indicating whether an anomaly was detected
        and its details.
        """
        window = await self._get_window(service_name)

        async with window.lock:
            # Add new entry
            entry = WindowEntry(
                timestamp=timestamp,
                level=level,
                latency_ms=latency_ms,
                service_name=service_name,
            )
            window.entries.append(entry)

            # Evict old entries
            now = datetime.now(timezone.utc)
            window._evict_expired(now)

            # Update Prometheus gauges
            current_size = len(window.entries)
            ACTIVE_WINDOW_SIZE.labels(service=service_name).set(current_size)

            # Need minimum entries for meaningful detection
            min_entries = max(10, settings.anomaly_window_size // 10)
            if current_size < min_entries:
                return AnomalyResult(service_name=service_name)

            # Calculate metrics
            error_rate = window.calculate_error_rate()
            p95_latency = window.calculate_p95_latency()

            ERROR_RATE_GAUGE.labels(service=service_name).set(error_rate)
            P95_LATENCY_GAUGE.labels(service=service_name).set(p95_latency)

            # Check cooldown
            if window.is_in_cooldown(now):
                return AnomalyResult(service_name=service_name)

            # Determine window bounds
            window_start = window.entries[0].timestamp
            window_end = window.entries[-1].timestamp

            # --- Check error rate anomaly ---
            if error_rate >= settings.anomaly_error_rate_threshold:
                severity = (
                    "CRITICAL"
                    if error_rate >= settings.anomaly_error_rate_threshold * 2
                    else "WARNING"
                )
                window.last_anomaly_time = now

                ANOMALIES_DETECTED_TOTAL.labels(
                    service=service_name, type="ERROR_RATE", severity=severity
                ).inc()

                logger.warning(
                    "Anomaly detected: ERROR_RATE=%.2f for service=%s (threshold=%.2f)",
                    error_rate,
                    service_name,
                    settings.anomaly_error_rate_threshold,
                )

                return AnomalyResult(
                    detected=True,
                    anomaly_type="ERROR_RATE",
                    severity=severity,
                    metric_value=error_rate,
                    threshold_value=settings.anomaly_error_rate_threshold,
                    window_size=current_size,
                    window_start=window_start,
                    window_end=window_end,
                    service_name=service_name,
                    details={
                        "error_count": sum(
                            1 for e in window.entries if e.level in {"ERROR", "FATAL"}
                        ),
                        "total_count": current_size,
                        "p95_latency_ms": p95_latency,
                    },
                )

            # --- Check latency anomaly ---
            if p95_latency > 0 and p95_latency >= settings.anomaly_latency_threshold_ms:
                severity = (
                    "CRITICAL"
                    if p95_latency >= settings.anomaly_latency_threshold_ms * 2
                    else "WARNING"
                )
                window.last_anomaly_time = now

                ANOMALIES_DETECTED_TOTAL.labels(
                    service=service_name, type="LATENCY_SPIKE", severity=severity
                ).inc()

                logger.warning(
                    "Anomaly detected: LATENCY_SPIKE p95=%.1fms for service=%s (threshold=%.1fms)",
                    p95_latency,
                    service_name,
                    settings.anomaly_latency_threshold_ms,
                )

                return AnomalyResult(
                    detected=True,
                    anomaly_type="LATENCY_SPIKE",
                    severity=severity,
                    metric_value=p95_latency,
                    threshold_value=settings.anomaly_latency_threshold_ms,
                    window_size=current_size,
                    window_start=window_start,
                    window_end=window_end,
                    service_name=service_name,
                    details={
                        "p95_latency_ms": p95_latency,
                        "error_rate": error_rate,
                    },
                )

        return AnomalyResult(service_name=service_name)

    def get_window_stats(self, service_name: str) -> dict:
        """Get current window statistics for a service (non-async, for metrics)."""
        window = self._windows.get(service_name)
        if not window:
            return {"window_size": 0, "error_rate": 0.0, "p95_latency_ms": 0.0}
        return {
            "window_size": len(window.entries),
            "error_rate": window.calculate_error_rate(),
            "p95_latency_ms": window.calculate_p95_latency(),
        }

    def get_all_services(self) -> list[str]:
        """Return list of all tracked service names."""
        return list(self._windows.keys())


# Global detector instance
detector = AnomalyDetector()
