"""
Scenario Controller (Task L7)

Reads declarative YAML timelines (quakes, telecommunications outages, aftershocks)
and dynamically drives the fleet manager's event injection.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml

from simulator.fleet_manager import FleetManager

logger = logging.getLogger(__name__)


class ScenarioController:
    """Executes timed scenario scripts against a FleetManager."""

    def __init__(self, fleet_manager: FleetManager, scenario_path: Optional[str] = None):
        self.fleet = fleet_manager
        self.scenario_path = scenario_path
        self.timeline: List[Dict[str, Any]] = []
        self.scenario_name: str = "Manual Controller"
        self.scenario_description: str = ""

        self.is_running: bool = False
        self.start_time: float = 0.0
        self.current_step_index: int = 0
        self._runner_task: Optional[asyncio.Task] = None

        if scenario_path:
            self.load_scenario(scenario_path)

    def load_scenario(self, path_str: str):
        """Loads and parses a YAML scenario file."""
        path = Path(path_str)
        if not path.is_file():
            raise FileNotFoundError(f"Scenario file not found: {path_str}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self.scenario_name = data.get("name", "Unnamed Scenario")
        self.scenario_description = data.get("description", "")
        self.timeline = sorted(data.get("timeline", []), key=lambda step: step.get("at_seconds", 0))
        self.current_step_index = 0
        logger.info("Loaded scenario '%s' with %d steps", self.scenario_name, len(self.timeline))

    async def execute_step(self, step: Dict[str, Any]):
        """Executes a single declarative action."""
        action = step.get("action")
        desc = step.get("description", action)
        logger.info("Executing Scenario Action: %s", desc)

        if action == "scale_fleet":
            nodes = step.get("target_nodes", 500)
            self.fleet.set_target_fleet_size(nodes)

        elif action == "trigger_earthquake":
            mag = float(step.get("magnitude", 5.0))
            epi = tuple(step.get("epicenter_km", [0.0, 0.0]))
            dur = float(step.get("duration_s", 30.0))
            self.fleet.trigger_earthquake(mag, epi, dur)

        elif action == "clear_earthquake":
            self.fleet.clear_active_event()

        elif action == "sever_network":
            sector = step.get("sector", "B")
            self.fleet.set_sector_network(sector, online=False)

        elif action == "restore_network":
            sector = step.get("sector", "B")
            self.fleet.set_sector_network(sector, online=True)

        elif action == "set_jitter":
            enabled = bool(step.get("enabled", True))
            self.fleet.set_global_jitter(enabled)

    async def run(self):
        """Asynchronously plays the scenario timeline."""
        if not self.timeline:
            logger.warning("No timeline loaded in ScenarioController.")
            return

        self.is_running = True
        self.start_time = time.time()
        self.current_step_index = 0

        try:
            while self.is_running and self.current_step_index < len(self.timeline):
                now = time.time()
                elapsed = now - self.start_time
                next_step = self.timeline[self.current_step_index]
                at_seconds = next_step.get("at_seconds", 0)

                if elapsed >= at_seconds:
                    await self.execute_step(next_step)
                    self.current_step_index += 1
                else:
                    sleep_time = min(1.0, at_seconds - elapsed)
                    await asyncio.sleep(sleep_time)

            logger.info("Scenario '%s' completed successfully.", self.scenario_name)
        except asyncio.CancelledError:
            logger.info("Scenario playback cancelled.")
        finally:
            self.is_running = False

    def start(self):
        """Starts background scenario playback."""
        if not self._runner_task or self._runner_task.done():
            self._runner_task = asyncio.create_task(self.run())

    def stop(self):
        """Stops scenario playback."""
        self.is_running = False
        if self._runner_task and not self._runner_task.done():
            self._runner_task.cancel()

    def get_status(self) -> Dict[str, Any]:
        """Provides status for web dashboard."""
        elapsed = time.time() - self.start_time if self.is_running else 0.0
        return {
            "name": self.scenario_name,
            "is_running": self.is_running,
            "elapsed_seconds": round(elapsed, 1),
            "current_step_index": self.current_step_index,
            "total_steps": len(self.timeline),
            "timeline": self.timeline,
        }
