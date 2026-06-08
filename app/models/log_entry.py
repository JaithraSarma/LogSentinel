"""
LogEntry ORM model — stores every ingested application log.
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
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class LogEntry(Base):
    """Represents a single structured application log entry."""

    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    service_name = Column(String(255), nullable=False, index=True)
    level = Column(String(10), nullable=False, index=True)  # INFO, WARN, ERROR, FATAL
    message = Column(Text, nullable=False)
    latency_ms = Column(Float, nullable=True)
    status_code = Column(Integer, nullable=True)
    trace_id = Column(String(64), nullable=True, index=True)
    metadata_ = Column("metadata", JSON().with_variant(JSONB, "postgresql"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_log_entries_service_timestamp", "service_name", "timestamp"),
        Index("ix_log_entries_level_timestamp", "level", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"<LogEntry(id={self.id}, service={self.service_name}, "
            f"level={self.level}, ts={self.timestamp})>"
        )
