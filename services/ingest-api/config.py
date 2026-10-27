"""
Configuration settings for the Ingest API service.
Reads configuration from environment variables with production defaults.
"""

import os
from pydantic import BaseModel


class Settings(BaseModel):
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    API_KEY: str = os.getenv("DEVICE_API_KEY", "dev-secret-key-123")

    # RabbitMQ Connection & Queue Topology
    RABBITMQ_URL: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    RABBITMQ_ENABLED: bool = os.getenv("RABBITMQ_ENABLED", "true").lower() in ("true", "1", "yes")
    QUEUE_LIVE: str = os.getenv("QUEUE_LIVE", "telemetry.live")
    QUEUE_BACKFILL: str = os.getenv("QUEUE_BACKFILL", "telemetry.backfill")
    QUEUE_DLQ: str = os.getenv("QUEUE_DLQ", "telemetry.dlq")

    # Ingestion Backpressure & Rate Control
    MAX_INFLIGHT_REQUESTS: int = int(os.getenv("MAX_INFLIGHT_REQUESTS", "2500"))
    RETRY_AFTER_SECONDS: int = int(os.getenv("RETRY_AFTER_SECONDS", "5"))


settings = Settings()
