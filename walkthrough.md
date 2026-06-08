# LogSentinel — Build Walkthrough

## Project Location
`C:\Users\Jaith\OneDrive\Desktop\projects\LogSentinel`

## What Was Built

**36 files** across the following components:

### 1. App Core (13 files)
- [config.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/app/config.py) — Pydantic-settings config with all env vars
- [database.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/app/database.py) — Async SQLAlchemy engine + session factory
- [log_entry.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/app/models/log_entry.py) — Log entry ORM model with composite indexes
- [anomaly_event.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/app/models/anomaly_event.py) — Anomaly event ORM model
- [log.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/app/schemas/log.py) — Pydantic schemas for log CRUD
- [anomaly.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/app/schemas/anomaly.py) — Anomaly event schemas
- [detector.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/app/core/detector.py) — **Sliding window anomaly detector** with per-service isolation, cooldown, error rate + p95 latency
- [remediation.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/app/core/remediation.py) — **Remediation engine** with Lambda/mock/webhook modes
- [metrics.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/app/metrics.py) — 7 Prometheus metrics (counters, gauges, histograms)
- [logs.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/app/api/logs.py) — Log ingestion + query endpoints
- [anomalies.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/app/api/anomalies.py) — Anomaly event query endpoints
- [health.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/app/api/health.py) — Health/readiness probes
- [main.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/app/main.py) — FastAPI app with lifespan, CORS, Prometheus instrumentation

### 2. Infrastructure (8 files)
- [Dockerfile](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/infra/docker/Dockerfile) — Multi-stage build, non-root user, health check
- [docker-compose.yml](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/docker-compose.yml) — 5 services (API, PostgreSQL, Prometheus, Grafana, Seed)
- [prometheus.yml](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/infra/prometheus/prometheus.yml) — Scrape config
- [prometheus datasource](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/infra/grafana/provisioning/datasources/prometheus.yml) — Grafana auto-provisioning
- [postgres datasource](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/infra/grafana/provisioning/datasources/postgres.yml) — Grafana PostgreSQL datasource for anomaly feed
- [dashboard.yml](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/infra/grafana/provisioning/dashboards/dashboard.yml) — Dashboard provisioning
- [LogSentinel.json](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/infra/grafana/dashboards/LogSentinel.json) — 8-panel Grafana dashboard
- [handler.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/infra/lambda/handler.py) — Lambda remediation playbook

### 3. Scripts (2 files)
- [seed_data.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/scripts/seed_data.py) — Realistic data generator with anomaly injection for 3 services
- [wait_for_db.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/scripts/wait_for_db.py) — DB readiness checker with exponential backoff

### 4. Tests (5 files)
- [conftest.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/tests/conftest.py) — SQLite in-memory test DB, async fixtures
- [test_health.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/tests/test_health.py) — 2 tests
- [test_log_ingestion.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/tests/test_log_ingestion.py) — 12 tests
- [test_detector.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/tests/test_detector.py) — 9 tests
- [test_remediation.py](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/tests/test_remediation.py) — 9 tests

### 5. Documentation (2 files)
- [README.md](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/README.md) — Full docs with Mermaid architecture diagram, API reference, config table
- [THEORY.md](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/THEORY.md) — 9-section deep-dive with 2-3 paragraphs per section

### 6. Config & Hygiene (6 files)
- [.gitignore](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/.gitignore), [LICENSE](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/LICENSE), [.env.example](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/.env.example)
- [requirements.txt](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/requirements.txt), [requirements-dev.txt](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/requirements-dev.txt)
- [pyproject.toml](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/pyproject.toml), [ci.yml](file:///C:/Users/Jaith/OneDrive/Desktop/projects/LogSentinel/.github/workflows/ci.yml)

## How to Run

```bash
cd C:\Users\Jaith\OneDrive\Desktop\projects\LogSentinel
cp .env.example .env
docker compose up --build -d
# Seed demo data:
docker compose --profile seed up LogSentinel-seed
```

## Next Steps
- Set `C:\Users\Jaith\OneDrive\Desktop\projects\LogSentinel` as the active workspace
- Run `docker compose up --build -d` to start the stack
- Run the seed script to see anomaly detection in action
