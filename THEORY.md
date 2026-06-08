# LogSentinel — Theory & Deep Dive

**A comprehensive technical document for interview preparation and project presentation.**

This document covers the design philosophy, engineering decisions, and theoretical foundations behind LogSentinel. Each section provides 2–3 substantive paragraphs — enough depth for an informed technical discussion, not just surface-level bullet points.

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [System Design](#2-system-design)
3. [Anomaly Detection Theory](#3-anomaly-detection-theory)
4. [Auto-Remediation Architecture](#4-auto-remediation-architecture)
5. [Observability Stack](#5-observability-stack)
6. [Database Design](#6-database-design)
7. [Docker & CI/CD](#7-docker--cicd)
8. [Production Considerations](#8-production-considerations)
9. [Trade-offs & Alternatives](#9-trade-offs--alternatives)

---

## 1. Problem Statement

Modern distributed systems generate enormous volumes of logs — often millions of entries per hour across dozens of microservices. When something goes wrong, the signal (a sudden spike in error rates or a gradual latency degradation) is buried in noise. Human operators cannot realistically monitor raw log streams in real time. By the time a dashboard is checked or a Slack alert is noticed, the incident may have already cascaded across multiple services, affecting thousands of users. The gap between "something started going wrong" and "someone noticed" is where outages become expensive.

Log anomaly detection systems close this gap by continuously analyzing log streams and surfacing deviations from normal behavior. Rather than relying on static alert rules ("alert if errors > 100 in 5 minutes"), a sliding window approach adapts to the baseline of each service. LogSentinel focuses on two primary signals: **error rate** (the fraction of ERROR and FATAL logs within a time window) and **p95 latency** (the 95th percentile of request durations). These two metrics capture the most common failure modes in web services: things breaking (errors) and things slowing down (latency). By detecting these anomalies automatically and triggering remediation playbooks, LogSentinel reduces the Mean Time to Detection (MTTD) from minutes to seconds.

The value proposition extends beyond just detection. Traditional monitoring tools tell you *that* something is wrong; LogSentinel also acts on it. The auto-remediation layer can restart degraded services, dispatch alerts to the right on-call engineer, and recommend scaling actions — all without human intervention for the initial response. This "detect-and-respond" pipeline transforms the operations model from reactive (wait for pages) to proactive (system self-heals common failure modes).

---

## 2. System Design

LogSentinel follows a classic **ingest → process → store → observe** pipeline, but with a critical addition: an inline anomaly detection step that runs synchronously during log ingestion. When a log entry arrives via the REST API, it passes through three stages: (1) validation and persistence to PostgreSQL, (2) feeding into the per-service sliding window detector, and (3) conditional remediation if an anomaly is detected. This synchronous inline approach was chosen over an asynchronous event-driven design (e.g., Kafka consumer) because it provides immediate feedback to the caller — the API response includes whether an anomaly was detected, which is useful for testing and debugging. The trade-off is that detection latency adds to API response time, but since the sliding window operations are O(n) on a bounded window (n ≤ 100 by default), this overhead is typically under 1ms.

The system is decomposed into four logical components that map cleanly to the codebase. The **API layer** (FastAPI routes) handles HTTP concerns: request validation, response serialization, and dependency injection. The **core layer** contains the domain logic: the `AnomalyDetector` class maintains per-service sliding windows and computes metrics, while the `RemediationEngine` dispatches actions based on anomaly type and severity. The **data layer** (SQLAlchemy models + async sessions) abstracts database interactions. The **metrics layer** (Prometheus client) provides observability. These layers communicate through well-defined interfaces — the API layer calls the core layer with primitive values (timestamps, strings, floats), not HTTP-specific types, making the core logic independently testable.

The component architecture also reflects deployment boundaries. The FastAPI service, PostgreSQL, Prometheus, and Grafana each run as separate containers in Docker Compose, communicating over a shared bridge network. This mirrors how they would deploy in a real environment (ECS tasks, Kubernetes pods). The Lambda remediation function is external by design — it runs in a separate execution environment (AWS Lambda) and communicates via synchronous invocation. For local development, the `REMEDIATION_MODE=mock` setting replaces the Lambda call with a local simulation that logs the same decision tree, so the full pipeline can be exercised without AWS credentials.

---

## 3. Anomaly Detection Theory

The sliding window approach used in LogSentinel is a form of **streaming statistical anomaly detection**. Rather than analyzing the entire historical dataset (which would be computationally expensive and slow to adapt), we maintain a fixed-size window of recent observations per service. This window is bounded by both count (`ANOMALY_WINDOW_SIZE`, default 100 entries) and time (`ANOMALY_WINDOW_TIME_SECONDS`, default 300 seconds). When a new log entry arrives, expired entries are evicted from the front of the deque, the new entry is appended, and two metrics are computed: the error rate (count of ERROR+FATAL entries divided by total entries) and the p95 latency (the value at the 95th percentile of all latency values in the window). If either metric exceeds its configured threshold, an anomaly is detected.

This approach is deliberately **threshold-based** rather than **model-based** (e.g., using machine learning or z-score calculations). The reasoning is pragmatic: threshold-based detection is interpretable, deterministic, and easy to tune. When an alert fires, the operator knows exactly why — "error rate was 0.23, threshold is 0.15" — rather than getting an opaque anomaly score from a trained model. For a system meant to trigger automated remediation, false positives are costly (you don't want to restart a healthy service), so the ability to set explicit, well-understood thresholds is critical. The severity system adds nuance: metric values between 1x and 2x the threshold are classified as WARNING, while values above 2x are CRITICAL. This two-tier approach maps to different remediation responses (alert-only vs. restart + page).

To prevent **alert storms** — where a sustained anomaly triggers hundreds of duplicate alerts — the detector implements a **cooldown period** (default 60 seconds). After detecting an anomaly for a service, no further anomalies are reported for that service until the cooldown expires, even if the metric remains above the threshold. The minimum entry count (10% of window size, minimum 10) prevents false positives during cold start when the window has too few data points for a statistically meaningful calculation. An alternative approach considered was **z-score detection** (flagging values more than N standard deviations from the rolling mean), which would be more adaptive but also more prone to false negatives during gradual degradation — a "boiling frog" scenario where the mean slowly drifts upward. The fixed threshold approach catches both sudden spikes and sustained degradation equally well.

---

## 4. Auto-Remediation Architecture

The remediation engine follows an **event-driven command pattern**: anomaly detection produces an event (the `AnomalyResult`), which the engine translates into a set of actions based on a decision tree. The decision tree considers two dimensions — anomaly type (ERROR_RATE vs. LATENCY_SPIKE) and severity (WARNING vs. CRITICAL) — producing different action sets for each combination. CRITICAL error rates trigger a restart signal, alert dispatch, and on-call page. WARNING error rates trigger an alert only. CRITICAL latency spikes trigger an alert plus a scaling recommendation. This decision tree is intentionally simple and explicit; in a production system, it would evolve based on operational experience and could be externalized into a configuration file or rules engine.

The remediation engine supports three execution modes: **Lambda**, **webhook**, and **mock**. In Lambda mode, the engine invokes an AWS Lambda function via the `boto3` SDK, passing the anomaly payload as the event. The Lambda function implements the same decision tree but in an isolated, serverless environment — this separation is important because the remediation action (e.g., calling the ECS API to restart a task) requires different IAM permissions than the LogSentinel API. The Lambda function returns a structured response that includes the actions taken and recommendations, which is stored on the `AnomalyEvent` record for audit purposes. If Lambda invocation fails (network error, permissions, etc.), the engine falls back to a webhook POST if a `REMEDIATION_WEBHOOK_URL` is configured. This fallback chain ensures that anomalies are always communicated, even if the primary remediation channel is unavailable.

**Idempotency** is a critical concern for remediation actions. Restarting a service that's already restarting, or sending duplicate pages to the on-call engineer, is wasteful and confusing. The cooldown mechanism in the detector is the first line of defense — it prevents duplicate anomaly events from being created. The Lambda function should also be idempotent: if it receives two invocations for the same service within a short window, it should check whether a restart was already initiated before issuing another one. In the current demo implementation, the Lambda logs actions but doesn't actually call cloud provider APIs (ECS, etc.), so idempotency is implicit. A production implementation would add a state check (e.g., querying ECS task status) before issuing restart commands.

---

## 5. Observability Stack

LogSentinel uses the **Prometheus + Grafana** stack for observability, which has become the de facto standard for cloud-native monitoring. Prometheus operates on a **pull model**: it scrapes the `/metrics` endpoint of the LogSentinel API at a configured interval (every 10 seconds in our setup). This is fundamentally different from push-based systems like StatsD or Datadog, where the application pushes metrics to an aggregator. The pull model has several advantages: Prometheus determines the scrape schedule (no thundering herd problem), the application doesn't need to know where metrics go (just expose them), and if Prometheus goes down, the application keeps running — metrics are simply not collected for that interval. The `prometheus-fastapi-instrumentator` library automatically generates request-level metrics (latency histograms, status code counters) for every FastAPI endpoint, while custom metrics (error rate, anomaly count, window size) are defined explicitly using the `prometheus-client` library.

**Metrics cardinality** is a key design consideration. Each unique combination of labels creates a separate time series in Prometheus. If we used high-cardinality labels like `trace_id` or `user_id`, the number of time series would explode and Prometheus would run out of memory. LogSentinel uses only low-cardinality labels: `service` (3–10 unique values), `level` (5 values), `type` (2 values), and `severity` (2 values). This keeps the total time series count manageable. The `LogSentinel_log_latency_ms` histogram uses 10 predefined buckets (10ms to 10,000ms), which creates 10 time series per service — a reasonable overhead for the distributional insight it provides. The p95 latency gauge is computed in the application and exported directly, which is simpler than computing percentiles in PromQL from the histogram (which can be imprecise with few buckets).

The Grafana dashboard is **pre-provisioned** via Grafana's file-based provisioning system. On startup, Grafana reads the datasource YAML files from `/etc/grafana/provisioning/datasources/` and the dashboard JSON from the configured path. This means the dashboard is ready immediately on `docker compose up` — no manual configuration needed. The dashboard uses two datasources: Prometheus (for all metric panels) and PostgreSQL (for the anomaly feed table). The table panel queries the `anomaly_events` table directly with a SQL query, providing richer data than what Prometheus stores (e.g., remediation response details, window timestamps). This dual-datasource approach is standard in production Grafana deployments where you need both time-series metrics and relational data on the same dashboard.

---

## 6. Database Design

The database schema consists of two tables: `log_entries` and `anomaly_events`. The `log_entries` table stores every ingested log with full fidelity — timestamp, service name, log level, message, latency, status code, trace ID, and arbitrary JSON metadata. The `JSONB` column for metadata allows callers to attach any structured data without schema changes, which is critical for a log ingestion service where different teams have different log formats. PostgreSQL's JSONB type supports indexing and querying into JSON structures, so even ad-hoc queries against metadata fields are possible.

**Indexing strategy** is driven by the query patterns. The composite index `(service_name, timestamp)` on `log_entries` supports the most common query: "give me recent logs for service X, ordered by time." The single-column indexes on `level` and `trace_id` support filtering and correlation queries. The `anomaly_events` table has a similar composite index on `(service_name, detected_at)`. These indexes make the primary read paths fast (index scans) without excessive write amplification. In a production system with high write throughput, you might consider partitioning `log_entries` by time (e.g., monthly range partitions) to keep index sizes manageable and enable efficient data retention via partition drops rather than row-level deletes.

The ORM layer uses **SQLAlchemy 2.0 with async support** and the `asyncpg` driver. This combination is the highest-performance option for async PostgreSQL access in Python — `asyncpg` uses PostgreSQL's binary protocol directly (bypassing libpq) and achieves throughput comparable to hand-written SQL. The async session factory uses `expire_on_commit=False` to prevent lazy-loading issues common in async code (since lazy loads would require a synchronous database call, which isn't possible in an async context). The `get_db` dependency creates a new session per request and handles commit/rollback automatically, following the Unit of Work pattern.

---

## 7. Docker & CI/CD

The Dockerfile uses a **multi-stage build** to minimize the runtime image size and attack surface. The first stage (`builder`) installs gcc and libpq-dev — build-time dependencies needed to compile C extensions for `asyncpg` and `psycopg2` — and installs Python packages into a separate prefix (`/install`). The second stage (`runtime`) starts from a clean `python:3.11-slim` image, copies only the compiled packages and application code, and creates a non-root user (`LogSentinel`). This separation means the final image doesn't contain compilers, header files, or pip — only what's needed to run the application. The built-in `HEALTHCHECK` instruction allows Docker (and orchestrators like ECS or Kubernetes) to detect if the container is unhealthy and replace it automatically.

Docker Compose orchestrates five services on a shared bridge network. Service dependencies are managed via `depends_on` with health check conditions — the API service waits for PostgreSQL to pass its `pg_isready` health check before starting. The seed data generator runs as a separate service with the `seed` profile, meaning it doesn't start with the default `docker compose up` but can be invoked explicitly with `docker compose --profile seed up LogSentinel-seed`. This profile-based approach keeps the default startup fast while making the seed script easily accessible. Persistent volumes are used for PostgreSQL data, Prometheus TSDB, and Grafana state, so data survives container restarts.

The **GitHub Actions CI pipeline** runs three sequential jobs: lint, test, and docker-build. The lint job runs `ruff` for both style checking and formatting validation — ruff is a Rust-based Python linter that's 10–100x faster than flake8+black. The test job spins up a PostgreSQL service container (using GitHub Actions' `services` feature), installs dependencies, and runs pytest with coverage reporting. The docker-build job validates that the image builds successfully using Docker Buildx with GitHub Actions cache, which dramatically speeds up subsequent builds by caching intermediate layers. The jobs are ordered with `needs` dependencies: test depends on lint, docker-build depends on test. This fail-fast approach saves CI minutes by not building the Docker image if tests fail.

---

## 8. Production Considerations

**Horizontal scaling** is the most significant gap between this demo and a production deployment. The sliding window state is currently held **in-memory within the process**. If you run multiple API instances behind a load balancer, each instance has its own independent window, which means the same service's logs might be split across instances, producing inaccurate error rate calculations. Horizontal scaling requires offloading the window state to a shared store like **Redis** — each `analyze()` call would read the current window from Redis, append the new entry, evict expired entries, and write back (using Redis transactions or Lua scripts for atomicity). This is a deliberate single-instance trade-off for the demo; the code is structured so that the `ServiceWindow` class could be swapped for a `RedisServiceWindow` implementation without changing the `AnomalyDetector` interface.

**Security** in a production deployment would require several additions. The API should implement authentication (API keys or JWT tokens) to prevent unauthorized log ingestion. Rate limiting (e.g., via a middleware or API gateway) would prevent a single misbehaving service from overwhelming the system. The PostgreSQL connection should use SSL/TLS (`sslmode=require`), and AWS credentials should be provided via IAM roles (not environment variables) when running in AWS. The `.env` file should never be committed to version control (it's in `.gitignore`), and secrets should be managed via AWS Secrets Manager, HashiCorp Vault, or similar. The CORS middleware is currently set to allow all origins (`*`) for development convenience; in production, this should be restricted to specific domains.

**Data retention** is another production concern. A service ingesting 1,000 logs/second would accumulate ~86 million rows per day in `log_entries`. Without retention policies, the database would grow unbounded. The recommended approach is PostgreSQL table partitioning by time (e.g., daily or weekly partitions) combined with a retention job that drops old partitions. Alternatively, log entries could be archived to S3 in Parquet format before deletion, preserving them for compliance or forensic analysis. The `anomaly_events` table grows much more slowly (at most a few events per day per service), so simple row-level deletion with a cron job is sufficient. Prometheus handles its own retention via the `--storage.tsdb.retention.time` flag (set to 7 days in our config).

---

## 9. Trade-offs & Alternatives

**Why FastAPI over Flask?** FastAPI provides native async support via ASGI, which is essential for an I/O-bound service that makes database calls and external API requests on every request. Flask (with WSGI) would require either synchronous processing (blocking the worker thread during DB calls) or bolting on async support via `asgiref` or Celery — adding complexity without the ergonomic benefits. FastAPI also generates OpenAPI schemas automatically from Pydantic models, so the Swagger UI documentation is always in sync with the actual API behavior. The type validation from Pydantic catches malformed requests at the framework level, before application code runs, which reduces defensive coding.

**Why PostgreSQL over TimescaleDB or ClickHouse?** TimescaleDB (a time-series extension for PostgreSQL) would be a natural fit for log data, offering automatic partitioning (hypertables) and time-based aggregation functions. However, it adds deployment complexity (a separate Docker image, additional configuration) and the primary query patterns in LogSentinel (simple INSERTs and filtered SELECTs) don't benefit significantly from TimescaleDB's columnar compression or continuous aggregates. Vanilla PostgreSQL with appropriate indexes handles the expected throughput (hundreds to thousands of logs/second) comfortably. ClickHouse would offer even better analytical performance but is a fundamentally different database paradigm (column-oriented, eventually consistent) that doesn't fit the OLTP pattern of log ingestion. For a production system at very high scale (>10k logs/sec), TimescaleDB or a dedicated log store (Elasticsearch, Loki) would be worth evaluating.

**Why not Kafka?** A common pattern for log processing is to put a message queue (Kafka, RabbitMQ) between the log producers and the processing pipeline. This provides buffering (logs aren't lost if the processor is down), decoupling (producers don't need to know about consumers), and fan-out (multiple consumers can process the same log stream). LogSentinel's synchronous REST API approach skips this layer for simplicity — the API is both the ingestion point and the processor. In a production system, adding Kafka between the API and the detector would provide resilience (logs are persisted in Kafka if the API is temporarily unable to write to PostgreSQL) and would enable horizontal consumer scaling (each consumer processes a partition of the log stream). The trade-off is operational complexity: Kafka requires ZooKeeper (or KRaft), broker configuration, topic management, and monitoring — which is substantial overhead for a system that's primarily a demo.

---

## Summary for Interviewers

LogSentinel demonstrates competency in:

- **System design**: Multi-component architecture with clear responsibility boundaries
- **Python**: Async/await, FastAPI, Pydantic v2, SQLAlchemy 2.0 async
- **Database**: PostgreSQL schema design, indexing strategy, async ORM
- **Algorithm design**: Sliding window with cooldown, per-service isolation
- **DevOps**: Docker multi-stage builds, Compose orchestration, GitHub Actions CI
- **Observability**: Prometheus metrics design (cardinality awareness), Grafana provisioning
- **Cloud**: AWS Lambda integration with fallback chain, IAM considerations
- **Testing**: Async test fixtures, dependency injection overrides, in-memory DB for speed
- **Production awareness**: Scaling trade-offs (in-memory vs. Redis), security, data retention

The key talking points for interviews are the **deliberate trade-offs**: why inline detection over async processing, why thresholds over ML, why in-memory over Redis, why REST over Kafka. Each decision has a clear rationale grounded in the demo's constraints, with a stated path to the production-grade alternative.
