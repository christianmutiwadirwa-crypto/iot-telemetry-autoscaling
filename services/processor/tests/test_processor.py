"""
Integration & Unit tests for Processor Consumer, Deduplication & Event Correlation (Tasks L13, L14, L15)
"""

import pytest
import sys
from pathlib import Path

PROCESSOR_DIR = Path(__file__).resolve().parent.parent
if str(PROCESSOR_DIR) not in sys.path:
    sys.path.insert(0, str(PROCESSOR_DIR))

from consumer import TelemetryConsumer
from db import DatabaseClient
from event_correlator import SeismicEventCorrelator


@pytest.fixture
def mock_db(monkeypatch):
    """Provides an isolated database client instance for tests."""
    client = DatabaseClient()
    monkeypatch.setattr("consumer.db_client", client)
    return client


@pytest.mark.asyncio
async def test_summary_processing_and_deduplication(mock_db):
    """
    Verify summary batch is processed into DB,
    and a duplicate batch ID is safely ignored without creating duplicate rows (Task L14).
    """
    consumer = TelemetryConsumer()
    batch = {
        "device_id": "node-042",
        "batch_id": "11111111-2222-3333-4444-555555555555",
        "sector": "A",
        "sent_at": "2026-10-27T10:00:00Z",
        "is_backfill": False,
        "payload_type": "summary",
        "summary": {
            "interval_seconds": 60,
            "peak_acceleration_g": 0.003,
            "rms_acceleration_g": 0.001,
            "sample_count": 60000,
            "temperature_c": 25.0
        }
    }

    # First pass: must insert
    res1 = await consumer.process_payload(batch, queue_name="telemetry.live")
    assert res1 is True
    assert len(mock_db._memory_summaries) == 1

    # Second pass with identical batch_id: must deduplicate and NOT insert second row
    res2 = await consumer.process_payload(batch, queue_name="telemetry.live")
    assert res2 is True
    assert len(mock_db._memory_summaries) == 1  # Still 1 row!


@pytest.mark.asyncio
async def test_waveform_processing_and_fft(mock_db):
    """Verify waveform processing runs FFT math and stores computed metrics."""
    consumer = TelemetryConsumer()
    batch = {
        "device_id": "node-101",
        "batch_id": "22222222-3333-4444-5555-666666666666",
        "sector": "B",
        "sent_at": "2026-10-27T10:01:00Z",
        "is_backfill": False,
        "payload_type": "waveform",
        "waveform": {
            "sampling_rate_hz": 1000,
            "measured_at_start": "2026-10-27T10:00:59.900Z",
            "samples": [
                {"t_offset_ms": 0, "x": 0.0, "y": 0.0, "z": 0.12},
                {"t_offset_ms": 1, "x": 0.0, "y": 0.0, "z": -0.15},
                {"t_offset_ms": 2, "x": 0.0, "y": 0.0, "z": 0.08},
                {"t_offset_ms": 3, "x": 0.0, "y": 0.0, "z": 0.03},
            ]
        }
    }

    res = await consumer.process_payload(batch, queue_name="telemetry.live")
    assert res is True
    assert len(mock_db._memory_waveforms) == 1

    stored_batch, analysis = mock_db._memory_waveforms[0]
    assert stored_batch["batch_id"] == batch["batch_id"]
    assert analysis["peak_acceleration_g"] == 0.15
    assert "dominant_frequency_hz" in analysis
    assert "spectral_energy" in analysis


@pytest.mark.asyncio
async def test_event_detection_single_node_vs_multi_node(mock_db):
    """
    Task L15: A single triggered node produces no event alert.
    Multiple nearby stations triggered within the window declares an event.
    """
    consumer = TelemetryConsumer()
    # Configure 3 nodes threshold
    consumer.correlator.min_nodes = 3

    # 1. Trigger node-001 (isolated noise / false alarm)
    b1 = {
        "device_id": "node-001",
        "batch_id": "aaaa1111-0000-0000-0000-000000000001",
        "sector": "A",
        "sent_at": "2026-10-27T10:05:00Z",
        "is_backfill": False,
        "payload_type": "waveform",
        "waveform": {
            "sampling_rate_hz": 1000,
            "samples": [{"t_offset_ms": 0, "z": 0.18}]
        }
    }
    await consumer.process_payload(b1, queue_name="telemetry.live")
    assert len(mock_db._memory_events) == 0  # No event declared!

    # 2. Trigger node-002
    b2 = {
        "device_id": "node-002",
        "batch_id": "aaaa1111-0000-0000-0000-000000000002",
        "sector": "A",
        "sent_at": "2026-10-27T10:05:01Z",
        "is_backfill": False,
        "payload_type": "waveform",
        "waveform": {
            "sampling_rate_hz": 1000,
            "samples": [{"t_offset_ms": 0, "z": 0.22}]
        }
    }
    await consumer.process_payload(b2, queue_name="telemetry.live")
    assert len(mock_db._memory_events) == 0  # Still below threshold

    # 3. Trigger node-003 (3rd node in Sector A -> crosses threshold)
    b3 = {
        "device_id": "node-003",
        "batch_id": "aaaa1111-0000-0000-0000-000000000003",
        "sector": "A",
        "sent_at": "2026-10-27T10:05:01Z",
        "is_backfill": False,
        "payload_type": "waveform",
        "waveform": {
            "sampling_rate_hz": 1000,
            "samples": [{"t_offset_ms": 0, "z": 0.25}]
        }
    }
    await consumer.process_payload(b3, queue_name="telemetry.live")
    # Must now declare a confirmed event
    assert len(mock_db._memory_events) == 1
    event = mock_db._memory_events[0]
    assert event["sector"] == "A"
    assert event["triggering_nodes_count"] == 3
    assert event["max_peak_g"] == 0.25


@pytest.mark.asyncio
async def test_backfill_skips_realtime_event_alerts(mock_db):
    """Task L15: Backfill historical batches must not trigger real-time emergency events."""
    consumer = TelemetryConsumer()
    consumer.correlator.min_nodes = 2

    # Send 3 nodes with is_backfill: True
    for i in range(1, 4):
        b = {
            "device_id": f"node-{i:03d}",
            "batch_id": f"bbbb2222-0000-0000-0000-00000000000{i}",
            "sector": "C",
            "sent_at": "2026-10-27T08:00:00Z",
            "is_backfill": True,  # Historical backfill
            "payload_type": "waveform",
            "waveform": {
                "sampling_rate_hz": 1000,
                "samples": [{"t_offset_ms": 0, "z": 0.35}]
            }
        }
        await consumer.process_payload(b, queue_name="telemetry.backfill")

    # Even with high shaking across 3 nodes, backfill data should NOT produce live alert events
    assert len(mock_db._memory_events) == 0


@pytest.mark.asyncio
async def test_malformed_batch_raises_error():
    """Verify malformed payload missing batch_id raises ValueError for DLQ routing."""
    consumer = TelemetryConsumer()
    bad_batch = {
        # missing batch_id
        "device_id": "node-001",
        "sector": "A",
        "payload_type": "summary",
    }
    with pytest.raises(ValueError):
        await consumer.process_payload(bad_batch, queue_name="telemetry.live")
