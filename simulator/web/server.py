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
    duration_s: float = 300.0


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
    snapshot["cluster"] = cluster_model.tick(
        current_rps=snapshot.get("current_rps", 0.0),
        dt=0.1,
        triggered_nodes=snapshot.get("triggered_nodes_count", 0),
        backfill_rps=snapshot.get("backfill_rps", 0.0),
    )
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
            early_warning_delay_s=15.0,
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
                fleet_manager._update_rps()
                current_rps = fleet_manager.stats.get("current_rps", 0.0)
                triggered_online = sum(
                    1 for nid in fleet_manager.active_node_ids
                    if fleet_manager.nodes[nid].is_triggered and fleet_manager.nodes[nid].link_online
                )
                backfill_rps = len(fleet_manager._recent_backfill_window) / 2.0

                # Tick cluster autoscaling model
                cluster_state = cluster_model.tick(
                    current_rps=current_rps,
                    dt=0.1,
                    triggered_nodes=triggered_online,
                    backfill_rps=backfill_rps,
                )

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


def _fetch_aks_json():
    import subprocess
    try:
        out = subprocess.check_output(
            ["kubectl", "--kubeconfig=.azure/kubeconfig", "get", "hpa,pods", "-n", "telemetry", "-o", "json"],
            timeout=4.0,
            stderr=subprocess.DEVNULL
        )
        return json.loads(out.decode())
    except Exception:
        return None

def _fetch_rabbitmq_queue_depth():
    import subprocess
    try:
        out = subprocess.check_output(
            ["kubectl", "--kubeconfig=.azure/kubeconfig", "exec", "-n", "telemetry", "rabbitmq-0",
             "--", "rabbitmqctl", "list_queues", "-q", "name", "messages"],
            timeout=4.0,
            stderr=subprocess.DEVNULL
        )
        total_q = 0
        for line in out.decode().splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].isdigit():
                # Only count active in-flight queues, exclude dead-letter backlog
                if parts[0] in ("telemetry.live", "telemetry.backfill"):
                    total_q += int(parts[1])
        return total_q
    except Exception:
        return None

