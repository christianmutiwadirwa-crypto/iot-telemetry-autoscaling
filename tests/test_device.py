"""
Unit tests for Task L5: Virtual Sensor Node
Verifies summary and raw waveform batch generation, unique batch IDs,
and offline local ring buffering.
"""

import pytest
from uuid import UUID
from aiohttp import web
from simulator.virtual_device import VirtualSensorNode
from simulator.models import TelemetryBatch
from simulator.waveform_generator import SeismicEvent


def test_virtual_node_summary_batch():
    """Verify summary batch generation conforming to schema."""
    node = VirtualSensorNode(
        node_id="node-042",
        sector="A",
        coordinates_km=(0.5, -0.5),
    )
    batch = node.generate_summary_batch(sim_time_s=10.0)

    assert isinstance(batch, TelemetryBatch)
    assert batch.device_id == "node-042"
    assert batch.sector == "A"
    assert batch.payload_type == "summary"
    assert batch.summary is not None
    assert batch.waveform is None
    assert isinstance(batch.batch_id, UUID)
    assert batch.is_backfill is False
    assert batch.summary.peak_acceleration_g >= 0.0
    assert batch.summary.sample_count == 60000


def test_virtual_node_waveform_batch():
    """Verify waveform batch generation during seismic event."""
    node = VirtualSensorNode(
        node_id="node-105",
        sector="B",
        coordinates_km=(5.0, -3.0),
    )
    event = SeismicEvent(
        magnitude=6.0,
        epicenter_km=(5.0, -3.0),
        start_time_s=0.0,
    )
    batch, peak_g = node.generate_waveform_batch(sim_time_s=3.0, active_event=event)

    assert isinstance(batch, TelemetryBatch)
    assert batch.device_id == "node-105"
    assert batch.sector == "B"
    assert batch.payload_type == "waveform"
    assert batch.waveform is not None
    assert batch.summary is None
    assert len(batch.waveform.samples) == 100
    assert batch.waveform.sampling_rate_hz == 1000
    assert peak_g > 0.05
    assert node.is_triggered is True


def test_unique_batch_ids():
    """Verify that successive batches always have distinct UUIDv4 batch IDs for idempotency."""
    node = VirtualSensorNode(
        node_id="node-001",
        sector="A",
        coordinates_km=(0.0, 0.0),
    )
    b1 = node.generate_summary_batch(sim_time_s=0.0)
    b2 = node.generate_summary_batch(sim_time_s=60.0)
    assert b1.batch_id != b2.batch_id


@pytest.mark.asyncio
async def test_offline_buffering_and_backfill():
    """Verify that when the link is down, batches are stored in memory and marked is_backfill."""
    node = VirtualSensorNode(
        node_id="node-201",
        sector="C",
        coordinates_km=(-4.0, 4.0),
    )
    node.set_link_state(False)  # Disconnect link

    batch = node.generate_summary_batch(sim_time_s=0.0)
    assert batch.is_backfill is False

    # Mock session
    import aiohttp
    async with aiohttp.ClientSession() as session:
        result = await node.emit_batch(session, batch)

    assert result["status"] == "buffered"
    assert len(node.offline_buffer) == 1
    buffered_batch = node.offline_buffer[0]
    assert buffered_batch.is_backfill is True


@pytest.mark.asyncio
async def test_mock_ingest_server_dual_mode(aiohttp_client):
    """
    Test that a single virtual device can send both summary and waveform batches
    to an HTTP server and receive 202 Accepted.
    """
    received_batches = []

    async def ingest_handler(request):
        # Validate authentication header
        api_key = request.headers.get("X-Device-API-Key")
        if api_key != "dev-secret-key-123":
            return web.json_response({"error": "unauthorized"}, status=401)
        
        data = await request.json()
        received_batches.append(data)
        return web.json_response({
            "status": "accepted",
            "batch_id": data["batch_id"],
            "queue": "telemetry.live"
        }, status=202)

    app = web.Application()
    app.router.add_post("/api/v1/telemetry", ingest_handler)
    client = await aiohttp_client(app)

    node = VirtualSensorNode(
        node_id="node-001",
        sector="A",
        coordinates_km=(0.0, 0.0),
    )

    url = f"{client.make_url('/api/v1/telemetry')}"

    # 1. Send Summary Batch
    summary_batch = node.generate_summary_batch(sim_time_s=0.0)
    res_summary = await node.emit_batch(client.session, summary_batch, ingest_url=url)
    assert res_summary["status"] == "accepted"
    assert res_summary["http_code"] == 202

    # 2. Send Waveform Batch
    event = SeismicEvent(magnitude=5.5, epicenter_km=(0.0, 0.0), start_time_s=0.0)
    waveform_batch, _ = node.generate_waveform_batch(sim_time_s=3.0, active_event=event)
    res_waveform = await node.emit_batch(client.session, waveform_batch, ingest_url=url)
    assert res_waveform["status"] == "accepted"
    assert res_waveform["http_code"] == 202

    assert len(received_batches) == 2
    assert received_batches[0]["payload_type"] == "summary"
    assert received_batches[1]["payload_type"] == "waveform"
