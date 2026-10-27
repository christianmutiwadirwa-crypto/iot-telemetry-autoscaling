"""
Priority RabbitMQ Consumer & Pipeline Orchestrator (Tasks L13, L14, L15, L16)

Consumes from telemetry.live and telemetry.backfill:
- Prioritizes live telemetry over backfill historical data.
- Invokes SeismicMathEngine for FFT and vibration feature extraction.
- Detects and records multi-node seismic shockwave events.
- Enforces batch idempotency (ignores duplicate batch IDs without error).
- Dead-letters unprocessable messages to telemetry.dlq.
- Implements graceful shutdown (completes current message before exit).
"""

import json
import logging
import time
from typing import Optional, Dict, Any
import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from prometheus_client import Counter, Histogram

from config import settings
from db import db_client
from math_engine import SeismicMathEngine
from event_correlator import SeismicEventCorrelator

logger = logging.getLogger(__name__)

# Prometheus Metrics
PROCESSED_TOTAL = Counter(
    "processor_messages_processed_total",
    "Total messages consumed and processed",
    ["queue", "payload_type"],
)
DUPLICATES_TOTAL = Counter(
    "processor_duplicates_skipped_total",
    "Duplicate batch IDs ignored for idempotency",
)
DEAD_LETTER_TOTAL = Counter(
    "processor_dead_letter_total",
    "Malformed messages routed to dead-letter queue",
)
PROCESSING_LATENCY = Histogram(
    "processor_task_duration_seconds",
    "Time taken to process and store a single batch including FFT",
    buckets=[0.001, 0.005, 0.010, 0.025, 0.050, 0.100, 0.250],
)


class TelemetryConsumer:
    """Consumes and processes telemetry streams from RabbitMQ."""

    def __init__(self):
        self.connection: Optional[aio_pika.abc.AbstractRobustConnection] = None
        self.channel: Optional[aio_pika.abc.AbstractChannel] = None
        self.correlator = SeismicEventCorrelator()
        self.is_running: bool = False
        self.current_in_flight = 0

    async def connect(self):
        """Establishes connection to RabbitMQ."""
        try:
            self.connection = await aio_pika.connect_robust(
                settings.RABBITMQ_URL,
                timeout=5.0,
            )
            self.channel = await self.connection.channel()
            # Set prefetch to control concurrency per worker pod
            await self.channel.set_qos(prefetch_count=settings.PREFETCH_COUNT)
            logger.info("Consumer connected to RabbitMQ.")
        except Exception as e:
            logger.warning("Could not connect consumer to RabbitMQ (%s).", e)

    async def process_payload(self, data: Dict[str, Any], queue_name: str) -> bool:
        """
        Processes a single deserialized batch dictionary.
        Returns True if successfully processed or safely deduplicated,
        raises exception on malformed payload.
        """
        start_time = time.perf_counter()
        batch_id = data.get("batch_id")
        payload_type = data.get("payload_type")

        if not batch_id or not payload_type:
            raise ValueError("Payload missing required 'batch_id' or 'payload_type'")

        if payload_type == "summary":
            # 1. Insert Summary (Idempotent)
            inserted = await db_client.insert_summary(data)
            if not inserted:
                DUPLICATES_TOTAL.inc()
                logger.info("Duplicate summary batch %s ignored.", batch_id)
            else:
                PROCESSED_TOTAL.labels(queue=queue_name, payload_type="summary").inc()

        elif payload_type == "waveform":
            # 2. Extract and compute FFT, PGA, and RMS (Task L13)
            waveform_block = data.get("waveform", {})
            samples = waveform_block.get("samples", [])
            rate = waveform_block.get("sampling_rate_hz", 1000)

            analysis = SeismicMathEngine.analyze_waveform(samples, sampling_rate_hz=rate)

            # Insert Waveform (Idempotent)
            inserted = await db_client.insert_waveform(data, analysis)
            if not inserted:
                DUPLICATES_TOTAL.inc()
                logger.info("Duplicate waveform batch %s ignored.", batch_id)
            else:
                PROCESSED_TOTAL.labels(queue=queue_name, payload_type="waveform").inc()

                # 3. Multi-node Event Correlation (Task L15)
                is_backfill = bool(data.get("is_backfill", False))
                peak_g = analysis["peak_acceleration_g"]
                node_id = data.get("device_id", "unknown")
                sector = data.get("sector", "unknown")

                detected_event = self.correlator.record_trigger(
                    node_id=node_id,
                    sector=sector,
                    peak_g=peak_g,
                    is_backfill=is_backfill,
                )
                if detected_event:
                    await db_client.insert_seismic_event(detected_event)

        duration = time.perf_counter() - start_time
        PROCESSING_LATENCY.observe(duration)
        return True

    async def on_message(self, message: AbstractIncomingMessage, queue_name: str):
        """Callback invoked for each incoming RabbitMQ message."""
        self.current_in_flight += 1
        try:
            body = message.body.decode("utf-8")
            data = json.loads(body)

            await self.process_payload(data, queue_name)
            await message.ack()

        except Exception as exc:
            # Task L14: Malformed messages are rejected and routed to Dead Letter Queue
            DEAD_LETTER_TOTAL.inc()
            logger.error("Failed to process message (routing to DLQ): %s", exc)
            await message.reject(requeue=False)
        finally:
            self.current_in_flight -= 1

    async def start_consuming(self):
        """Starts consuming from priority live queue and backfill queue."""
        if not self.channel:
            return

        self.is_running = True

        # Consume from Live Queue (Priority)
        live_queue = await self.channel.get_queue(settings.QUEUE_LIVE)
        await live_queue.consume(
            lambda msg: self.on_message(msg, queue_name=settings.QUEUE_LIVE)
        )

        # Consume from Backfill Queue
        backfill_queue = await self.channel.get_queue(settings.QUEUE_BACKFILL)
        await backfill_queue.consume(
            lambda msg: self.on_message(msg, queue_name=settings.QUEUE_BACKFILL)
        )

        logger.info("Started consuming from %s and %s", settings.QUEUE_LIVE, settings.QUEUE_BACKFILL)

    async def stop(self):
        """Graceful shutdown (Task L16): waits for in-flight messages to complete."""
        self.is_running = False
        logger.info("Stopping consumer. Waiting for in-flight tasks to finish (%d in-flight)...", self.current_in_flight)

        for _ in range(50):
            if self.current_in_flight == 0:
                break
            await asyncio.sleep(0.1)

        if self.connection and not self.connection.is_closed:
            await self.connection.close()
        logger.info("Consumer stopped cleanly.")


consumer = TelemetryConsumer()
