"""
Health check endpoints — liveness and readiness probes.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter()


@router.get("/health", summary="Liveness probe")
async def health_check():
    """Returns 200 if the service is alive."""
    return {"status": "healthy", "service": "LogSentinel"}


@router.get("/ready", summary="Readiness probe")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Returns 200 if the service is ready (database is reachable)."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        return {"status": "not_ready", "database": "disconnected", "error": str(e)}
