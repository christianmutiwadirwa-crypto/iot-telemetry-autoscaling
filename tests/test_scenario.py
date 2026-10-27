"""
Unit tests for Task L7: Scenario Controller
Verifies loading declarative YAML timeline and executing actions against FleetManager.
"""

import pytest
import asyncio
from pathlib import Path
from simulator.fleet_manager import FleetManager
from simulator.scenario_controller import ScenarioController


@pytest.fixture
def sample_scenario_file(tmp_path):
    yaml_content = """
name: "Test Fast Timeline"
timeline:
  - at_seconds: 0
    action: "scale_fleet"
    target_nodes: 50
    description: "Scale to 50"
  - at_seconds: 0
    action: "sever_network"
    sector: "C"
    description: "Cut Sector C"
  - at_seconds: 1
    action: "trigger_earthquake"
    magnitude: 6.2
    epicenter_km: [0.0, 0.0]
    duration_s: 10.0
    description: "Quake"
  - at_seconds: 1
    action: "restore_network"
    sector: "C"
    description: "Restore Sector C"
  - at_seconds: 2
    action: "clear_earthquake"
    description: "Clear"
"""
    file_path = tmp_path / "test_scenario.yaml"
    file_path.write_text(yaml_content, encoding="utf-8")
    return str(file_path)


def test_scenario_load(sample_scenario_file):
    fleet = FleetManager(initial_nodes=500)
    controller = ScenarioController(fleet, sample_scenario_file)

    assert controller.scenario_name == "Test Fast Timeline"
    assert len(controller.timeline) == 5
    status = controller.get_status()
    assert status["total_steps"] == 5
    assert status["current_step_index"] == 0


@pytest.mark.asyncio
async def test_scenario_execution(sample_scenario_file):
    fleet = FleetManager(initial_nodes=500)
    controller = ScenarioController(fleet, sample_scenario_file)

    # Execute step 0: scale_fleet
    await controller.execute_step(controller.timeline[0])
    assert len(fleet.active_node_ids) == 50

    # Execute step 1: sever_network Sector C
    await controller.execute_step(controller.timeline[1])
    assert fleet.nodes["node-201"].link_online is False

    # Execute step 2: trigger_earthquake
    await controller.execute_step(controller.timeline[2])
    assert fleet.active_event is not None
    assert fleet.active_event.magnitude == 6.2

    # Execute step 3: restore_network Sector C
    await controller.execute_step(controller.timeline[3])
    assert fleet.nodes["node-201"].link_online is True

    # Execute step 4: clear_earthquake
    await controller.execute_step(controller.timeline[4])
    assert fleet.active_event is None
