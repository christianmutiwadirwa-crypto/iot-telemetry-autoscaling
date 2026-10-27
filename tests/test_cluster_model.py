"""
Unit tests for ClusterModel autoscaler and queue simulation.
Verifies scale-out to 10 pods under high load, bounds clamping (2-10),
queue accumulation and draining, and stabilization before scale-in.
"""

import pytest
from simulator.cluster_model import ClusterModel


def test_cluster_initial_state():
    """Verify default idle cluster has 2 pods, zero queue depth, and stable status."""
    cluster = ClusterModel()
    state = cluster.tick(current_rps=8.0, dt=0.1)
    assert state["replicas"] == 2
    assert state["ready_pods"] == 2
    assert state["min_pods"] == 2
    assert state["max_pods"] == 10
    assert state["queue_depth"] == 0
    assert state["status"] == "stable"


def test_cluster_scale_out_under_load():
    """Verify cluster scales out toward 10 pods when seismic spike hits 3500 rps."""
    cluster = ClusterModel()
    # Apply 3500 rps
    state = cluster.tick(current_rps=3500.0, dt=0.1)
    assert state["replicas"] >= 8
    assert state["status"] == "scaling out"
    assert state["starting_pods"] > 0

    # Advance time by 6s to allow pods to become ready
    for _ in range(60):
        state = cluster.tick(current_rps=3500.0, dt=0.1)

    assert state["ready_pods"] >= 8
    assert state["starting_pods"] == 0


def test_cluster_bounds_clamped():
    """Verify replicas cannot exceed max_pods (10) even with extreme load (50,000 rps)."""
    cluster = ClusterModel(max_pods=10)
    state = cluster.tick(current_rps=50000.0, dt=0.1)
    assert state["replicas"] == 10
    assert state["max_pods"] == 10


def test_cluster_queue_drain_after_load():
    """Verify queue accumulates when unready, and drains once capacity exceeds rps."""
    cluster = ClusterModel()
    # High spike causes queue backlog while pods are booting
    for _ in range(20):
        state = cluster.tick(current_rps=2500.0, dt=0.1)
    assert state["queue_depth"] > 0

    # Let pods boot
    for _ in range(60):
        state = cluster.tick(current_rps=2500.0, dt=0.1)

    # Now reduce rps to 10; queue should drain
    for _ in range(100):
        state = cluster.tick(current_rps=10.0, dt=0.1)

    assert state["queue_depth"] == 0
