"""
Prometheus metrics definitions for LogSentinel.

Exposes counters, gauges, and histograms for log ingestion,
anomaly detection, and remediation tracking.
"""

from prometheus_client import Counter, Gauge, Histogram

# --- Log Ingestion ---
LOGS_INGESTED_TOTAL = Counter(
    "LogSentinel_logs_ingested_total",
    "Total number of logs ingested",
    ["service", "level"],
)

LOG_LATENCY_MS = Histogram(
    "LogSentinel_log_latency_ms",
    "Latency of ingested log entries in milliseconds",
    ["service"],
    buckets=[10, 25, 50, 100, 250, 500, 1000, 2000, 5000, 10000],
)

# --- Anomaly Detection ---
ANOMALIES_DETECTED_TOTAL = Counter(
    "LogSentinel_anomalies_detected_total",
    "Total number of anomalies detected",
    ["service", "type", "severity"],
)

ACTIVE_WINDOW_SIZE = Gauge(
    "LogSentinel_active_window_size",
    "Current number of entries in the sliding window",
    ["service"],
)

ERROR_RATE_GAUGE = Gauge(
    "LogSentinel_error_rate",
    "Current error rate in the sliding window",
    ["service"],
)

P95_LATENCY_GAUGE = Gauge(
    "LogSentinel_p95_latency_ms",
    "Current p95 latency in the sliding window",
    ["service"],
)

# --- Remediation ---
REMEDIATION_TRIGGERED_TOTAL = Counter(
    "LogSentinel_remediation_triggered_total",
    "Total number of remediation actions triggered",
    ["service", "status"],
)
