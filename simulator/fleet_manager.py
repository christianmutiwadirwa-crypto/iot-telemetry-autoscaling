"""
Asyncio Fleet Manager (Task L6)

Manages a metropolitan fleet of up to 500 virtual seismic sensor nodes:
- Geographic layout across Sectors A through E.
- Dynamic fleet scaling: smoothly ramp from 50 to 500 nodes with random joins and leaves.
- High-concurrency client connection pooling (aiohttp TCPConnector) to ensure the 
  simulator laptop is never the bottleneck.
- Event injection: trigger earthquakes, cut sector network links, restore with backfill flush.
- Real-time aggregated fleet statistics (req/sec, active triggered nodes, queue depth, error rates).
"""

import asyncio
import logging
import math
import random
import time
from typing import Dict, List, Optional, Tuple, Any

import aiohttp

from simulator.config import (
    DEFAULT_API_KEY,
    DEFAULT_INGEST_URL,
    SECTOR_INFO,
    TOTAL_NODES,
    SEISMIC_TRIGGER_THRESHOLD_G,
)
from simulator.virtual_device import VirtualSensorNode
from simulator.waveform_generator import SeismicEvent
from simulator.city_layout import get_city_layout

logger = logging.getLogger(__name__)


class FleetManager:
    """Orchestrates 50 to 500 virtual seismic stations concurrently via asyncio."""

    def __init__(
        self,
        ingest_url: str = DEFAULT_INGEST_URL,
        api_key: str = DEFAULT_API_KEY,
        initial_nodes: int = 500,
        jitter_enabled: bool = True,
    ):
        self.ingest_url = ingest_url
        self.api_key = api_key
        self.target_node_count = min(TOTAL_NODES, max(10, initial_nodes))
        self.jitter_enabled = jitter_enabled

        self.nodes: Dict[str, VirtualSensorNode] = {}
        self.active_node_ids: set = set()

        # Active earthquake event
        self.active_event: Optional[SeismicEvent] = None
        self.sim_start_time = time.time()

        # Concurrency & lifecycle
        self.session: Optional[aiohttp.ClientSession] = None
        self.is_running: bool = False
        self._fleet_task: Optional[asyncio.Task] = None

        # Fleet statistics counters
        self.stats = {
            "total_sent": 0,
            "summaries_sent": 0,
            "waveforms_sent": 0,
            "backfill_sent": 0,
            "rate_limited_429": 0,
            "errors": 0,
            "current_rps": 0.0,
            "active_nodes": 0,
            "triggered_nodes": 0,
            "buffering_nodes": 0,
        }
        self._recent_requests_window: List[float] = []
        self._latest_waveform_samples: List[float] = []

        self._initialize_nodes()

    def _initialize_nodes(self):
        """Constructs all 500 virtual stations mapped to city layout infrastructure."""
        layout = get_city_layout()
        for s in layout["sensors"]:
            node_id = s["id"]
            sector_id = s["sector"]
            amplification = SECTOR_INFO[sector_id]["soil_amplification"]

            node = VirtualSensorNode(
                node_id=node_id,
                sector=sector_id,
                coordinates_km=(s["x"], s["y"]),
                soil_amplification=amplification,
                api_key=self.api_key,
                jitter_enabled=self.jitter_enabled,
                kind=s.get("kind", "ground_station"),
                site=s.get("site", ""),
            )
            self.nodes[node_id] = node

        # Activate initial quota
        all_ids = list(self.nodes.keys())
        self.active_node_ids = set(all_ids[: self.target_node_count])

    def set_target_fleet_size(self, target: int):
        """Scale active fleet dynamically between 50 and 500 nodes."""
        target = min(TOTAL_NODES, max(10, target))
        self.target_node_count = target
        all_ids = list(self.nodes.keys())

        if len(self.active_node_ids) < target:
            # Add nodes
            inactive = [nid for nid in all_ids if nid not in self.active_node_ids]
            to_add = inactive[: target - len(self.active_node_ids)]
            self.active_node_ids.update(to_add)
            logger.info("Fleet scaled up to %d nodes (+%d joined)", len(self.active_node_ids), len(to_add))
        elif len(self.active_node_ids) > target:
            # Remove nodes
            to_remove = random.sample(list(self.active_node_ids), len(self.active_node_ids) - target)
            self.active_node_ids.difference_update(to_remove)
            logger.info("Fleet scaled down to %d nodes (-%d left)", len(self.active_node_ids), len(to_remove))

    def trigger_earthquake(
        self,
        magnitude: float,
        epicenter_km: Tuple[float, float],
        duration_s: float = 45.0,
    ) -> SeismicEvent:
        """Initiate an earthquake shockwave propagating across the city."""
        sim_time = time.time() - self.sim_start_time
        self.active_event = SeismicEvent(
            magnitude=magnitude,
            epicenter_km=epicenter_km,
            start_time_s=sim_time,
            duration_s=duration_s,
        )
        logger.info(
            "Earthquake triggered: M%.1f at coords (%.1f, %.1f)km, duration %.1fs",
            magnitude,
            epicenter_km[0],
            epicenter_km[1],
            duration_s,
        )
        return self.active_event

    def clear_active_event(self):
        """Immediately ends active seismic shaking and returns fleet to quiescent baseline."""
        self.active_event = None
        for node in self.nodes.values():
            node.is_triggered = False
        logger.info("Seismic event cleared. Fleet returned to quiescent mode.")

    def set_sector_network(self, sector: str, online: bool):
        """Sever or restore cellular network connectivity for all stations in a sector."""
        for node in self.nodes.values():
            if node.sector == sector:
                node.set_link_state(online)

    def set_global_jitter(self, enabled: bool):
        """Enable or disable minute-boundary report jitter across all nodes."""
        self.jitter_enabled = enabled
        for node in self.nodes.values():
            node.set_jitter_mode(enabled)
        logger.info("Global jitter set to %s", enabled)

    def get_fleet_snapshot(self) -> Dict[str, Any]:
        """Provides status data for web dashboard and monitoring."""
        triggered_count = sum(1 for nid in self.active_node_ids if self.nodes[nid].is_triggered)
        buffering_count = sum(1 for nid in self.active_node_ids if not self.nodes[nid].link_online)
        total_buffered = sum(len(self.nodes[nid].offline_buffer) for nid in self.active_node_ids)

        nodes_summary = []
        for nid in sorted(self.nodes.keys()):
            node = self.nodes[nid]
            status = "inactive"
            if nid in self.active_node_ids:
                if not node.link_online:
                    status = "buffering"
                elif node.is_triggered:
                    status = "triggered"
                else:
                    status = "quiescent"

            nodes_summary.append({
                "id": node.node_id,
                "sector": node.sector,
                "status": status,
                "coords": node.coordinates_km,
                "buffer_len": len(node.offline_buffer),
                "kind": node.kind,
                "site": node.site,
            })

        sim_now = round(time.time() - self.sim_start_time, 2)
        return {
            "sim_time_s": sim_now,
            "ingest_url": self.ingest_url,
            "target_fleet_size": self.target_node_count,
            "active_nodes_count": len(self.active_node_ids),
            "triggered_nodes_count": triggered_count,
            "buffering_nodes_count": buffering_count,
            "total_buffered_batches": total_buffered,
            "current_rps": round(self.stats["current_rps"], 1),
            "stats": self.stats,
            "jitter_enabled": self.jitter_enabled,
            "has_active_event": self.active_event is not None,
            "active_event": {
                "magnitude": self.active_event.magnitude,
                "epicenter": self.active_event.epicenter_km,
                "start_time_s": self.active_event.start_time_s,
                "duration_s": self.active_event.duration_s,
            } if self.active_event else None,
            "latest_waveform": self._latest_waveform_samples[-60:] if self._latest_waveform_samples else [],
            "nodes": nodes_summary,
        }

    async def _node_waveform_loop(self, node: VirtualSensorNode):
        """Fast-rate loop running while node is triggered (10 batches/sec)."""
        while self.is_running and node.node_id in self.active_node_ids and node.is_triggered:
            if not self.active_event:
                node.is_triggered = False
                break
            sim_time = time.time() - self.sim_start_time
            if sim_time > (self.active_event.start_time_s + self.active_event.duration_s + 2.0):
                node.is_triggered = False
                break
            batch, peak_g = node.generate_waveform_batch(sim_time, self.active_event)
            if batch.waveform and batch.waveform.samples:
                self._latest_waveform_samples = [s.z for s in batch.waveform.samples[-40:]]
            
            if self.session:
                res = await node.emit_batch(self.session, batch, self.ingest_url)
                self._record_result(res, is_waveform=True)

            # 100ms interval = 10 req/s
            await asyncio.sleep(0.1)

    async def _node_tick(self, node: VirtualSensorNode, current_sim_time: float):
        """Periodic tick evaluating trigger state and summary emission."""
        if not self.is_running or node.node_id not in self.active_node_ids:
            return

        # 1. Check if node should trigger on seismic wave
        if self.active_event is not None and not node.is_triggered:
            epi_dist = node.generator.calculate_distance_km(self.active_event.epicenter_km)
            hypo_dist = math.sqrt(epi_dist ** 2 + self.active_event.depth_km ** 2)
            t_arrival_p = self.active_event.start_time_s + (hypo_dist / self.active_event.p_velocity_km_s)
            event_end = self.active_event.start_time_s + self.active_event.duration_s + 2.0

            if current_sim_time >= t_arrival_p and current_sim_time <= event_end:
                # Check if physical ground acceleration exceeds trigger threshold
                _, _, _, peak_g, _ = node.generator.generate_window(
                    start_sim_time_s=current_sim_time,
                    sample_count=100,
                    active_event=self.active_event,
                )
                if peak_g >= SEISMIC_TRIGGER_THRESHOLD_G:
                    node.is_triggered = True
                    asyncio.create_task(self._node_waveform_loop(node))
                    return

        # 2. Quiescent Summary Mode
        if not node.is_triggered:
            # Calculate interval with jitter
            offset = node.jitter_offset_s if node.jitter_enabled else 0.0
            second_in_cycle = (current_sim_time + offset) % 60.0

            # Emit summary packet within a 1-second slot of its 60s cycle
            if second_in_cycle < 1.0:
                batch = node.generate_summary_batch(current_sim_time)
                if self.session:
                    res = await node.emit_batch(self.session, batch, self.ingest_url)
                    self._record_result(res, is_waveform=False)

        # 3. Flushes any pending backfill if reconnected
        if node.link_online and node.offline_buffer and self.session:
            flushed = await node.flush_backlog(self.session, self.ingest_url, max_batches=10)
            if flushed > 0:
                self.stats["backfill_sent"] += flushed
                self.stats["total_sent"] += flushed

    def _record_result(self, res: Dict[str, Any], is_waveform: bool):
        """Updates internal fleet statistics counters."""
        now = time.time()
        self._recent_requests_window.append(now)

        status = res.get("status")
        if status in ("accepted", "buffered"):
            self.stats["total_sent"] += 1
            if is_waveform:
                self.stats["waveforms_sent"] += 1
            else:
                self.stats["summaries_sent"] += 1
        elif status == "rate_limited":
            self.stats["rate_limited_429"] += 1
        else:
            self.stats["errors"] += 1

    def _update_rps(self):
        """Calculates moving window requests per second."""
        now = time.time()
        # Keep only events from the last 2 seconds
        cutoff = now - 2.0
        self._recent_requests_window = [t for t in self._recent_requests_window if t >= cutoff]
        self.stats["current_rps"] = len(self._recent_requests_window) / 2.0

    async def run(self):
        """Main async orchestration loop."""
        self.is_running = True
        self.sim_start_time = time.time()

        # Create high-capacity TCP connector to avoid client-side connection starvation
        connector = aiohttp.TCPConnector(
            limit=1000,
            limit_per_host=1000,
            enable_cleanup_closed=True,
            ttl_dns_cache=300,
        )
        async with aiohttp.ClientSession(connector=connector) as session:
            self.session = session
            logger.info("Fleet Manager started with %d active nodes targeting %s", len(self.active_node_ids), self.ingest_url)

            while self.is_running:
                sim_time = time.time() - self.sim_start_time
                self._update_rps()

                # Auto-clear earthquake event after duration expires
                if self.active_event and sim_time > (self.active_event.start_time_s + self.active_event.duration_s + 2.0):
                    logger.info("Earthquake duration completed (%.1fs). Returning fleet to quiescent baseline.", self.active_event.duration_s)
                    self.clear_active_event()

                # Process all active nodes
                active_nodes = [self.nodes[nid] for nid in list(self.active_node_ids)]
                # Run ticks concurrently
                tasks = [self._node_tick(node, sim_time) for node in active_nodes]
                await asyncio.gather(*tasks, return_exceptions=True)

                await asyncio.sleep(1.0)

    def stop(self):
        """Stop the fleet manager runner."""
        self.is_running = False
        if self._fleet_task:
            self._fleet_task.cancel()
