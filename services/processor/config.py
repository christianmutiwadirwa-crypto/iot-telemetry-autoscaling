"""
Configuration settings for the Processor microservice.
"""

import os
from pydantic import BaseModel


class ProcessorSettings(BaseModel):
    # RabbitMQ Connection & Queue Topology
    RABBITMQ_URL: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    QUEUE_LIVE: str = os.getenv("QUEUE_LIVE", "telemetry.live")
    QUEUE_BACKFILL: str = os.getenv("QUEUE_BACKFILL", "telemetry.backfill")
    QUEUE_DLQ: str = os.getenv("QUEUE_DLQ", "telemetry.dlq")
    PREFETCH_COUNT: int = int(os.getenv("PREFETCH_COUNT", "100"))

    # TimescaleDB / PostgreSQL Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/telemetry",
    )
    DB_FALLBACK_MEMORY: bool = os.getenv("DB_FALLBACK_MEMORY", "true").lower() in ("true", "1", "yes")

    # Metrics & Health Probe Port
    METRICS_PORT: int = int(os.getenv("METRICS_PORT", "8001"))

    # Event Correlation Window (Task L15)
    CORRELATION_WINDOW_SECONDS: float = float(os.getenv("CORRELATION_WINDOW_SECONDS", "3.0"))
    CORRELATION_MIN_NODES: int = int(os.getenv("CORRELATION_MIN_NODES", "3"))


settings = ProcessorSettings()
