"""
AnomalyEvent ORM model — stores every detected anomaly and its remediation status.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class AnomalyEvent(Base):
    """Represents a detected anomaly event with remediation tracking."""

    __tablename__ = "anomaly_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    detected_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    anomaly_type = Column(String(50), nullable=False)  # ERROR_RATE, LATENCY_SPIKE
    severity = Column(String(20), nullable=False)  # WARNING, CRITICAL
    metric_value = Column(Float, nullable=False)
    threshold_value = Column(Float, nullable=False)
    window_size = Column(Integer, nullable=False)
    window_start = Column(DateTime, nullable=False)
    window_end = Column(DateTime, nullable=False)
    service_name = Column(String(255), nullable=False, index=True)
    remediation_status = Column(
        String(20), nullable=False, default="PENDING"
    )  # PENDING, TRIGGERED, SUCCESS, FAILED, SKIPPED
    remediation_response = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    details = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    __table_args__ = (
        Index(
            "ix_anomaly_events_service_detected",
            "service_name",
            "detected_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AnomalyEvent(id={self.id}, type={self.anomaly_type}, "
            f"service={self.service_name}, severity={self.severity})>"
        )
