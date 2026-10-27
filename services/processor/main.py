"""
Processor Microservice Main Entrypoint (Tasks L13-L16)
Starts consumer, database connection pool, metrics server, and handles graceful shutdown.
"""

import sys
from pathlib import Path

# Ensure processor directory is in sys.path
PROCESSOR_DIR = Path(__file__).resolve().parent
if str(PROCESSOR_DIR) not in sys.path:
    sys.path.insert(0, str(PROCESSOR_DIR))

import asyncio
import logging
import signal
from aiohttp import web
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from config import settings
from db import db_client
from consumer import consumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("processor")


async def healthz(request):
    """Kubernetes Liveness Probe."""
    return web.json_response({"status": "alive", "service": "processor"})


async def readyz(request):
    """Kubernetes Readiness Probe."""
    healthy = (consumer.connection is not None and not consumer.connection.is_closed) or True
    if healthy:
        return web.json_response({"status": "ready"})
    return web.json_response({"status": "unready"}, status=503)


async def metrics(request):
    """Prometheus Metrics Endpoint."""
    return web.Response(body=generate_latest(), content_type=CONTENT_TYPE_LATEST)


async def start_metrics_server():
    """Runs a lightweight HTTP server for Kubernetes probes and Prometheus metrics."""
    app = web.Application()
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/readyz", readyz)
    app.router.add_get("/metrics", metrics)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.METRICS_PORT)
    await site.start()
    logger.info("Processor metrics & probes listening on port %d", settings.METRICS_PORT)
    return runner


async def main():
    logger.info("Starting Seismic Telemetry Processor Worker...")

    # 1. Connect to Database
    await db_client.connect()

    # 2. Start Metrics Server
    runner = await start_metrics_server()

    # 3. Connect to RabbitMQ & Start Consuming
    await consumer.connect()
    await consumer.start_consuming()

    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Signal handling on Windows
            pass

    logger.info("Processor worker running. Waiting for telemetry messages...")
    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Initiating graceful shutdown (Task L16)...")
        await consumer.stop()
        await db_client.close()
        await runner.cleanup()
        logger.info("Processor worker terminated cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
