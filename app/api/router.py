"""
Top-level API router — aggregates all sub-routers.
"""

from fastapi import APIRouter

from app.api.anomalies import router as anomalies_router
from app.api.health import router as health_router
from app.api.logs import router as logs_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["Health"])
api_router.include_router(logs_router, prefix="/api/v1", tags=["Logs"])
api_router.include_router(anomalies_router, prefix="/api/v1", tags=["Anomalies"])
