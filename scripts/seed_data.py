"""
LogSentinel — Seed Data Generator

Generates realistic log streams for demo services with injected anomaly
patterns (error rate spikes, latency spikes). Sends logs to the running
LogSentinel API via POST requests.

Usage:
    python scripts/seed_data.py                    # Defaults
    python scripts/seed_data.py --duration 60      # Run for 60 seconds
    python scripts/seed_data.py --rate 10           # 10 logs/sec

Environment Variables:
    API_URL                  — LogSentinel API base URL (default: http://localhost:8000)
    SEED_DURATION_SECONDS    — How long to generate data (default: 120)
    SEED_RATE_PER_SECOND     — Logs per second (default: 5)
    SEED_ANOMALY_PROBABILITY — Chance of anomaly injection per cycle (default: 0.08)
"""

import argparse
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("seed")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_URL = os.getenv("API_URL", "http://localhost:8000")
DURATION = int(os.getenv("SEED_DURATION_SECONDS", "120"))
RATE = int(os.getenv("SEED_RATE_PER_SECOND", "5"))
ANOMALY_PROB = float(os.getenv("SEED_ANOMALY_PROBABILITY", "0.08"))

SERVICES = [
    {
        "name": "auth-service",
        "endpoints": ["/api/auth/login", "/api/auth/verify", "/api/auth/refresh"],
        "base_latency": (20, 150),
        "error_rate": 0.02,
    },
    {
        "name": "payment-api",
        "endpoints": ["/api/payments/charge", "/api/payments/refund", "/api/payments/status"],
        "base_latency": (50, 300),
        "error_rate": 0.03,
    },
    {
        "name": "order-processor",
        "endpoints": ["/api/orders/create", "/api/orders/update", "/api/orders/fulfill"],
        "base_latency": (30, 200),
        "error_rate": 0.01,
    },
]

MESSAGES = {
    "INFO": [
        "Request processed successfully",
        "Cache hit for user session",
        "Background job completed",
        "Health check passed",
        "Connection pool refreshed",
    ],
    "WARN": [
        "Retry attempt 2/3 for downstream call",
        "Response time approaching SLA threshold",
        "Connection pool utilization above 80%",
        "Rate limit threshold approaching",
        "Deprecated API version used by client",
    ],
    "ERROR": [
        "Failed to connect to downstream service",
        "Database query timeout after 5000ms",
        "Invalid authentication token",
        "Payment gateway returned 502",
        "Order validation failed: missing required fields",
    ],
    "FATAL": [
        "Unrecoverable error: database connection lost",
        "Out of memory — service shutting down",
        "Critical configuration missing — cannot start",
    ],
}


def generate_normal_log(service: dict) -> dict:
    """Generate a normal (non-anomalous) log entry."""
    level_roll = random.random()
    if level_roll < service["error_rate"]:
        level = "ERROR"
    elif level_roll < service["error_rate"] + 0.05:
        level = "WARN"
    else:
        level = "INFO"

    latency = random.uniform(*service["base_latency"])
    endpoint = random.choice(service["endpoints"])

    status_map = {
        "INFO": random.choice([200, 201, 204]),
        "WARN": 200,
        "ERROR": random.choice([500, 502, 503, 504]),
    }
    status_code = status_map.get(level, 200)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service_name": service["name"],
        "level": level,
        "message": random.choice(MESSAGES[level]),
        "latency_ms": round(latency, 2),
        "status_code": status_code,
        "trace_id": f"trace-{random.randint(100000, 999999)}",
        "metadata": {
            "endpoint": endpoint,
            "user_id": f"usr_{random.randint(1, 1000)}",
            "region": random.choice(["us-east-1", "eu-west-1", "ap-south-1"]),
        },
    }


def generate_error_spike_logs(service: dict, count: int) -> list[dict]:
    """Generate a burst of ERROR/FATAL logs to trigger error rate anomaly."""
    logs = []
    for _ in range(count):
        level = random.choice(["ERROR", "ERROR", "ERROR", "FATAL"])
        logs.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "service_name": service["name"],
                "level": level,
                "message": random.choice(MESSAGES[level]),
                "latency_ms": round(random.uniform(500, 3000), 2),
                "status_code": random.choice([500, 502, 503]),
                "trace_id": f"trace-{random.randint(100000, 999999)}",
                "metadata": {
                    "endpoint": random.choice(service["endpoints"]),
                    "anomaly_injected": True,
                    "pattern": "error_spike",
                },
            }
        )
    return logs


def generate_latency_spike_logs(service: dict, count: int) -> list[dict]:
    """Generate logs with very high latency to trigger latency anomaly."""
    logs = []
    for i in range(count):
        # Gradually increasing latency
        base = 1500 + (i * 200)
        latency = random.uniform(base, base + 500)
        logs.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "service_name": service["name"],
                "level": random.choice(["INFO", "WARN"]),
                "message": "Response time approaching SLA threshold",
                "latency_ms": round(latency, 2),
                "status_code": 200,
                "trace_id": f"trace-{random.randint(100000, 999999)}",
                "metadata": {
                    "endpoint": random.choice(service["endpoints"]),
                    "anomaly_injected": True,
                    "pattern": "latency_spike",
                },
            }
        )
    return logs


