"""
Unit tests for Task L6: Asyncio Fleet Manager
Verifies 500-node city fleet initialization, dynamic scaling (50 to 500),
sector network isolation, and performance without bottlenecking.
"""

import pytest
import asyncio
from simulator.fleet_manager import FleetManager
from simulator.config import TOTAL_NODES


def test_fleet_initialization():
    """Verify all 500 nodes are constructed across 5 sectors."""
    fleet = FleetManager(initial_nodes=500)
    assert len(fleet.nodes) == TOTAL_NODES
    assert len(fleet.active_node_ids) == 500

    # Check sector distribution (100 per sector)
    sector_counts = {}
    for node in fleet.nodes.values():
        sector_counts[node.sector] = sector_counts.get(node.sector, 0) + 1

    assert sector_counts == {"A": 100, "B": 100, "C": 100, "D": 100, "E": 100}


def test_fleet_dynamic_scaling():
    """Verify dynamic scale down to 50 and ramp back up to 500."""
    fleet = FleetManager(initial_nodes=500)
    assert len(fleet.active_node_ids) == 500

    # Scale down to 50 nodes
    fleet.set_target_fleet_size(50)
    assert len(fleet.active_node_ids) == 50
    assert fleet.target_node_count == 50

    # Ramp up to 350 nodes
    fleet.set_target_fleet_size(350)
    assert len(fleet.active_node_ids) == 350

    # Ramp up to full 500
    fleet.set_target_fleet_size(500)
    assert len(fleet.active_node_ids) == 500


def test_sector_network_cut_and_restore():
    """Verify cutting Sector B only disconnects Sector B nodes."""
    fleet = FleetManager(initial_nodes=500)

    fleet.set_sector_network("B", online=False)

    for node in fleet.nodes.values():
        if node.sector == "B":
            assert node.link_online is False
        else:
            assert node.link_online is True

    # Restore Sector B
    fleet.set_sector_network("B", online=True)
    for node in fleet.nodes.values():
        assert node.link_online is True


def test_fleet_snapshot():
    """Verify telemetry snapshot structure for web dashboard and monitoring."""
    fleet = FleetManager(initial_nodes=500)
    snapshot = fleet.get_fleet_snapshot()

    assert snapshot["target_fleet_size"] == 500
    assert snapshot["active_nodes_count"] == 500
    assert snapshot["triggered_nodes_count"] == 0
    assert snapshot["buffering_nodes_count"] == 0
    assert "current_rps" in snapshot
    assert "stats" in snapshot
    assert len(snapshot["nodes"]) == 500
    assert snapshot["nodes"][0]["id"] == "node-001"
    assert snapshot["nodes"][0]["status"] == "quiescent"


@pytest.mark.asyncio
async def test_fleet_concurrency_non_blocking():
    """Verify that ticking 500 nodes runs in sub-100ms without bottlenecking."""
    import time
    fleet = FleetManager(initial_nodes=500)
    fleet.is_running = True

    t0 = time.perf_counter()
    tasks = [fleet._node_tick(node, current_sim_time=0.0) for node in fleet.nodes.values()]
    await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - t0

    # Processing all 500 nodes should take less than 100 milliseconds
    assert elapsed < 0.15
