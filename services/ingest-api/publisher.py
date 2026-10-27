"""
Asynchronous RabbitMQ Message Publisher (Tasks L10 & L11)
Handles durable queue declarations, priority routing (live vs. backfill),
and graceful connection degradation.
"""

import asyncio
import logging
from typing import Optional
import aio_pika
from aio_pika import Message, DeliveryMode

from config import settings
from models import TelemetryBatch

logger = logging.getLogger(__name__)


class RabbitMQPublisher:
    """Manages asynchronous publishing of telemetry payloads to RabbitMQ."""

    def __init__(self):
        self.connection: Optional[aio_pika.abc.AbstractRobustConnection] = None
        self.channel: Optional[aio_pika.abc.AbstractChannel] = None
        self.is_connected: bool = False
        self._lock = asyncio.Lock()

    async def connect(self):
        """Establishes robust connection and declares queues."""
        if not settings.RABBITMQ_ENABLED:
            logger.info("RabbitMQ is disabled by config. Operating in fallback memory mode.")
            return

        async with self._lock:
            if self.is_connected and self.connection and not self.connection.is_closed:
                return

            try:
                self.connection = await aio_pika.connect_robust(
                    settings.RABBITMQ_URL,
                    timeout=5.0,
                )
                self.channel = await self.connection.channel()
                await self.channel.set_qos(prefetch_count=100)

                # Declare durable queues
                # 1. Dead Letter Queue
                await self.channel.declare_queue(
                    settings.QUEUE_DLQ,
                    durable=True,
                )

                # 2. Backfill Queue (Lower priority, historical data)
                await self.channel.declare_queue(
                    settings.QUEUE_BACKFILL,
                    durable=True,
                    arguments={
                        "x-dead-letter-exchange": "",
                        "x-dead-letter-routing-key": settings.QUEUE_DLQ,
                    },
                )

                # 3. Live Telemetry Queue (Priority queue for real-time quake alerts)
                await self.channel.declare_queue(
                    settings.QUEUE_LIVE,
                    durable=True,
                    arguments={
                        "x-max-priority": 10,
                        "x-dead-letter-exchange": "",
                        "x-dead-letter-routing-key": settings.QUEUE_DLQ,
                    },
                )

                self.is_connected = True
                logger.info("Connected to RabbitMQ and declared queues: %s, %s, %s",
                            settings.QUEUE_LIVE, settings.QUEUE_BACKFILL, settings.QUEUE_DLQ)
            except Exception as e:
                self.is_connected = False
                logger.warning("Could not connect to RabbitMQ (%s). Ingestion running in fallback buffer mode.", e)

    async def publish_batch(self, batch: TelemetryBatch) -> str:
        """
        Publishes validated telemetry batch to appropriate queue.
        Returns the destination queue name.
        """
        target_queue = settings.QUEUE_BACKFILL if batch.is_backfill else settings.QUEUE_LIVE

        if self.is_connected and self.channel and not self.channel.is_closed:
            # Set priority: waveform gets high priority (9), summary gets normal (2)
            priority = 9 if batch.payload_type == "waveform" else 2

            message = Message(
                body=batch.model_dump_json().encode("utf-8"),
                delivery_mode=DeliveryMode.PERSISTENT,
                priority=priority,
                message_id=str(batch.batch_id),
                content_type="application/json",
                headers={
                    "device_id": batch.device_id,
                    "sector": batch.sector,
                    "is_backfill": batch.is_backfill,
                    "payload_type": batch.payload_type,
                },
            )

            await self.channel.default_exchange.publish(
                message,
                routing_key=target_queue,
            )
        else:
            # Running in fallback mode (e.g. standalone test or RabbitMQ down)
            logger.debug("Fallback publish: %s -> %s", batch.batch_id, target_queue)

        return target_queue

    async def is_healthy(self) -> bool:
        """Check if connection to RabbitMQ is alive."""
        if not settings.RABBITMQ_ENABLED:
            return True
        return self.is_connected and self.connection is not None and not self.connection.is_closed

    async def close(self):
        """Close connection cleanly."""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            self.is_connected = False
            logger.info("RabbitMQ connection closed.")


publisher = RabbitMQPublisher()