def send_log(client: httpx.Client, log_entry: dict) -> bool:
    """Send a single log entry to the API."""
    try:
        resp = client.post(f"{API_URL}/api/v1/logs", json=log_entry, timeout=10.0)
        if resp.status_code == 201:
            data = resp.json()
            if data.get("anomaly_detected"):
                logger.warning(
                    "🚨 ANOMALY DETECTED! ID=%s Service=%s",
                    data.get("anomaly_id"),
                    log_entry["service_name"],
                )
            return True
        else:
            logger.error("API returned %d: %s", resp.status_code, resp.text[:200])
            return False
    except httpx.RequestError as e:
        logger.error("Request failed: %s", str(e))
        return False


def send_batch(client: httpx.Client, logs: list[dict]) -> bool:
    """Send a batch of log entries to the API."""
    try:
        resp = client.post(
            f"{API_URL}/api/v1/logs/batch",
            json={"logs": logs},
            timeout=30.0,
        )
        if resp.status_code == 201:
            data = resp.json()
            if data.get("anomalies_detected", 0) > 0:
                logger.warning(
                    "🚨 %d ANOMALIES DETECTED in batch!",
                    data["anomalies_detected"],
                )
            return True
        else:
            logger.error("Batch API returned %d: %s", resp.status_code, resp.text[:200])
            return False
    except httpx.RequestError as e:
        logger.error("Batch request failed: %s", str(e))
        return False


def wait_for_api(client: httpx.Client, max_retries: int = 30) -> bool:
    """Wait for the API to become healthy."""
    for i in range(max_retries):
        try:
            resp = client.get(f"{API_URL}/health", timeout=5.0)
            if resp.status_code == 200:
                logger.info("✅ API is healthy")
                return True
        except httpx.RequestError:
            pass
        logger.info("Waiting for API... (%d/%d)", i + 1, max_retries)
        time.sleep(2)
    return False


def main():
    parser = argparse.ArgumentParser(description="LogSentinel Seed Data Generator")
    parser.add_argument("--duration", type=int, default=DURATION, help="Duration in seconds")
    parser.add_argument("--rate", type=int, default=RATE, help="Logs per second")
    parser.add_argument(
        "--anomaly-prob", type=float, default=ANOMALY_PROB, help="Anomaly probability"
    )
    parser.add_argument("--api-url", type=str, default=API_URL, help="API base URL")
    args = parser.parse_args()

    api_url_final = args.api_url
    global API_URL
    API_URL = api_url_final

    logger.info("=" * 60)
    logger.info("LogSentinel Seed Data Generator")
    logger.info("=" * 60)
    logger.info("API URL:    %s", API_URL)
    logger.info("Duration:   %d seconds", args.duration)
    logger.info("Rate:       %d logs/sec", args.rate)
    logger.info("Anomaly %%:  %.1f%%", args.anomaly_prob * 100)
    logger.info("Services:   %s", ", ".join(s["name"] for s in SERVICES))
    logger.info("=" * 60)

    client = httpx.Client()

    if not wait_for_api(client):
        logger.error("❌ API is not reachable at %s — aborting", API_URL)
        sys.exit(1)

    start_time = time.time()
    total_sent = 0
    total_errors = 0
    total_anomalies_injected = 0
    interval = 1.0 / args.rate

    try:
        while (time.time() - start_time) < args.duration:
            service = random.choice(SERVICES)

            # Decide if this cycle injects an anomaly
            if random.random() < args.anomaly_prob:
                anomaly_type = random.choice(["error_spike", "latency_spike"])
                count = random.randint(8, 20)

                if anomaly_type == "error_spike":
                    logs = generate_error_spike_logs(service, count)
                    logger.info(
                        "💥 Injecting ERROR SPIKE: %d errors for %s",
                        count,
                        service["name"],
                    )
                else:
                    logs = generate_latency_spike_logs(service, count)
                    logger.info(
                        "🐌 Injecting LATENCY SPIKE: %d slow requests for %s",
                        count,
                        service["name"],
                    )

                total_anomalies_injected += 1
                if send_batch(client, logs):
                    total_sent += len(logs)
                else:
                    total_errors += 1
            else:
                log_entry = generate_normal_log(service)
                if send_log(client, log_entry):
                    total_sent += 1
                else:
                    total_errors += 1

            time.sleep(interval)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        elapsed = time.time() - start_time
        client.close()

        logger.info("=" * 60)
        logger.info("Seed Complete")
        logger.info("=" * 60)
        logger.info("Elapsed:    %.1f seconds", elapsed)
        logger.info("Total sent: %d logs", total_sent)
        logger.info("Errors:     %d", total_errors)
        logger.info("Anomalies injected: %d", total_anomalies_injected)
        logger.info("Avg rate:   %.1f logs/sec", total_sent / max(elapsed, 1))
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
