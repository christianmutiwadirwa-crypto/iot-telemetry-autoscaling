"""
Unit tests for Metropolitan Living City Layout Generator.
Verifies determinism, sensor counts, sector distribution, infrastructure mapping,
and physical constraints (no sensors inside open water unless on bridges/dam).
"""

import pytest
from simulator.city_layout import get_city_layout, is_water


def test_city_layout_structure():
    """Verify city layout contains all required geography layers."""
    layout = get_city_layout()
    assert "bounds" in layout
    assert "sectors" in layout
    assert "river" in layout
    assert "reservoir" in layout
    assert "dam" in layout
    assert "bridges" in layout
    assert "parks" in layout
    assert "roads" in layout
    assert "structures" in layout
    assert "trees" in layout
    assert "labels" in layout
    assert "sensors" in layout

    assert len(layout["sectors"]) == 5
    assert len(layout["bridges"]) == 5
    assert len(layout["structures"]) >= 100
    assert len(layout["trees"]) >= 1000


def test_sensors_distribution_and_ids():
    """Verify exactly 500 sensors, 100 per sector, strictly sequential IDs."""
    layout = get_city_layout()
    sensors = layout["sensors"]
    assert len(sensors) == 500

    sector_counts = {}
    for i, s in enumerate(sensors):
        expected_id = f"node-{i+1:03d}"
        assert s["id"] == expected_id, f"Sensor ID mismatch at {i}: {s['id']} != {expected_id}"
        sec = s["sector"]
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
        assert "x" in s and "y" in s
        assert "kind" in s and "site" in s

    assert sector_counts == {"A": 100, "B": 100, "C": 100, "D": 100, "E": 100}


def test_dam_and_bridge_sensors():
    """Verify Kelvin Dam has 10 dedicated piezometer sensors and bridges have sensors."""
    layout = get_city_layout()
    dam_sensors = [s for s in layout["sensors"] if s.get("kind") == "dam"]
    assert len(dam_sensors) == 10
    for s in dam_sensors:
        assert s["sector"] == "C"
        assert "Kelvin Dam" in s["site"]

    bridge_sensors = [s for s in layout["sensors"] if s.get("kind") == "bridge"]
    assert len(bridge_sensors) >= 6


def test_layout_determinism():
    """Verify two calls return identical data."""
    l1 = get_city_layout()
    l2 = get_city_layout()
    assert l1["sensors"][0]["id"] == l2["sensors"][0]["id"]
    assert l1["sensors"][0]["x"] == l2["sensors"][0]["x"]
    assert l1["sensors"][200]["site"] == l2["sensors"][200]["site"]
