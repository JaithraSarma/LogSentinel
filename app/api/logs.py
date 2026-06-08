"""
Log ingestion and retrieval endpoints.

POST /api/v1/logs       — ingest a single log entry
POST /api/v1/logs/batch — ingest a batch of log entries
GET  /api/v1/logs       — query logs with filters
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.detector import AnomalyResult, detector
from app.core.remediation import remediation_engine
from app.database import get_db
from app.metrics import LOG_LATENCY_MS, LOGS_INGESTED_TOTAL
from app.models.anomaly_event import AnomalyEvent
from app.models.log_entry import LogEntry
from app.schemas.log import (
    LogBatchCreate,
    LogBatchIngestionResponse,
    LogCreate,
    LogIngestionResponse,
    LogResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _process_log_entry(
    log_data: LogCreate, db: AsyncSession
) -> tuple[LogEntry, AnomalyResult | None]:
    """
    Persist a log entry and run anomaly detection.
    Returns the saved entry and any anomaly result.
    """
    # 1. Persist log entry
    db_entry = LogEntry(
        timestamp=log_data.timestamp,
        service_name=log_data.service_name,
        level=log_data.level,
        message=log_data.message,
        latency_ms=log_data.latency_ms,
        status_code=log_data.status_code,
        trace_id=log_data.trace_id,
        metadata_=log_data.metadata,
        created_at=datetime.now(timezone.utc),
    )
    db.add(db_entry)
    await db.flush()

    # 2. Update Prometheus counters
    LOGS_INGESTED_TOTAL.labels(service=log_data.service_name, level=log_data.level).inc()
    if log_data.latency_ms is not None:
        LOG_LATENCY_MS.labels(service=log_data.service_name).observe(log_data.latency_ms)

    # 3. Feed into anomaly detector
    anomaly_result = await detector.analyze(
        timestamp=log_data.timestamp,
        service_name=log_data.service_name,
        level=log_data.level,
        latency_ms=log_data.latency_ms,
    )

    return db_entry, anomaly_result


async def _handle_anomaly(anomaly_result: AnomalyResult, db: AsyncSession) -> int | None:
    """
    If an anomaly was detected, persist it and trigger remediation.
    Returns the anomaly event ID if created.
    """
    if not anomaly_result.detected:
        return None

    # Persist anomaly event
    anomaly_event = AnomalyEvent(
        detected_at=datetime.now(timezone.utc),
        anomaly_type=anomaly_result.anomaly_type,
        severity=anomaly_result.severity,
        metric_value=anomaly_result.metric_value,
        threshold_value=anomaly_result.threshold_value,
        window_size=anomaly_result.window_size,
        window_start=anomaly_result.window_start,
        window_end=anomaly_result.window_end,
        service_name=anomaly_result.service_name,
        remediation_status="PENDING",
        details=anomaly_result.details,
    )
    db.add(anomaly_event)
    await db.flush()

    # Trigger remediation
    try:
        remediation_response = await remediation_engine.execute(anomaly_result)
        anomaly_event.remediation_status = remediation_response.get("status", "FAILED")
        anomaly_event.remediation_response = remediation_response
    except Exception as e:
        logger.error("Remediation failed: %s", str(e))
        anomaly_event.remediation_status = "FAILED"
        anomaly_event.remediation_response = {"error": str(e)}

    return anomaly_event.id


@router.post(
    "/logs",
    response_model=LogIngestionResponse,
    status_code=201,
    summary="Ingest a single log entry",
)
async def ingest_log(log_data: LogCreate, db: AsyncSession = Depends(get_db)):
    """
    Ingest a single structured application log entry.

    The log is persisted to PostgreSQL, fed into the sliding window anomaly
    detector, and if an anomaly is detected, a remediation playbook is triggered.
    """
    db_entry, anomaly_result = await _process_log_entry(log_data, db)
    anomaly_id = await _handle_anomaly(anomaly_result, db)
    await db.commit()

    return LogIngestionResponse(
        id=db_entry.id,
        anomaly_detected=anomaly_result.detected if anomaly_result else False,
        anomaly_id=anomaly_id,
        message="Log ingested successfully",
    )


@router.post(
    "/logs/batch",
    response_model=LogBatchIngestionResponse,
    status_code=201,
    summary="Ingest a batch of log entries",
)
async def ingest_log_batch(batch: LogBatchCreate, db: AsyncSession = Depends(get_db)):
    """
    Ingest a batch of structured log entries (up to 1000 per request).

    Each log is independently analyzed for anomalies.
    """
    anomaly_ids = []
    anomalies_count = 0

    for log_data in batch.logs:
        db_entry, anomaly_result = await _process_log_entry(log_data, db)
        anomaly_id = await _handle_anomaly(anomaly_result, db)
        if anomaly_id is not None:
            anomalies_count += 1
            anomaly_ids.append(anomaly_id)

    await db.commit()

    return LogBatchIngestionResponse(
        ingested_count=len(batch.logs),
        anomalies_detected=anomalies_count,
        anomaly_ids=anomaly_ids,
        message=f"Batch of {len(batch.logs)} logs ingested successfully",
    )


@router.get(
    "/logs",
    response_model=list[LogResponse],
    summary="Query log entries",
)
async def list_logs(
    service_name: str | None = Query(None, description="Filter by service name"),
    level: str | None = Query(None, description="Filter by log level"),
    start_time: datetime | None = Query(None, description="Start of time range"),
    end_time: datetime | None = Query(None, description="End of time range"),
    limit: int = Query(50, ge=1, le=500, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: AsyncSession = Depends(get_db),
):
    """Query log entries with optional filters and pagination."""
    query = select(LogEntry).order_by(LogEntry.timestamp.desc())

    if service_name:
        query = query.where(LogEntry.service_name == service_name)
    if level:
        query = query.where(LogEntry.level == level)
    if start_time:
        query = query.where(LogEntry.timestamp >= start_time)
    if end_time:
        query = query.where(LogEntry.timestamp <= end_time)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    entries = result.scalars().all()

    return [
        LogResponse(
            id=e.id,
            timestamp=e.timestamp,
            service_name=e.service_name,
            level=e.level,
            message=e.message,
            latency_ms=e.latency_ms,
            status_code=e.status_code,
            trace_id=e.trace_id,
            metadata=e.metadata_,
            created_at=e.created_at,
        )
        for e in entries
    ]


@router.get(
    "/logs/stats",
    summary="Get log ingestion statistics",
)
async def log_stats(db: AsyncSession = Depends(get_db)):
    """Returns aggregate statistics about ingested logs."""
    total_result = await db.execute(select(func.count(LogEntry.id)))
    total = total_result.scalar() or 0

    services_result = await db.execute(
        select(LogEntry.service_name, func.count(LogEntry.id)).group_by(LogEntry.service_name)
    )
    by_service = {row[0]: row[1] for row in services_result.all()}

    levels_result = await db.execute(
        select(LogEntry.level, func.count(LogEntry.id)).group_by(LogEntry.level)
    )
    by_level = {row[0]: row[1] for row in levels_result.all()}

    # Get current window stats for each tracked service
    window_stats = {}
    for svc in detector.get_all_services():
        window_stats[svc] = detector.get_window_stats(svc)

    return {
        "total_logs": total,
        "by_service": by_service,
        "by_level": by_level,
        "window_stats": window_stats,
    }
