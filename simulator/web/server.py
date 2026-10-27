"""
FastAPI & WebSocket Server for City Simulation Control Dashboard
Serves interactive real-time control UI at http://localhost:8080.
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from simulator.fleet_manager import FleetManager
from simulator.scenario_controller import ScenarioController

logger = logging.getLogger(__name__)

app = FastAPI(title="City Seismic Fleet Controller & Dashboard")

# Global instances (initialized in create_app or main)
fleet_manager: Optional[FleetManager] = None
scenario_controller: Optional[ScenarioController] = None

# Connected WebSocket clients
active_websockets = set()


class EarthquakeRequest(BaseModel):
    magnitude: float = 6.5
    epicenter_x: float = 0.0
    epicenter_y: float = 0.0
    duration_s: float = 30.0


class NetworkCutRequest(BaseModel):
    sector: str = "B"
    online: bool = False


class FleetSizeRequest(BaseModel):
    target_nodes: int = 500


class JitterRequest(BaseModel):
    enabled: bool = True


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "simulator-dashboard"}


@app.get("/api/fleet/snapshot")
async def get_snapshot():
    if not fleet_manager:
        return {"error": "Fleet manager not initialized"}
    return fleet_manager.get_fleet_snapshot()


@app.post("/api/scenario/earthquake")
async def trigger_earthquake(req: EarthquakeRequest):
    if fleet_manager:
        fleet_manager.trigger_earthquake(
            magnitude=req.magnitude,
            epicenter_km=(req.epicenter_x, req.epicenter_y),
            duration_s=req.duration_s,
        )
        return {"status": "triggered", "magnitude": req.magnitude}
    return {"error": "Fleet manager not ready"}


@app.post("/api/scenario/clear")
async def clear_earthquake():
    if fleet_manager:
        fleet_manager.clear_active_event()
        return {"status": "cleared"}
    return {"error": "Fleet manager not ready"}


@app.post("/api/scenario/network")
async def set_network(req: NetworkCutRequest):
    if fleet_manager:
        fleet_manager.set_sector_network(req.sector, online=req.online)
        return {"status": "updated", "sector": req.sector, "online": req.online}
    return {"error": "Fleet manager not ready"}


@app.post("/api/scenario/jitter")
async def set_jitter(req: JitterRequest):
    if fleet_manager:
        fleet_manager.set_global_jitter(req.enabled)
        return {"status": "updated", "jitter_enabled": req.enabled}
    return {"error": "Fleet manager not ready"}


@app.post("/api/scenario/fleet-size")
async def set_fleet_size(req: FleetSizeRequest):
    if fleet_manager:
        fleet_manager.set_target_fleet_size(req.target_nodes)
        return {"status": "updated", "target_nodes": req.target_nodes}
    return {"error": "Fleet manager not ready"}


@app.post("/api/scenario/timeline/start")
async def start_scenario():
    if scenario_controller:
        scenario_controller.start()
        return {"status": "started", "scenario": scenario_controller.scenario_name}
    return {"error": "Scenario controller not ready"}


@app.post("/api/scenario/timeline/stop")
async def stop_scenario():
    if scenario_controller:
        scenario_controller.stop()
        return {"status": "stopped"}
    return {"error": "Scenario controller not ready"}


@app.get("/api/scenario/status")
async def get_scenario_status():
    if scenario_controller:
        return scenario_controller.get_status()
    return {"is_running": False}


@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    await websocket.accept()
    active_websockets.add(websocket)
    try:
        while True:
            # Keep socket open and process incoming messages if any
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        active_websockets.discard(websocket)
    except Exception:
        active_websockets.discard(websocket)


async def broadcast_telemetry_loop():
    """Broadcasts snapshot to all connected WebSocket clients at ~2 Hz."""
    while True:
        try:
            if active_websockets and fleet_manager:
                snapshot = fleet_manager.get_fleet_snapshot()
                if scenario_controller:
                    snapshot["scenario"] = scenario_controller.get_status()
                for ws in list(active_websockets):
                    try:
                        await ws.send_json(snapshot)
                    except Exception:
                        active_websockets.discard(ws)
        except Exception as e:
            logger.error("Error in websocket broadcast: %s", e)
        await asyncio.sleep(0.5)


# Static assets
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(str(static_dir / "index.html"))
