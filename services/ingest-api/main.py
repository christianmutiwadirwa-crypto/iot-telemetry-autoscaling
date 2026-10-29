"""
FastAPI Ingest API Microservice (Tasks L8, L9, L11)

Accepts high-concurrency IoT telemetry batches from 500 virtual seismic nodes,
performs schema validation, validates per-device API keys, enforces backpressure,
and enqueues batches to RabbitMQ (live vs. backfill).
"""

import sys
from pathlib import Path

# Ensure service directory is in sys.path
SERVICE_DIR = Path(__file__).resolve().parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import time
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from config import settings
from models import TelemetryBatch, IngestAcceptedResponse, ErrorResponse
from publisher import publisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest-api")

# Prometheus Metrics Instrumentation
REQUESTS_TOTAL = Counter(
    "telemetry_ingest_requests_total",
    "Total incoming telemetry batches received",
    ["status", "payload_type"],
)
RATE_LIMITED_TOTAL = Counter(
    "telemetry_ingest_rate_limited_total",
    "Total requests rejected due to backpressure 429",
)
INGEST_LATENCY = Histogram(
    "telemetry_ingest_latency_seconds",
    "Ingestion processing latency from request arrival to RabbitMQ publish",
    buckets=[0.001, 0.005, 0.010, 0.025, 0.050, 0.100, 0.250, 0.500, 1.0],
)

# Concurrency tracker for backpressure
current_inflight_requests = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle startup and shutdown handler."""
    logger.info("Starting Ingest API on %s:%d", settings.HOST, settings.PORT)
    await publisher.connect()
    yield
    logger.info("Shutting down Ingest API...")
    await publisher.close()


app = FastAPI(
    title="Cloud-Native IoT Telemetry Ingest API",
    version="1.0.0",
    lifespan=lifespan,
)


# Custom validation error handler (returns 400 with strict API contract body)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    first_error = errors[0] if errors else {}
    msg = first_error.get("msg", "Malformed JSON or validation error")
    loc = " -> ".join(str(l) for l in first_error.get("loc", []))
    detail = f"Field '{loc}': {msg}" if loc else msg

    REQUESTS_TOTAL.labels(status="400", payload_type="unknown").inc()
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ErrorResponse(
            status="error",
            code="VALIDATION_FAILED",
            detail=detail,
        ).model_dump(),
    )


@app.post(
    "/api/v1/telemetry",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestAcceptedResponse,
    responses={
        202: {"model": IngestAcceptedResponse, "description": "Batch accepted and enqueued"},
        400: {"model": ErrorResponse, "description": "Validation failed"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate limited / backpressure"},
    },
)
async def ingest_telemetry(
    batch: TelemetryBatch,
    response: Response,
    x_device_api_key: Optional[str] = Header(None, alias="X-Device-API-Key"),
):
    global current_inflight_requests
    start_time = time.perf_counter()

    # 1. Per-Device Authentication (Task L9)
    if not x_device_api_key or x_device_api_key != settings.API_KEY:
        REQUESTS_TOTAL.labels(status="401", payload_type=batch.payload_type).inc()
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=ErrorResponse(
                status="error",
                code="UNAUTHORIZED",
                detail="Invalid or missing device API key.",
            ).model_dump(),
        )

    # 2. Backpressure Protection (Task L9)
    if current_inflight_requests >= settings.MAX_INFLIGHT_REQUESTS:
        RATE_LIMITED_TOTAL.inc()
        REQUESTS_TOTAL.labels(status="429", payload_type=batch.payload_type).inc()
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(settings.RETRY_AFTER_SECONDS)},
            content=ErrorResponse(
                status="error",
                code="RATE_LIMIT_EXCEEDED",
                detail=f"Server under heavy load. Retry after {settings.RETRY_AFTER_SECONDS} seconds.",
            ).model_dump(),
        )

    current_inflight_requests += 1
    try:
        # 3. Publish to RabbitMQ (Tasks L10 & L11)
        queue_name = await publisher.publish_batch(batch)

        received_iso = datetime.now(timezone.utc).isoformat()
        REQUESTS_TOTAL.labels(status="202", payload_type=batch.payload_type).inc()

        duration = time.perf_counter() - start_time
        INGEST_LATENCY.observe(duration)

        return IngestAcceptedResponse(
            status="accepted",
            batch_id=str(batch.batch_id),
            queue=queue_name,
            received_at=received_iso,
        )
    finally:
        current_inflight_requests -= 1


@app.get("/healthz", status_code=status.HTTP_200_OK)
async def healthz():
    """Kubernetes Liveness Probe."""
    return {"status": "alive"}


@app.get("/readyz")
async def readyz():
    """Kubernetes Readiness Probe (checks RabbitMQ connectivity)."""
    healthy = await publisher.is_healthy()
    if healthy:
        return {"status": "ready"}
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "unready", "reason": "RabbitMQ broker unavailable"},
    )


@app.get("/metrics")
async def metrics():
    """Prometheus Metrics Endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT, log_level="info")
