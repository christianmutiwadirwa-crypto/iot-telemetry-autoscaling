"""
Virtual Sensor Node (Task L5)

Implements the edge state machine for a single seismic monitoring station:
- Dual reporting modes: Quiescent Summary vs. Triggered High-Resolution Waveform.
- Unique UUIDv4 batch IDs for end-to-end deduplication / idempotency.
- Disconnection resilience: Capped local ring buffer when cellular link drops (Z10).
- Backlog flush: Transmits buffered historical records marked `is_backfill=True`.
- Thundering herd control: Configurable minute-boundary jitter toggle (Z11).
"""

import random
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any, List
from uuid import uuid4

import aiohttp

from simulator.config import (
    DEFAULT_API_KEY,
    DEFAULT_INGEST_URL,
    MAX_BUFFERED_BATCHES,
    SAMPLING_RATE_HZ,
    SEISMIC_TRIGGER_THRESHOLD_G,
    SUMMARY_INTERVAL_SECONDS,
    WAVEFORM_BATCH_SIZE,
)
from simulator.models import SummaryData, TelemetryBatch, WaveformData
from simulator.waveform_generator import SeismicEvent, SeismicWaveformGenerator

logger = logging.getLogger(__name__)


class VirtualSensorNode:
    """Represents an intelligent edge seismic station in the metropolitan network."""

    def __init__(
        self,
        node_id: str,
        sector: str,
        coordinates_km: Tuple[float, float],
        soil_amplification: float = 1.0,
        api_key: str = DEFAULT_API_KEY,
        jitter_enabled: bool = True,
    ):
        self.node_id = node_id
        self.sector = sector
        self.coordinates_km = coordinates_km
        self.soil_amplification = soil_amplification
        self.api_key = api_key
        self.jitter_enabled = jitter_enabled

        # Internal state
        self.is_triggered: bool = False
        self.link_online: bool = True
        self.offline_buffer: deque = deque(maxlen=MAX_BUFFERED_BATCHES)

        # Minute-boundary jitter (spreads 60s summary calls uniformly across 0-59s)
        self.jitter_offset_s: float = random.uniform(0.0, 59.0) if jitter_enabled else 0.0

        # Physical waveform generator engine
        self.generator = SeismicWaveformGenerator(
            node_id=node_id,
            coordinates_km=coordinates_km,
            soil_amplification=soil_amplification,
        )

        # Transmission metrics
        self.sent_summaries_count = 0
        self.sent_waveforms_count = 0
        self.buffered_count = 0
        self.dropped_buffer_count = 0

    def set_link_state(self, online: bool):
        """Simulate cellular tower outage (link down) or restoration (link up)."""
        self.link_online = online
        logger.info("Node %s link changed: online=%s (buffered: %d)", self.node_id, online, len(self.offline_buffer))

    def set_jitter_mode(self, enabled: bool):
        """Toggle jitter on or off to simulate thundering herd."""
        self.jitter_enabled = enabled
        self.jitter_offset_s = random.uniform(0.0, 59.0) if enabled else 0.0

    def generate_summary_batch(
        self,
        sim_time_s: float,
        interval_s: float = SUMMARY_INTERVAL_SECONDS,
    ) -> TelemetryBatch:
        """
        Generates a 60-second quiescent statistical summary batch.
        Samples 1,000 points (representative downsampled baseline) to calculate peak and RMS.
        """
        sample_count = 1000
        _, _, _, peak_g, rms_g = self.generator.generate_window(
            start_sim_time_s=sim_time_s,
            sample_count=sample_count,
            active_event=None,
        )

        summary = SummaryData(
            interval_seconds=interval_s,
            peak_acceleration_g=round(peak_g, 5),
            rms_acceleration_g=round(rms_g, 5),
            sample_count=int(interval_s * SAMPLING_RATE_HZ),
            temperature_c=round(self.generator.temp_base + random.uniform(-0.5, 0.5), 1),
        )

        batch = TelemetryBatch(
            device_id=self.node_id,
            batch_id=uuid4(),
            sector=self.sector,
            sent_at=datetime.now(timezone.utc).isoformat(),
            is_backfill=False,
            payload_type="summary",
            summary=summary,
        )
        return batch

    def generate_waveform_batch(
        self,
        sim_time_s: float,
        active_event: Optional[SeismicEvent],
        sample_count: int = WAVEFORM_BATCH_SIZE,
    ) -> Tuple[TelemetryBatch, float]:
        """
        Generates a 100-sample high-resolution raw acceleration batch.
        Returns:
            (TelemetryBatch, peak_g)
        """
        x, y, z, peak_g, _ = self.generator.generate_window(
            start_sim_time_s=sim_time_s,
            sample_count=sample_count,
            active_event=active_event,
        )

        # Trigger threshold check
        self.is_triggered = peak_g >= SEISMIC_TRIGGER_THRESHOLD_G

        samples = self.generator.format_waveform_samples(x, y, z)
        waveform = WaveformData(
            sampling_rate_hz=SAMPLING_RATE_HZ,
            measured_at_start=datetime.now(timezone.utc).isoformat(),
            samples=samples,
        )

        batch = TelemetryBatch(
            device_id=self.node_id,
            batch_id=uuid4(),
            sector=self.sector,
            sent_at=datetime.now(timezone.utc).isoformat(),
            is_backfill=False,
            payload_type="waveform",
            waveform=waveform,
        )
        return batch, peak_g

    async def emit_batch(
        self,
        session: aiohttp.ClientSession,
        batch: TelemetryBatch,
        ingest_url: str = DEFAULT_INGEST_URL,
    ) -> Dict[str, Any]:
        """
        Sends the batch over HTTPS/HTTP with authentication headers.
        If offline, automatically enqueues to the local ring buffer for backfill.
        """
        if not self.link_online:
            # Mark as backfill and buffer locally
            batch.is_backfill = True
            if len(self.offline_buffer) >= MAX_BUFFERED_BATCHES:
                self.dropped_buffer_count += 1
            self.offline_buffer.append(batch)
            self.buffered_count += 1
            return {"status": "buffered", "batch_id": str(batch.batch_id), "queue_size": len(self.offline_buffer)}

        headers = {
            "Content-Type": "application/json",
            "X-Device-API-Key": self.api_key,
        }

        try:
            payload_json = batch.model_dump_json()
            async with session.post(
                ingest_url,
                data=payload_json,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5.0),
            ) as response:
                if response.status == 202:
                    if batch.payload_type == "summary":
                        self.sent_summaries_count += 1
                    else:
                        self.sent_waveforms_count += 1
                    data = await response.json()
                    return {"status": "accepted", "http_code": 202, "body": data}
                elif response.status == 429:
                    # Backpressure from Ingest API
                    retry_after = response.headers.get("Retry-After", "5")
                    return {"status": "rate_limited", "http_code": 429, "retry_after": retry_after}
                else:
                    text = await response.text()
                    return {"status": "error", "http_code": response.status, "detail": text}
        except (aiohttp.ClientError, TimeoutError) as exc:
            # Network failure during transmission -> save to local buffer
            batch.is_backfill = True
            self.offline_buffer.append(batch)
            self.buffered_count += 1
            return {"status": "network_failure_buffered", "error": str(exc)}

    async def flush_backlog(
        self,
        session: aiohttp.ClientSession,
        ingest_url: str = DEFAULT_INGEST_URL,
        max_batches: Optional[int] = None,
    ) -> int:
        """
        Flushes buffered historical records to the Ingest API with is_backfill=True.
        Returns total number of batches successfully transmitted.
        """
        if not self.link_online or not self.offline_buffer:
            return 0

        flushed = 0
        limit = max_batches or len(self.offline_buffer)

        while self.offline_buffer and flushed < limit:
            batch = self.offline_buffer.popleft()
            batch.is_backfill = True
            batch.sent_at = datetime.now(timezone.utc).isoformat()

            res = await self.emit_batch(session, batch, ingest_url)
            if res.get("status") == "accepted":
                flushed += 1
            elif res.get("status") == "rate_limited":
                # Put back and respect backpressure
                self.offline_buffer.appendleft(batch)
                break
            else:
                # If network dropped again during flush, return batch to queue
                self.offline_buffer.appendleft(batch)
                break

        return flushed
