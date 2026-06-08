"""
Tests for health check endpoints.
"""

import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    """Test liveness probe returns healthy status."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "LogSentinel"


@pytest.mark.asyncio
async def test_readiness_check(client):
    """Test readiness probe returns ready status with DB connection."""
    response = await client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"