async def sync_live_aks_loop():
    """Periodically queries Azure AKS HPA, Pods, and Ingest API to faithfully mirror real cloud metrics."""
    import re
    import time
    last_ingest_count = None
    last_ingest_time = None
    queue_check_counter = 0
    cached_queue_depth = 0

    while True:
        try:
            kubeconfig = Path(".azure/kubeconfig")
            if kubeconfig.exists():
                # 1. Query real HPA and Pods JSON from AKS via thread pool
                data = await asyncio.to_thread(_fetch_aks_json)
                if data:
                    items = data.get("items", [])
                    hpas = [i for i in items if i.get("kind") == "HorizontalPodAutoscaler"]
                    pods = [i for i in items if i.get("kind") == "Pod"]

                    # 1. Parse HPAs
                    ingest_hpa = next((h for h in hpas if "ingest-api" in h.get("metadata", {}).get("name", "")), None)
                    processor_hpa = next((h for h in hpas if "processor" in h.get("metadata", {}).get("name", "")), None)

                    def get_hpa_cpu(h):
                        if not h: return None
                        for m in h.get("status", {}).get("currentMetrics", []):
                            u = m.get("resource", {}).get("current", {}).get("averageUtilization")
                            if u is not None: return float(u)
                        return None

                    ingest_cpu = get_hpa_cpu(ingest_hpa)
                    proc_cpu = get_hpa_cpu(processor_hpa)

                    # 2. Parse Pods
                    all_ingest_pods = [
                        p for p in pods 
                        if p.get("metadata", {}).get("labels", {}).get("app") == "ingest-api"
                        and p.get("status", {}).get("phase") in ("Running", "Pending")
                    ]
                    all_proc_pods = [
                        p for p in pods 
                        if p.get("metadata", {}).get("labels", {}).get("app") == "processor"
                        and p.get("status", {}).get("phase") in ("Running", "Pending")
                    ]

                    ingest_ready_cnt = sum(
                        1 for p in all_ingest_pods 
                        if any(c.get("type") == "Ready" and c.get("status") == "True" for c in p.get("status", {}).get("conditions", []))
                    )
                    proc_ready_cnt = sum(
                        1 for p in all_proc_pods 
                        if any(c.get("type") == "Ready" and c.get("status") == "True" for c in p.get("status", {}).get("conditions", []))
                    )

                    ingest_cur = ingest_hpa.get("status", {}).get("currentReplicas", len(all_ingest_pods)) if ingest_hpa else len(all_ingest_pods)
                    ingest_des = ingest_hpa.get("status", {}).get("desiredReplicas", ingest_cur) if ingest_hpa else ingest_cur
                    ingest_replicas = max(ingest_des, ingest_cur, len(all_ingest_pods), 2)
                    ingest_ready = max(1, min(ingest_ready_cnt, ingest_replicas))
                    ingest_starting = max(0, ingest_replicas - ingest_ready)

                    proc_cur = processor_hpa.get("status", {}).get("currentReplicas", len(all_proc_pods)) if processor_hpa else len(all_proc_pods)
                    proc_des = processor_hpa.get("status", {}).get("desiredReplicas", proc_cur) if processor_hpa else proc_cur
                    proc_replicas = max(proc_des, proc_cur, len(all_proc_pods), 2)
                    proc_ready = max(1, min(proc_ready_cnt, proc_replicas))
                    proc_starting = max(0, proc_replicas - proc_ready)

                    ingest_stats = {
                        "replicas": ingest_replicas,
                        "ready_pods": ingest_ready,
                        "starting_pods": ingest_starting,
                        "cpu_percent": ingest_cpu or 4.0,
                    }
                    processor_stats = {
                        "replicas": proc_replicas,
                        "ready_pods": proc_ready,
                        "starting_pods": proc_starting,
                        "cpu_percent": proc_cpu or 4.0,
                    }

                    # Overall cluster metrics
                    live_replicas = max(ingest_replicas, proc_replicas)
                    live_ready = max(ingest_ready, proc_ready)
                    max_cpu = max(ingest_cpu or 0.0, proc_cpu or 0.0)

                    # 3. Check RabbitMQ queue depth periodically
                    queue_check_counter += 1
                    if queue_check_counter >= 3:
                        queue_check_counter = 0
                        q_val = await asyncio.to_thread(_fetch_rabbitmq_queue_depth)
                        if q_val is not None:
                            cached_queue_depth = q_val

                    # 4. Query Real Ingestion Rate from Azure Ingest API /metrics
                    real_writes_sec = None
                    try:
                        import aiohttp
                        async with aiohttp.ClientSession() as s:
                            async with s.get("http://20.239.8.235:8000/metrics", timeout=aiohttp.ClientTimeout(total=2.0)) as m_resp:
                                if m_resp.status == 200:
                                    m_text = await m_resp.text()
                                    total_ingest = 0
                                    for line in m_text.splitlines():
                                        if line.startswith("telemetry_ingest_requests_total"):
                                            m_parts = line.split()
                                            if len(m_parts) >= 2:
                                                try:
                                                    total_ingest += float(m_parts[1])
                                                except ValueError:
                                                    pass
                                    now_t = time.time()
                                    if last_ingest_count is not None and last_ingest_time is not None:
                                        dt = max(0.5, now_t - last_ingest_time)
                                        real_writes_sec = max(0, int((total_ingest - last_ingest_count) / dt))
                                    last_ingest_count = total_ingest
                                    last_ingest_time = now_t
                    except Exception:
                        pass

                    cluster_model.update_live_cluster(
                        replicas=live_replicas,
                        ready_pods=live_ready,
                        cpu_percent=max_cpu,
                        queue_depth=cached_queue_depth,
                        db_writes_per_sec=real_writes_sec,
                        ingest_stats=ingest_stats,
                        processor_stats=processor_stats,
                    )
        except Exception:
            pass
        await asyncio.sleep(1.5)


# Static assets
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(str(static_dir / "index.html"))
