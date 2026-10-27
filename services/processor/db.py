"""
TimescaleDB / PostgreSQL Storage Client (Tasks L12 & L14)

Handles asynchronous time-series writes, unique constraint deduplication,
and fallback in-memory state tracking for local unit testing.
"""

import json
import logging
from typing import Optional, Dict, Any, Set
from uuid import UUID
import asyncpg

from config import settings

logger = logging.getLogger(__name__)


class DatabaseClient:
    """Manages asynchronous database connection pool and idempotent telemetry storage."""

    def __init__(self, database_url: str = settings.DATABASE_URL):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None
        self.is_connected: bool = False

        # In-memory deduplication set for fallback/unit test mode
        self._memory_batch_ids: Set[str] = set()
        self._memory_summaries: list = []
        self._memory_waveforms: list = []
        self._memory_events: list = []

    async def connect(self):
        """Initializes connection pool to TimescaleDB / PostgreSQL."""
        try:
            self.pool = await asyncpg.create_pool(
                dsn=self.database_url,
                min_size=2,
                max_size=20,
                timeout=5.0,
            )
            self.is_connected = True
            logger.info("Connected to TimescaleDB / PostgreSQL at %s", self.database_url)
        except Exception as e:
            self.is_connected = False
            logger.warning("Could not connect to PostgreSQL (%s). Operating in fallback memory mode.", e)

    async def insert_summary(self, batch: Dict[str, Any]) -> bool:
        """
        Idempotently inserts summary batch.
        Returns True if inserted, False if duplicate was ignored.
        """
        batch_id_str = str(batch["batch_id"])

        if self.is_connected and self.pool:
            query = """
            INSERT INTO telemetry_summaries (
                batch_id, device_id, sector, sent_at, is_backfill,
                interval_seconds, peak_acceleration_g, rms_acceleration_g,
                sample_count, temperature_c
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10
            )
            ON CONFLICT (batch_id) DO NOTHING
            RETURNING id;
            """
            summary = batch.get("summary", {})
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    UUID(batch_id_str),
                    batch["device_id"],
                    batch["sector"],
                    batch["sent_at"],
                    bool(batch.get("is_backfill", False)),
                    float(summary.get("interval_seconds", 60.0)),
                    float(summary.get("peak_acceleration_g", 0.0)),
                    float(summary.get("rms_acceleration_g", 0.0)),
                    int(summary.get("sample_count", 0)),
                    summary.get("temperature_c"),
                )
                return row is not None

        # Fallback in-memory deduplication
        if batch_id_str in self._memory_batch_ids:
            return False  # Duplicate ignored

        self._memory_batch_ids.add(batch_id_str)
        self._memory_summaries.append(batch)
        return True

    async def insert_waveform(self, batch: Dict[str, Any], analysis: Dict[str, float]) -> bool:
        """
        Idempotently inserts waveform batch and computed FFT/RMS metrics.
        Returns True if inserted, False if duplicate was ignored.
        """
        batch_id_str = str(batch["batch_id"])

        if self.is_connected and self.pool:
            query = """
            INSERT INTO telemetry_waveforms (
                batch_id, device_id, sector, sent_at, is_backfill,
                sampling_rate_hz, peak_acceleration_g, rms_acceleration_g,
                dominant_frequency_hz, spectral_energy, sample_count, samples_json
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
            )
            ON CONFLICT (batch_id) DO NOTHING
            RETURNING id;
            """
            waveform = batch.get("waveform", {})
            samples = waveform.get("samples", [])
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    UUID(batch_id_str),
                    batch["device_id"],
                    batch["sector"],
                    batch["sent_at"],
                    bool(batch.get("is_backfill", False)),
                    int(waveform.get("sampling_rate_hz", 1000)),
                    float(analysis.get("peak_acceleration_g", 0.0)),
                    float(analysis.get("rms_acceleration_g", 0.0)),
                    float(analysis.get("dominant_frequency_hz", 0.0)),
                    float(analysis.get("spectral_energy", 0.0)),
                    len(samples),
                    json.dumps(samples),
                )
                return row is not None

        # Fallback in-memory deduplication
        if batch_id_str in self._memory_batch_ids:
            return False  # Duplicate ignored

        self._memory_batch_ids.add(batch_id_str)
        self._memory_waveforms.append((batch, analysis))
        return True

    async def insert_seismic_event(self, event: Dict[str, Any]):
        """Persists a confirmed multi-node earthquake event."""
        if self.is_connected and self.pool:
            query = """
            INSERT INTO seismic_events (
                detected_at, sector, triggering_nodes_count,
                max_peak_g, estimated_magnitude, description
            ) VALUES ($1, $2, $3, $4, $5, $6);
            """
            async with self.pool.acquire() as conn:
                await conn.execute(
                    query,
                    event["detected_at"],
                    event["sector"],
                    event["triggering_nodes_count"],
                    event["max_peak_g"],
                    event["estimated_magnitude"],
                    event["description"],
                )
        else:
            self._memory_events.append(event)

    async def close(self):
        """Closes the connection pool."""
        if self.pool:
            await self.pool.close()
            self.is_connected = False


db_client = DatabaseClient()
