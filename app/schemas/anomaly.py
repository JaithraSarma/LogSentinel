"""
Pydantic schemas for anomaly events.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AnomalyResponse(BaseModel):
    """Schema for returning an anomaly event."""

    id: int
    detected_at: datetime
    anomaly_type: str
    severity: str
    metric_value: float
    threshold_value: float
    window_size: int
    window_start: datetime
    window_end: datetime
    service_name: str
    remediation_status: str
    remediation_response: dict[str, Any] | None = None
    details: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class AnomalyQueryParams(BaseModel):
    """Query parameters for listing anomaly events."""

    service_name: str | None = None
    anomaly_type: str | None = None
    severity: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
