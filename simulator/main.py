"""
Main CLI Entrypoint for City-Wide Seismic IoT Fleet Simulator
Runs fleet manager with web dashboard (http://localhost:8080) or in headless mode.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn

from simulator.config import DEFAULT_INGEST_URL, DEFAULT_API_KEY
from simulator.fleet_manager import FleetManager
from simulator.scenario_controller import ScenarioController
from simulator.web import server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("simulator")


def parse_args():
    parser = argparse.ArgumentParser(description="City-Wide Seismic IoT Fleet Simulator")
    parser.add_argument(
        "--ingest-url",
        type=str,
        default=DEFAULT_INGEST_URL,
        help=f"Target Ingest API endpoint (default: {DEFAULT_INGEST_URL})",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=DEFAULT_API_KEY,
        help="Device API key header (default: dev-secret-key-123)",
    )
    parser.add_argument(
        "--nodes",
        type=int,
        default=500,
        help="Number of active virtual sensor nodes (50-500, default: 500)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Web dashboard port (default: 8080)",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default=str(Path(__file__).parent / "scenarios" / "earthquake_lifecycle.yaml"),
        help="Path to YAML scenario timeline",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without the web dashboard",
    )
    parser.add_argument(
        "--auto-run-scenario",
        action="store_true",
        help="Automatically start playing the scenario timeline on launch",
    )
    return parser.parse_args()


async def run_simulator(args):
    # 1. Initialize Fleet Manager
    fleet = FleetManager(
        ingest_url=args.ingest_url,
        api_key=args.api_key,
        initial_nodes=args.nodes,
    )
    server.fleet_manager = fleet

    # 2. Initialize Scenario Controller
    scenario_path = args.scenario if Path(args.scenario).exists() else None
    controller = ScenarioController(fleet, scenario_path)
    server.scenario_controller = controller

    # 3. Background fleet runner task
    fleet_task = asyncio.create_task(fleet.run())

    # 4. Background websocket broadcaster
    broadcast_task = asyncio.create_task(server.broadcast_telemetry_loop())

    if args.auto_run_scenario:
        controller.start()

    if args.headless:
        logger.info("Running simulator in HEADLESS mode. Press Ctrl+C to stop.")
        try:
            await fleet_task
        except asyncio.CancelledError:
            pass
    else:
        logger.info("=" * 70)
        logger.info("CITY SEISMIC SIMULATOR DASHBOARD ONLINE")
        logger.info("URL: http://localhost:%d", args.port)
        logger.info("Fleet Size: %d active stations across Sectors A-E", args.nodes)
        logger.info("Ingest Target: %s", args.ingest_url)
        logger.info("=" * 70)

        config = uvicorn.Config(
            app=server.app,
            host="0.0.0.0",
            port=args.port,
            log_level="warning",
            loop="asyncio",
        )
        srv = uvicorn.Server(config)
        await srv.serve()

    fleet.stop()
    fleet_task.cancel()
    broadcast_task.cancel()


def main():
    args = parse_args()
    try:
        asyncio.run(run_simulator(args))
    except KeyboardInterrupt:
        logger.info("Simulator terminated by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
