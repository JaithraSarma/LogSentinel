"""
LogSentinel — FastAPI application entrypoint.

Initializes the app, mounts routers, configures Prometheus instrumentation,
and manages database lifecycle events.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.router import api_router
from app.config import settings
from app.core.remediation import remediation_engine
from app.database import close_db, init_db

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown events."""
    # Startup
    logger.info("Starting LogSentinel v%s", settings.app_version)
    await init_db()
    logger.info("Database tables initialized")
    yield
    # Shutdown
    logger.info("Shutting down LogSentinel")
    await remediation_engine.close()
    await close_db()
    logger.info("Cleanup complete")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Log Anomaly Detection & Auto-Remediation System. "
        "Ingests structured application logs, detects anomalies using "
        "sliding window analysis, and triggers automated remediation."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware — permissive for local dev, tighten for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all API routes
app.include_router(api_router)

# Prometheus instrumentation
if settings.prometheus_enabled:
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/health", "/ready", "/metrics"],
        inprogress_name="LogSentinel_requests_inprogress",
        inprogress_labels=True,
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    logger.info("Prometheus metrics enabled at /metrics")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level=settings.log_level.lower(),
    )
