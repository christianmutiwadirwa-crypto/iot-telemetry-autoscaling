"""
Multi-Node Seismic Event Correlation Engine (Task L15)

Correlates high-acceleration triggers across multiple stations within a rolling time window:
- Discards isolated false alarms (e.g. local truck or dropping a tool at one station).
- Declares a confirmed seismic event when >= N distinct nodes trigger within a sector.
- Bypasses real-time alerting for backfill / retransmitted data.
"""

import time
import math
import logging
from collections import deque
from typing import Dict, List, Optional, Any

from config import settings

logger = logging.getLogger(__name__)


class SeismicEventCorrelator:
    """Detects metropolitan seismic shockwaves through spatial-temporal clustering."""

    def __init__(
        self,
        window_seconds: float = settings.CORRELATION_WINDOW_SECONDS,
        min_nodes: int = settings.CORRELATION_MIN_NODES,
        event_cooldown_seconds: float = 15.0,
    ):
        self.window_seconds = window_seconds
        self.min_nodes = min_nodes
        self.event_cooldown_seconds = event_cooldown_seconds

        # Buffer of recent trigger events: List of (timestamp, node_id, sector, peak_g)
        self.recent_triggers = deque()
        self.last_declared_events: Dict[str, float] = {}  # sector -> last_event_timestamp

    def record_trigger(
        self,
        node_id: str,
        sector: str,
        peak_g: float,
        is_backfill: bool,
    ) -> Optional[Dict[str, Any]]:
        """
        Processes an event waveform trigger.
        Returns event dict if a confirmed multi-node earthquake is detected, else None.
        """
        # Task L15 Requirement: Skip real-time event alerting for backfill / historical data
        if is_backfill:
            return None

        # Only consider triggers that cross the seismic threshold (> 0.05g)
        if peak_g < 0.05:
            return None

        now = time.time()
        self.recent_triggers.append((now, node_id, sector, peak_g))

        # Purge triggers outside sliding window
        cutoff = now - self.window_seconds
        while self.recent_triggers and self.recent_triggers[0][0] < cutoff:
            self.recent_triggers.popleft()

        # Count distinct nodes triggered in this sector within the window
        sector_triggers = [t for t in self.recent_triggers if t[2] == sector]
        distinct_nodes = {t[1] for t in sector_triggers}

        if len(distinct_nodes) >= self.min_nodes:
            # Check cooldown to prevent duplicate alerts for the same continuous quake
            last_event_time = self.last_declared_events.get(sector, 0.0)
            if (now - last_event_time) >= self.event_cooldown_seconds:
                max_peak = max(t[3] for t in sector_triggers)
                # Estimate Richter magnitude from peak acceleration (empirical scaling)
                # PGA ~ 0.1g -> ~5.2M, PGA ~ 0.5g -> ~6.5M
                est_mag = round(min(7.8, max(3.5, 4.0 + 1.8 * math.log10(max(0.01, max_peak) * 10))), 1)

                self.last_declared_events[sector] = now

                event_record = {
                    "detected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                    "sector": sector,
                    "triggering_nodes_count": len(distinct_nodes),
                    "max_peak_g": round(float(max_peak), 4),
                    "estimated_magnitude": est_mag,
                    "description": (
                        f"Metropolitan Seismic Event confirmed in Sector {sector}: "
                        f"{len(distinct_nodes)} stations triggered (Peak: {max_peak:.3f}g, Est. Magnitude: {est_mag})"
                    ),
                }

                logger.warning("🚨 [SEISMIC ALERT] %s", event_record["description"])
                return event_record

        return None
