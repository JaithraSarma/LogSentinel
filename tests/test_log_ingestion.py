"""
Tests for log ingestion endpoints.
"""

import pytest

VALID_LOG = {
    "timestamp": "2026-06-07T12:00:00Z",
    "service_name": "test-service",
    "level": "INFO",
    "message": "Test log entry",
    "latency_ms": 150.0,
    "status_code": 200,
    "trace_id": "trace-123456",
    "metadata": {"endpoint": "/api/test"},
}


@pytest.mark.asyncio
async def test_ingest_single_log(client):
    """Test ingesting a single valid log entry."""
    response = await client.post("/api/v1/logs", json=VALID_LOG)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] > 0
    assert data["message"] == "Log ingested successfully"


@pytest.mark.asyncio
async def test_ingest_log_minimal_fields(client):
    """Test ingesting a log with only required fields."""
    minimal = {
        "timestamp": "2026-06-07T12:00:00Z",
        "service_name": "test-service",
        "level": "INFO",
        "message": "Minimal log entry",
    }
    response = await client.post("/api/v1/logs", json=minimal)
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_ingest_log_invalid_level(client):
    """Test that invalid log levels are rejected."""
    invalid = {**VALID_LOG, "level": "INVALID"}
    response = await client.post("/api/v1/logs", json=invalid)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ingest_log_missing_required_field(client):
    """Test that missing required fields cause validation error."""
    missing_message = {
        "timestamp": "2026-06-07T12:00:00Z",
        "service_name": "test-service",
        "level": "INFO",
    }
    response = await client.post("/api/v1/logs", json=missing_message)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ingest_log_negative_latency(client):
    """Test that negative latency is rejected."""
    negative = {**VALID_LOG, "latency_ms": -10.0}
    response = await client.post("/api/v1/logs", json=negative)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ingest_batch(client):
    """Test ingesting a batch of log entries."""
    batch = {"logs": [VALID_LOG, {**VALID_LOG, "level": "WARN", "message": "Second entry"}]}
    response = await client.post("/api/v1/logs/batch", json=batch)
    assert response.status_code == 201
    data = response.json()
    assert data["ingested_count"] == 2


@pytest.mark.asyncio
async def test_ingest_batch_empty(client):
    """Test that empty batch is rejected."""
    response = await client.post("/api/v1/logs/batch", json={"logs": []})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_logs(client):
    """Test listing logs after ingestion."""
    # Ingest some logs
    await client.post("/api/v1/logs", json=VALID_LOG)
    await client.post(
        "/api/v1/logs",
        json={**VALID_LOG, "level": "ERROR", "message": "Error log"},
    )

    # List all
    response = await client.get("/api/v1/logs")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_list_logs_filter_by_level(client):
    """Test filtering logs by level."""
    await client.post("/api/v1/logs", json=VALID_LOG)
    await client.post(
        "/api/v1/logs",
        json={**VALID_LOG, "level": "ERROR", "message": "Error log"},
    )

    response = await client.get("/api/v1/logs?level=ERROR")
    assert response.status_code == 200
    data = response.json()
    assert all(log["level"] == "ERROR" for log in data)


@pytest.mark.asyncio
async def test_list_logs_filter_by_service(client):
    """Test filtering logs by service name."""
    await client.post("/api/v1/logs", json=VALID_LOG)
    await client.post(
        "/api/v1/logs",
        json={**VALID_LOG, "service_name": "other-service"},
    )

    response = await client.get("/api/v1/logs?service_name=test-service")
    assert response.status_code == 200
    data = response.json()
    assert all(log["service_name"] == "test-service" for log in data)


@pytest.mark.asyncio
async def test_list_logs_pagination(client):
    """Test log listing with limit and offset."""
    # Ingest 5 logs
    for i in range(5):
        await client.post(
            "/api/v1/logs",
            json={**VALID_LOG, "message": f"Log {i}"},
        )

    response = await client.get("/api/v1/logs?limit=2&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_log_stats(client):
    """Test log statistics endpoint."""
    await client.post("/api/v1/logs", json=VALID_LOG)
    response = await client.get("/api/v1/logs/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_logs"] >= 1
