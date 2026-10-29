"""
Asyncio Fleet Manager (Task L6)

Manages a metropolitan fleet of up to 500 virtual seismic sensor nodes:
- Geographic layout across Sectors A through E.
- Dynamic fleet scaling: smoothly ramp from 50 to 500 nodes.
- Chronological physical wave propagation:
  - P-wave (2.8 km/s): sensors turn AMBER ("detecting") in distance order.
  - S-wave (1.5 km/s trailing): sensors turn RED ("shaking / triggered") and burst-fire to AKS.
  - Stations where local PGA < 0.05g transition back to GREEN ("quiescent").
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
        self._waveform_node_ids: set = set()

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
            "detecting_nodes": 0,
            "buffering_nodes": 0,
        }
        self._recent_requests_window: List[float] = []
        self._recent_backfill_window: List[float] = []
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

        all_ids = list(self.nodes.keys())
        self.active_node_ids = set(all_ids[: self.target_node_count])

    def set_target_fleet_size(self, target: int):
        """Scale active fleet dynamically between 50 and 500 nodes."""
        target = min(TOTAL_NODES, max(10, target))
        self.target_node_count = target
        all_ids = list(self.nodes.keys())

        if len(self.active_node_ids) < target:
            inactive = [nid for nid in all_ids if nid not in self.active_node_ids]
            to_add = inactive[: target - len(self.active_node_ids)]
            self.active_node_ids.update(to_add)
            logger.info("Fleet scaled up to %d nodes (+%d joined)", len(self.active_node_ids), len(to_add))
        elif len(self.active_node_ids) > target:
            to_remove_count = len(self.active_node_ids) - target
            active_list = list(self.active_node_ids)
            to_remove = set(random.sample(active_list, to_remove_count))
            self.active_node_ids.difference_update(to_remove)
            for nid in to_remove:
                self.nodes[nid].is_triggered = False
                self.nodes[nid].is_detecting = False
            logger.info("Fleet scaled down to %d nodes (-%d left)", len(self.active_node_ids), len(to_remove))

    def trigger_earthquake(
        self,
        magnitude: float,
        epicenter_km: Tuple[float, float],
        duration_s: float = 300.0,
        early_warning_delay_s: float = 15.0,
    ) -> SeismicEvent:
        """
        Initiate an earthquake propagating physically outward:
        P-wave arrives first (nodes turn Amber), S-wave follows (nodes turn Red).
        """
        for node in self.nodes.values():
            node.is_triggered = False
            node.is_detecting = False
        self._waveform_node_ids.clear()

        effective_duration = max(300.0, duration_s)
        sim_time = time.time() - self.sim_start_time
        self.active_event = SeismicEvent(
            magnitude=magnitude,
            epicenter_km=epicenter_km,
            start_time_s=sim_time,
            duration_s=effective_duration,
            early_warning_delay_s=early_warning_delay_s,
        )
        logger.info(
            "Seismic rupture initiated: M%.1f at (%.1f, %.1f)km, duration=%.1fs, trigger_radius=%.1fkm",
            magnitude,
            epicenter_km[0],
            epicenter_km[1],
            effective_duration,
            self.active_event.trigger_radius_km,
        )
        return self.active_event

    def clear_active_event(self):
        """Immediately ends active seismic shaking and returns fleet to quiescent baseline."""
        self.active_event = None
        self._waveform_node_ids.clear()
        for node in self.nodes.values():
            node.is_triggered = False
            node.is_detecting = False
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
        self._update_rps()
        sim_now = round(time.time() - self.sim_start_time, 2)

        ev = self.active_event
        early_warning_rem = 0.0
        is_early_warning = False
        if ev is not None:
            early_warning_rem = round(max(0.0, ev.impact_time_s - sim_now), 1)
            is_early_warning = early_warning_rem > 0.0

        triggered_count = sum(
            1 for nid in self.active_node_ids
            if self.nodes[nid].is_triggered and self.nodes[nid].link_online
        )
        detecting_count = sum(
            1 for nid in self.active_node_ids
            if self.nodes[nid].is_detecting and not self.nodes[nid].is_triggered and self.nodes[nid].link_online
        )
        quiescent_count = sum(
            1 for nid in self.active_node_ids
            if not self.nodes[nid].is_triggered and not self.nodes[nid].is_detecting and self.nodes[nid].link_online
        )
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
                elif node.is_detecting:
                    status = "detecting"
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

        return {
            "sim_time_s": sim_now,
            "ingest_url": self.ingest_url,
            "target_fleet_size": self.target_node_count,
            "active_nodes_count": len(self.active_node_ids),
            "triggered_nodes_count": triggered_count,
            "detecting_nodes_count": detecting_count,
            "quiescent_nodes_count": quiescent_count,
            "buffering_nodes_count": buffering_count,
            "total_buffered_batches": total_buffered,
            "current_rps": round(self.stats["current_rps"], 1),
            "backfill_rps": round(len(self._recent_backfill_window) / 2.0, 1),
            "stats": self.stats,
            "jitter_enabled": self.jitter_enabled,
            "has_active_event": ev is not None,
            "active_event": {
                "magnitude": ev.magnitude,
                "epicenter": ev.epicenter_km,
                "start_time_s": ev.start_time_s,
                "impact_time_s": ev.impact_time_s,
                "early_warning_delay_s": ev.early_warning_delay_s,
                "early_warning_remaining_s": early_warning_rem,
                "is_early_warning": is_early_warning,
                "duration_s": ev.duration_s,
                "trigger_radius_km": ev.trigger_radius_km,
                "p_velocity_km_s": ev.p_velocity_km_s,
                "s_velocity_km_s": ev.s_velocity_km_s,
            } if ev else None,
            "latest_waveform": self._latest_waveform_samples[-60:] if self._latest_waveform_samples else [],
            "nodes": nodes_summary,
        }

    async def _node_waveform_loop(self, node: VirtualSensorNode, event_end_s: float):
        """Emits raw waveform bursts to Azure AKS while the S-wave is shaking this station."""
        try:
            while self.is_running and node.node_id in self.active_node_ids and self.active_event is not None:
                sim_time = time.time() - self.sim_start_time
                if sim_time > event_end_s:
                    node.is_triggered = False
                    node.is_detecting = False
                    break

                node.is_triggered = True
                node.is_detecting = False

                batch, _ = node.generate_waveform_batch(sim_time, self.active_event)
                if batch.waveform and batch.waveform.samples:
                    self._latest_waveform_samples = [s.z for s in batch.waveform.samples[-40:]]

                if self.session:
                    res = await node.emit_batch(self.session, batch, self.ingest_url)
                    self._record_result(res, is_waveform=True)

                await asyncio.sleep(0.40)
        finally:
            node.is_triggered = False
            node.is_detecting = False
            self._waveform_node_ids.discard(node.node_id)

    async def _node_tick(self, node: VirtualSensorNode, current_sim_time: float):
        """Periodic tick evaluating physical wave arrival and summary emission."""
        if not self.is_running or node.node_id not in self.active_node_ids:
            return

        # 1. Seismic wave propagation evaluation
        if self.active_event is not None:
            ev = self.active_event
            epi_dist = node.generator.calculate_distance_km(ev.epicenter_km)
            t_p = ev.start_time_s + (epi_dist / ev.p_velocity_km_s)
            t_s = ev.impact_time_s + (epi_dist / ev.s_velocity_km_s)
            local_pga = ev.local_pga_at_distance(epi_dist, node.soil_amplification)
            event_end = t_s + ev.duration_s

            if current_sim_time < t_p:
                # Wave has not reached this sensor yet: Quiescent (Green)
                node.is_detecting = False
                node.is_triggered = False

            elif t_p <= current_sim_time < t_s:
                # P-wave has arrived! Precursor micro-tremor detection: Amber
                node.is_detecting = True
                node.is_triggered = False

            elif t_s <= current_sim_time <= event_end:
                # S-wave has arrived!
                node.is_detecting = False
                if local_pga >= SEISMIC_TRIGGER_THRESHOLD_G:
                    # Shaking exceeds 0.05g -> Station triggers into RED burst mode
                    node.is_triggered = True
                    if node.node_id not in self._waveform_node_ids:
                        self._waveform_node_ids.add(node.node_id)
                        asyncio.create_task(self._node_waveform_loop(node, event_end))
                        return
                else:
                    # Distant / minor tremor below trigger threshold -> settles back to Green
                    node.is_triggered = False

            else:
                # Event ended at this station
                node.is_detecting = False
                node.is_triggered = False

        # 2. Quiescent Summary Mode (when station is not bursting waveforms)
        if not node.is_triggered:
            offset = node.jitter_offset_s if node.jitter_enabled else 0.0
            second_in_cycle = (current_sim_time + offset) % 60.0

            if second_in_cycle < 1.0:
                batch = node.generate_summary_batch(current_sim_time)
                if self.session:
                    res = await node.emit_batch(self.session, batch, self.ingest_url)
                    self._record_result(res, is_waveform=False)

        # 3. Flushes any pending backfill if reconnected
        if node.link_online and node.offline_buffer and self.session:
            flushed = await node.flush_backlog(self.session, self.ingest_url, max_batches=10)
            if flushed > 0:
                now = time.time()
                self.stats["backfill_sent"] += flushed
                self.stats["total_sent"] += flushed
                for _ in range(flushed):
                    self._recent_requests_window.append(now)
                    self._recent_backfill_window.append(now)

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
        cutoff = now - 2.0
        self._recent_requests_window = [t for t in self._recent_requests_window if t >= cutoff]
        self._recent_backfill_window = [t for t in self._recent_backfill_window if t >= cutoff]
        self.stats["current_rps"] = len(self._recent_requests_window) / 2.0

    async def run(self):
        """Main async orchestration loop."""
        self.is_running = True
        self.sim_start_time = time.time()

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

                if self.active_event:
                    ev = self.active_event
                    max_event_end = ev.impact_time_s + (48.0 / ev.s_velocity_km_s) + ev.duration_s + 2.0
                    if sim_time > max_event_end:
                        logger.info("Earthquake wave propagation completed. Returning fleet to quiescent baseline.")
                        self.clear_active_event()

                active_nodes = [self.nodes[nid] for nid in list(self.active_node_ids)]
                tasks = [self._node_tick(node, sim_time) for node in active_nodes]
                await asyncio.gather(*tasks, return_exceptions=True)

                await asyncio.sleep(0.4)

    def stop(self):
        """Stop the fleet manager runner."""
        self.is_running = False
        if self._fleet_task:
            self._fleet_task.cancel()
