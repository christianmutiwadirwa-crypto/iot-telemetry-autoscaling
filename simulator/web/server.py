"""
FastAPI & WebSocket Server for City Simulation Control Dashboard (Living City Edition).
Serves interactive real-time control UI at http://localhost:8080.
Includes:
- City Layout REST API (/api/city/layout)
- Real-time WebSocket streaming with per-station seismograph wave packets (10 Hz)
- Full fleet & HPA cluster telemetry snapshots (2 Hz)
- Scenario & earthquake triggers with sub-second synchronization
- Cache-control middleware to prevent browser stale cache
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from simulator.fleet_manager import FleetManager
from simulator.scenario_controller import ScenarioController
from simulator.city_layout import get_city_layout
from simulator.cluster_model import ClusterModel

logger = logging.getLogger(__name__)

app = FastAPI(title="City Seismic Fleet Controller & Dashboard")

# Global instances
fleet_manager: Optional[FleetManager] = None
scenario_controller: Optional[ScenarioController] = None
cluster_model = ClusterModel()

# Client tracking: mapping websocket -> selected node_id
active_client_subscriptions: Dict[WebSocket, str] = {}


@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    """Ensure static web assets and API payloads are never served stale during development."""
    response: Response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/" or request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


class EarthquakeRequest(BaseModel):
    magnitude: float = 6.5
    epicenter_x: float = 0.0
    epicenter_y: float = 0.3
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


@app.get("/api/city/layout")
async def get_layout():
    """Returns deterministic geography, roads, dam, bridges, structures, trees and sensors."""
    return get_city_layout()


@app.get("/api/fleet/snapshot")
async def get_snapshot():
    if not fleet_manager:
        return {"error": "Fleet manager not initialized"}
    snapshot = fleet_manager.get_fleet_snapshot()
    snapshot["cluster"] = cluster_model.tick(snapshot.get("current_rps", 0.0), dt=0.1)
    if scenario_controller:
        snapshot["scenario"] = scenario_controller.get_status()
    return snapshot


@app.post("/api/scenario/earthquake")
async def trigger_earthquake(req: EarthquakeRequest):
    if fleet_manager:
        event = fleet_manager.trigger_earthquake(
            magnitude=req.magnitude,
            epicenter_km=(req.epicenter_x, req.epicenter_y),
            duration_s=req.duration_s,
        )
        return {
            "status": "triggered",
            "magnitude": req.magnitude,
            "epicenter": [req.epicenter_x, req.epicenter_y],
            "start_time_s": event.start_time_s,
            "duration_s": event.duration_s,
        }
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
    # Default subscription to downtown landmark tower sensor
    active_client_subscriptions[websocket] = "node-001"
    try:
        while True:
            text = await websocket.receive_text()
            try:
                msg = json.loads(text)
                if msg.get("type") == "select" and "node_id" in msg:
                    active_client_subscriptions[websocket] = str(msg["node_id"])
            except Exception:
                pass
    except WebSocketDisconnect:
        active_client_subscriptions.pop(websocket, None)
    except Exception:
        active_client_subscriptions.pop(websocket, None)


async def broadcast_telemetry_loop():
    """
    Combined broadcast loop:
    - Runs at 10 Hz (dt = 0.1s)
    - Updates ClusterModel HPA state
    - Streams live tri-axial seismograph waveforms for each client's selected station
    - Sends full fleet & cluster snapshot every 5 ticks (2 Hz)
    """
    tick_counter = 0
    while True:
        try:
            if fleet_manager:
                sim_time = time.time() - fleet_manager.sim_start_time
                current_rps = fleet_manager.stats.get("current_rps", 0.0)

                # Tick cluster autoscaling model
                cluster_state = cluster_model.tick(current_rps=current_rps, dt=0.1)

                if active_client_subscriptions:
                    # 1. Seismograph Wave Stream (10 Hz)
                    for ws, node_id in list(active_client_subscriptions.items()):
                        node = fleet_manager.nodes.get(node_id)
                        if not node:
                            node = fleet_manager.nodes.get("node-001")

                        if node:
                            # Generate 100ms window (100 samples) and decimate by 5 -> 20 points
                            x_arr, y_arr, z_arr, peak_g, _ = node.generator.generate_window(
                                start_sim_time_s=max(0.0, sim_time - 0.1),
                                sample_count=100,
                                active_event=fleet_manager.active_event,
                            )
                            wave_packet = {
                                "type": "wave",
                                "node_id": node.node_id,
                                "site": node.site,
                                "kind": node.kind,
                                "sector": node.sector,
                                "peak_g": round(float(peak_g), 4),
                                "x": [round(float(v), 4) for v in x_arr[::5]],
                                "y": [round(float(v), 4) for v in y_arr[::5]],
                                "z": [round(float(v), 4) for v in z_arr[::5]],
                            }
                            try:
                                await ws.send_text(json.dumps(wave_packet))
                            except Exception:
                                active_client_subscriptions.pop(ws, None)

                    # 2. Snapshot Packet (every 5th tick = 2 Hz)
                    tick_counter += 1
                    if tick_counter >= 5:
                        tick_counter = 0
                        snapshot = fleet_manager.get_fleet_snapshot()
                        snapshot["cluster"] = cluster_state
                        if scenario_controller:
                            snapshot["scenario"] = scenario_controller.get_status()

                        snap_msg = json.dumps({"type": "snapshot", "data": snapshot})
                        for ws in list(active_client_subscriptions.keys()):
                            try:
                                await ws.send_text(snap_msg)
                            except Exception:
                                active_client_subscriptions.pop(ws, None)

        except Exception as e:
            logger.error("Error in websocket broadcast: %s", e)

        await asyncio.sleep(0.1)


# Static assets
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(str(static_dir / "index.html"))
