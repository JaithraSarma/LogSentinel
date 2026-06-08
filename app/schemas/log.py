"""
Pydantic schemas for log ingestion and retrieval.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LogCreate(BaseModel):
    """Schema for creating a single log entry via POST."""

    timestamp: datetime = Field(..., description="When the log event occurred (ISO 8601)")
    service_name: str = Field(
        ..., min_length=1, max_length=255, description="Name of the originating service"
    )
    level: str = Field(
        ...,
        pattern=r"^(DEBUG|INFO|WARN|ERROR|FATAL)$",
        description="Log level",
    )
    message: str = Field(..., min_length=1, description="Log message")
    latency_ms: float | None = Field(None, ge=0, description="Request latency in milliseconds")
    status_code: int | None = Field(None, ge=100, le=599, description="HTTP status code")
    trace_id: str | None = Field(None, max_length=64, description="Distributed trace ID")
    metadata: dict[str, Any] | None = Field(None, description="Additional structured metadata")

    model_config = {
        "json_schema_extra": {
            "example": {
                "timestamp": "2026-06-07T12:00:00Z",
                "service_name": "auth-service",
                "level": "ERROR",
                "message": "Failed to validate JWT token",
                "latency_ms": 2450.0,
                "status_code": 500,
                "trace_id": "abc123def456",
                "metadata": {"user_id": "usr_42", "endpoint": "/api/auth/verify"},
            }
        }
    }


class LogBatchCreate(BaseModel):
    """Schema for batch log ingestion."""

    logs: list[LogCreate] = Field(
        ..., min_length=1, max_length=1000, description="List of log entries"
    )


class LogResponse(BaseModel):
    """Schema for returning a log entry."""

    id: int
    timestamp: datetime
    service_name: str
    level: str
    message: str
    latency_ms: float | None = None
    status_code: int | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LogQueryParams(BaseModel):
    """Query parameters for listing logs."""

    service_name: str | None = None
    level: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class LogIngestionResponse(BaseModel):
    """Response after successful log ingestion."""

    id: int
    anomaly_detected: bool = False
    anomaly_id: int | None = None
    message: str = "Log ingested successfully"


class LogBatchIngestionResponse(BaseModel):
    """Response after successful batch log ingestion."""

    ingested_count: int
    anomalies_detected: int = 0
    anomaly_ids: list[int] = []
    message: str = "Batch ingested successfully"
