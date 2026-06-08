"""
Anomaly event retrieval endpoints.

GET /api/v1/anomalies      — list anomaly events with filters
GET /api/v1/anomalies/{id} — get a specific anomaly event
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.anomaly_event import AnomalyEvent
from app.schemas.anomaly import AnomalyResponse

router = APIRouter()


@router.get(
    "/anomalies",
    response_model=list[AnomalyResponse],
    summary="List anomaly events",
)
async def list_anomalies(
    service_name: str | None = Query(None, description="Filter by service"),
    anomaly_type: str | None = Query(None, description="ERROR_RATE or LATENCY_SPIKE"),
    severity: str | None = Query(None, description="WARNING or CRITICAL"),
    start_time: datetime | None = Query(None, description="Start of time range"),
    end_time: datetime | None = Query(None, description="End of time range"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Query anomaly events with optional filters and pagination."""
    query = select(AnomalyEvent).order_by(AnomalyEvent.detected_at.desc())

    if service_name:
        query = query.where(AnomalyEvent.service_name == service_name)
    if anomaly_type:
        query = query.where(AnomalyEvent.anomaly_type == anomaly_type)
    if severity:
        query = query.where(AnomalyEvent.severity == severity)
    if start_time:
        query = query.where(AnomalyEvent.detected_at >= start_time)
    if end_time:
        query = query.where(AnomalyEvent.detected_at <= end_time)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    events = result.scalars().all()

    return [AnomalyResponse.model_validate(e) for e in events]


@router.get(
    "/anomalies/{anomaly_id}",
    response_model=AnomalyResponse,
    summary="Get anomaly event by ID",
)
async def get_anomaly(
    anomaly_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a specific anomaly event by its ID."""
    result = await db.execute(select(AnomalyEvent).where(AnomalyEvent.id == anomaly_id))
    event = result.scalar_one_or_none()

    if event is None:
        raise HTTPException(status_code=404, detail="Anomaly event not found")

    return AnomalyResponse.model_validate(event)
