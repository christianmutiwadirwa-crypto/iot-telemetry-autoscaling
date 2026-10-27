"""
Unit and Integration Tests for Ingest API Service (Tasks L8 & L9)
Validates endpoints, authentication, backpressure, validation errors, and probes.
"""

import pytest
import sys
from pathlib import Path

# Add service directory to sys.path
SERVICE_DIR = Path(__file__).resolve().parent.parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from fastapi.testclient import TestClient
from main import app
from config import settings
import main


@pytest.fixture
def client():
    # Disable RabbitMQ connect attempt during unit tests
    settings.RABBITMQ_ENABLED = False
    with TestClient(app) as c:
        yield c


def test_healthz(client):
    """Verify Kubernetes liveness probe."""
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "alive"}


def test_readyz(client):
    """Verify Kubernetes readiness probe."""
    res = client.get("/readyz")
    assert res.status_code == 200
    assert res.json() == {"status": "ready"}


def test_prometheus_metrics(client):
    """Verify Prometheus metrics scraping endpoint."""
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "telemetry_ingest_requests_total" in res.text


def test_ingest_valid_summary_batch(client):
    """Verify valid summary batch returns 202 Accepted and targets live queue."""
    payload = {
        "device_id": "node-042",
        "batch_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
        "sector": "A",
        "sent_at": "2026-10-27T09:40:00.123Z",
        "is_backfill": False,
        "payload_type": "summary",
        "summary": {
            "interval_seconds": 60,
            "peak_acceleration_g": 0.0034,
            "rms_acceleration_g": 0.0012,
            "sample_count": 60000,
            "temperature_c": 26.5
        }
    }
    headers = {"X-Device-API-Key": "dev-secret-key-123"}
    res = client.post("/api/v1/telemetry", json=payload, headers=headers)

    assert res.status_code == 202
    data = res.json()
    assert data["status"] == "accepted"
    assert data["batch_id"] == "c9bf9e57-1685-4c89-bafb-ff5af830be8a"
    assert data["queue"] == "telemetry.live"
    assert "received_at" in data


def test_ingest_valid_waveform_batch(client):
    """Verify valid waveform batch returns 202 Accepted and targets live queue."""
    payload = {
        "device_id": "node-105",
        "batch_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "sector": "B",
        "sent_at": "2026-10-27T09:40:01.000Z",
        "is_backfill": False,
        "payload_type": "waveform",
        "waveform": {
            "sampling_rate_hz": 1000,
            "measured_at_start": "2026-10-27T09:40:00.900Z",
            "samples": [
                {"t_offset_ms": 0, "x": 0.001, "y": 0.002, "z": 0.085},
                {"t_offset_ms": 1, "x": 0.002, "y": 0.003, "z": 0.092}
            ]
        }
    }
    headers = {"X-Device-API-Key": "dev-secret-key-123"}
    res = client.post("/api/v1/telemetry", json=payload, headers=headers)

    assert res.status_code == 202
    data = res.json()
    assert data["status"] == "accepted"
    assert data["queue"] == "telemetry.live"


def test_ingest_backfill_routing(client):
    """Verify that is_backfill: true routes batch to backfill queue."""
    payload = {
        "device_id": "node-201",
        "batch_id": "e5f67890-abcd-ef12-3456-7890abcdef12",
        "sector": "C",
        "sent_at": "2026-10-27T09:45:00.000Z",
        "is_backfill": True,
        "payload_type": "summary",
        "summary": {
            "interval_seconds": 60,
            "peak_acceleration_g": 0.004,
            "rms_acceleration_g": 0.001,
            "sample_count": 60000
        }
    }
    headers = {"X-Device-API-Key": "dev-secret-key-123"}
    res = client.post("/api/v1/telemetry", json=payload, headers=headers)

    assert res.status_code == 202
    assert res.json()["queue"] == "telemetry.backfill"


def test_authentication_missing_api_key(client):
    """Verify missing API key returns 401 Unauthorized."""
    payload = {
        "device_id": "node-001",
        "batch_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
        "sector": "A",
        "sent_at": "2026-10-27T09:40:00.000Z",
        "is_backfill": False,
        "payload_type": "summary",
        "summary": {
            "interval_seconds": 60,
            "peak_acceleration_g": 0.002,
            "rms_acceleration_g": 0.001,
            "sample_count": 60000
        }
    }
    # No header
    res = client.post("/api/v1/telemetry", json=payload)
    assert res.status_code == 401
    data = res.json()
    assert data["status"] == "error"
    assert data["code"] == "UNAUTHORIZED"


def test_authentication_invalid_api_key(client):
    """Verify wrong API key returns 401 Unauthorized."""
    payload = {
        "device_id": "node-001",
        "batch_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
        "sector": "A",
        "sent_at": "2026-10-27T09:40:00.000Z",
        "is_backfill": False,
        "payload_type": "summary",
        "summary": {
            "interval_seconds": 60,
            "peak_acceleration_g": 0.002,
            "rms_acceleration_g": 0.001,
            "sample_count": 60000
        }
    }
    headers = {"X-Device-API-Key": "wrong-key-456"}
    res = client.post("/api/v1/telemetry", json=payload, headers=headers)
    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHORIZED"


def test_schema_validation_missing_required_field(client):
    """Verify missing sent_at returns 400 Bad Request."""
    invalid_payload = {
        "device_id": "node-001",
        "batch_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
        "sector": "A",
        # missing sent_at
        "is_backfill": False,
        "payload_type": "summary",
        "summary": {
            "interval_seconds": 60,
            "peak_acceleration_g": 0.002,
            "rms_acceleration_g": 0.001,
            "sample_count": 60000
        }
    }
    headers = {"X-Device-API-Key": "dev-secret-key-123"}
    res = client.post("/api/v1/telemetry", json=invalid_payload, headers=headers)
    assert res.status_code == 400
    data = res.json()
    assert data["status"] == "error"
    assert data["code"] == "VALIDATION_FAILED"


def test_backpressure_rate_limiting(client, monkeypatch):
    """Verify that exceeding MAX_INFLIGHT_REQUESTS returns 429 Too Many Requests with Retry-After header."""
    monkeypatch.setattr(settings, "MAX_INFLIGHT_REQUESTS", 0)

    payload = {
        "device_id": "node-001",
        "batch_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
        "sector": "A",
        "sent_at": "2026-10-27T09:40:00.000Z",
        "is_backfill": False,
        "payload_type": "summary",
        "summary": {
            "interval_seconds": 60,
            "peak_acceleration_g": 0.002,
            "rms_acceleration_g": 0.001,
            "sample_count": 60000
        }
    }
    headers = {"X-Device-API-Key": "dev-secret-key-123"}
    res = client.post("/api/v1/telemetry", json=payload, headers=headers)

    assert res.status_code == 429
    assert res.headers.get("Retry-After") == "5"
    data = res.json()
    assert data["status"] == "error"
    assert data["code"] == "RATE_LIMIT_EXCEEDED"
