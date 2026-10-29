"""
City Layout Generator for Metropolitan Seismic Monitoring (Living City Map).
Deterministic procedural generator producing rich metropolitan geography:
- Bounds, Sectors A-E
- Water bodies: Kelvin Dam, Reservoir, Meandering River
- Infrastructure: 5 Bridges, Highways (H7 & Northern Expressway), Ring Roads, Arterials, Rail Network
- Districts & Structures:
  - Downtown (high-rises, towers, Central Station, civic center)
  - Industrial & Port (quays, gantry cranes, container yard, factories, tank farm, cooling towers)
  - Residential Hills (neighborhoods, hospital, school)
  - Transit & Retail (Meadow Mall, Kelvin Arena stadium, retail park, transit hub)
  - Suburbs (subdivisions, farm fields, substation, water tower)
- Natural areas: Central Park, Hillside Park, Riverside Gardens, Greenbelts, ~1,800 trees
- Exactly 500 sensors (100 per sector) attached to meaningful infrastructure and facilities.
"""

import math
import random
from typing import Dict, List, Any, Tuple
from simulator.config import SECTOR_INFO, TOTAL_NODES

# Singleton layout cache
_CACHED_LAYOUT: Dict[str, Any] = None


def distance_point_to_segment(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Euclidean distance from point (px, py) to line segment (x1, y1)-(x2, y2)."""
    dx = x2 - x1
    dy = y2 - y1
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0.0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg_len_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def is_in_reservoir(x: float, y: float, cx: float = -13.8, cy: float = 3.5, rx: float = 3.2, ry: float = 1.9, rot: float = -0.15) -> bool:
    """Check if point is within the elliptical reservoir."""
    cos_r = math.cos(-rot)
    sin_r = math.sin(-rot)
    dx = x - cx
    dy = y - cy
    x_rot = dx * cos_r - dy * sin_r
    y_rot = dx * sin_r + dy * cos_r
    return (x_rot / rx) ** 2 + (y_rot / ry) ** 2 <= 1.0


def is_in_river(x: float, y: float, river_pts: List[Tuple[float, float]], width: float = 0.55) -> bool:
    """Check if point is within the river channel."""
    half_w = width / 2.0
    for i in range(len(river_pts) - 1):
        x1, y1 = river_pts[i]
        x2, y2 = river_pts[i + 1]
        if distance_point_to_segment(x, y, x1, y1, x2, y2) < half_w:
            return True
    return False


def is_water(x: float, y: float, river_pts: List[Tuple[float, float]], river_w: float = 0.55) -> bool:
    """Check if point is in water (river or reservoir)."""
    return is_in_reservoir(x, y) or is_in_river(x, y, river_pts, river_w)


def get_city_layout() -> Dict[str, Any]:
    """Return the cached city layout or generate it deterministically."""
    global _CACHED_LAYOUT
    if _CACHED_LAYOUT is not None:
        return _CACHED_LAYOUT

    rng = random.Random(42)

    # City geographic boundary (in km)
    bounds = {
        "minX": -18.0,
        "maxX": 17.5,
        "minY": -11.5,
        "maxY": 11.5,
        "widthKm": 35.5,
        "heightKm": 23.0,
    }

    # River centerline polyline
    river_points: List[Tuple[float, float]] = [
        (-10.3, 2.3),
        (-8.2, 0.9),
        (-5.6, -1.5),
        (-2.6, -3.1),
        (0.8, -3.5),
        (4.0, -2.6),
        (7.4, -1.4),
        (11.0, -1.7),
        (14.5, -0.7),
        (17.8, -0.4),
    ]
    river_width = 0.55  # km

    # Reservoir definition
    reservoir = {
        "cx": -13.8,
        "cy": 3.5,
        "rx": 3.2,
        "ry": 1.9,
        "rot": -0.15,
        "name": "Kelvin Reservoir",
    }

    # Kelvin Dam structure spanning the reservoir mouth
    dam = {
        "name": "Kelvin Dam",
        "x1": -10.9,
        "y1": 4.9,
        "x2": -10.0,
        "y2": 1.0,
        "width": 0.16,
        "crest_elevation_m": 142.0,
    }

    # 5 Major bridges spanning the river
    bridges = [
        {
            "id": "br-westgate",
            "name": "Westgate Bridge",
            "x1": -8.6,
            "y1": 1.5,
            "x2": -7.8,
            "y2": 0.3,
            "span_type": "suspension",
            "traffic_lanes": 6,
        },
        {
            "id": "br-oldtown",
            "name": "Old Town Bridge",
            "x1": -6.0,
            "y1": -0.9,
            "x2": -5.2,
            "y2": -2.1,
            "span_type": "arch",
            "traffic_lanes": 4,
        },
        {
            "id": "br-central",
            "name": "Central Crossing",
            "x1": -3.0,
            "y1": -2.4,
            "x2": -2.2,
            "y2": -3.8,
            "span_type": "cable-stayed",
            "traffic_lanes": 8,
        },
        {
            "id": "br-kings",
            "name": "Kingsway Viaduct",
            "x1": 0.5,
            "y1": -2.8,
            "x2": 1.1,
            "y2": -4.2,
            "span_type": "girder",
            "traffic_lanes": 6,
        },
        {
            "id": "br-harbour",
            "name": "Harbour Gate Bridge",
            "x1": 7.1,
            "y1": -0.7,
            "x2": 7.7,
            "y2": -2.1,
            "span_type": "cantilever",
            "traffic_lanes": 6,
        },
    ]

    # Parks and Green Spaces
    parks = [
        {"id": "pk-central", "name": "Central Park", "cx": 0.0, "cy": 1.2, "w": 1.8, "h": 0.9, "rot": 0.0},
        {"id": "pk-riverside", "name": "Riverside Green", "cx": -4.0, "cy": -0.8, "w": 2.2, "h": 0.7, "rot": 0.4},
        {"id": "pk-hillside", "name": "Hillside Nature Reserve", "cx": -13.0, "cy": 7.2, "w": 3.5, "h": 2.2, "rot": -0.2},
        {"id": "pk-greenbelt", "name": "Northern Greenbelt", "cx": 4.5, "cy": 8.0, "w": 4.5, "h": 1.5, "rot": 0.1},
        {"id": "pk-transit", "name": "Meadow Parklands", "cx": 11.0, "cy": 5.0, "w": 2.8, "h": 1.5, "rot": -0.1},
        {"id": "pk-wetlands", "name": "Port Wetlands Sanctuary", "cx": 15.0, "cy": -5.0, "w": 3.2, "h": 1.8, "rot": 0.3},
        {"id": "pk-fernwood", "name": "Fernwood Preserve", "cx": -12.0, "cy": -6.5, "w": 3.5, "h": 2.2, "rot": 0.0},
    ]

    # Major Road & Transit Network
    roads = [
        # Highway 7 (Southern Arterial Corridor)
        {
            "id": "rd-h7",
            "name": "Highway 7 Trans-Metro",
            "type": "highway",
            "lanes": 6,
            "points": [(-17.8, -3.4), (-11.0, -3.8), (-5.0, -4.2), (0.0, -4.6), (6.0, -4.2), (12.0, -4.8), (17.5, -4.5)],
        },
        # Northern Expressway
        {
            "id": "rd-nexp",
            "name": "Northern Expressway",
            "type": "highway",
            "lanes": 6,
            "points": [(-17.8, 8.8), (-10.0, 8.2), (-2.0, 7.8), (5.5, 7.5), (12.0, 7.0), (17.5, 6.4)],
        },
        # Metro Ring Road (surrounds Sector A Downtown)
        {
            "id": "rd-ring",
            "name": "Metro Inner Ring Road",
            "type": "arterial",
            "lanes": 4,
            "points": [
                (2.6, 0.3), (2.4, 2.1), (0.8, 2.8), (-1.2, 2.7), (-2.5, 1.8),
                (-2.6, -0.8), (-1.8, -2.2), (0.0, -2.6), (1.8, -2.1), (2.6, 0.3)
            ],
        },
        # North-South Spine
        {
            "id": "rd-ns",
            "name": "Central Boulevard",
            "type": "arterial",
            "lanes": 4,
            "points": [(0.0, -4.6), (0.0, -2.6), (0.0, 0.3), (0.0, 2.8), (0.5, 5.0), (1.0, 7.6)],
        },
        # East-West Radial
        {
            "id": "rd-ew",
            "name": "Grand Avenue",
            "type": "arterial",
            "lanes": 4,
            "points": [(-9.0, 0.0), (-5.0, 0.2), (-2.5, 0.3), (0.0, 0.3), (3.0, 0.4), (7.0, 0.5), (13.0, 0.6)],
        },
        # Industrial Port Corridor
        {
            "id": "rd-port",
            "name": "Port Access Expressway",
            "type": "arterial",
            "lanes": 4,
            "points": [(1.1, -4.2), (4.5, -4.8), (8.0, -5.2), (11.0, -5.8), (13.5, -6.5), (16.5, -6.0)],
        },
        # Residential Hills Access
        {
            "id": "rd-hills",
            "name": "Hillside Parkway",
            "type": "arterial",
            "lanes": 4,
            "points": [(-2.5, 1.8), (-5.0, 3.2), (-8.0, 4.8), (-10.5, 5.6), (-12.5, 6.0), (-15.5, 6.8)],
        },
        # Dam Access Service Road
        {
            "id": "rd-dam",
            "name": "Reservoir Crest Road",
            "type": "secondary",
            "lanes": 2,
            "points": [(-10.0, 1.0), (-10.4, 3.0), (-10.9, 4.9), (-12.5, 5.5)],
        },
        # Transit Corridor Radial
        {
            "id": "rd-transit",
            "name": "Metro North-East Parkway",
            "type": "arterial",
            "lanes": 4,
            "points": [(0.8, 2.8), (3.5, 4.0), (6.5, 5.0), (9.0, 5.8), (11.0, 6.5), (14.0, 7.2)],
        },
        # Suburbs Link
        {
            "id": "rd-suburbs",
            "name": "Southwest County Road",
            "type": "secondary",
            "lanes": 2,
            "points": [(-1.8, -2.2), (-4.5, -3.8), (-8.2, -5.6), (-11.5, -6.5), (-16.0, -7.5)],
        },
        # Rail line & Metro Spine
        {
            "id": "rd-rail",
            "name": "Metropolitan Freight & Passenger Rail",
            "type": "rail",
            "lanes": 2,
            "points": [
                (-17.8, 7.2), (-11.0, 6.6), (-6.5, 2.8), (-2.5, 1.0),
                (0.3, 0.55), (3.6, 2.8), (5.6, 6.1), (10.0, 6.0), (17.5, 5.4)
            ],
        },
    ]

    # Downtown grid streets
    dt_streets = []
    for gx in [-2.0, -1.5, -1.0, -0.5, 0.5, 1.0, 1.5, 2.0]:
        dt_streets.append({
            "id": f"st-v-{gx}",
            "name": "Street",
            "type": "street",
            "lanes": 2,
            "points": [(gx, -2.0), (gx, 2.4)],
        })
    for gy in [-1.8, -1.2, -0.6, 0.0, 0.6, 1.2, 1.8]:
        dt_streets.append({
            "id": f"st-h-{gy}",
            "name": "Street",
            "type": "street",
            "lanes": 2,
            "points": [(-2.2, gy), (2.2, gy)],
        })
    roads.extend(dt_streets)

    # Key landmark structures and buildings
    structures: List[Dict[str, Any]] = []

    # Sector A: Downtown Skyscrapers & City Hall & Central Station
    structures.append({"id": "str-cst", "name": "Central Railway Terminal", "sector": "A", "kind": "station", "x": 0.3, "y": 0.55, "w": 0.5, "h": 0.35, "floors": 6, "color": "#64748b"})
    structures.append({"id": "str-chall", "name": "City Hall & Municipal Center", "sector": "A", "kind": "civic", "x": -0.4, "y": 0.2, "w": 0.45, "h": 0.35, "floors": 8, "color": "#94a3b8"})
    structures.append({"id": "str-kfin", "name": "Kelvin Financial Tower (72F)", "sector": "A", "kind": "skyscraper", "x": 0.0, "y": 0.0, "w": 0.3, "h": 0.3, "floors": 72, "color": "#38bdf8"})
    structures.append({"id": "str-aegis", "name": "Aegis Telecom Spire (65F)", "sector": "A", "kind": "skyscraper", "x": -0.6, "y": -0.5, "w": 0.28, "h": 0.28, "floors": 65, "color": "#0ea5e9"})
    structures.append({"id": "str-zenith", "name": "Zenith Commercial Tower (58F)", "sector": "A", "kind": "skyscraper", "x": 0.7, "y": -0.4, "w": 0.3, "h": 0.3, "floors": 58, "color": "#0284c7"})
    structures.append({"id": "str-apex", "name": "Apex Center High-Rise (52F)", "sector": "A", "kind": "skyscraper", "x": -0.8, "y": 0.7, "w": 0.32, "h": 0.28, "floors": 52, "color": "#38bdf8"})
    structures.append({"id": "str-horizon", "name": "Horizon Plaza (48F)", "sector": "A", "kind": "skyscraper", "x": 0.9, "y": 0.9, "w": 0.3, "h": 0.32, "floors": 48, "color": "#0ea5e9"})

    # Grid mid-rises in Downtown
    for gx in [-1.8, -1.3, -0.9, -0.4, 0.4, 0.8, 1.3, 1.8]:
        for gy in [-1.5, -0.9, -0.3, 0.4, 1.0, 1.6]:
            if math.hypot(gx, gy - 0.3) < 2.5:
                # avoid overlapping with main landmarks
                if math.hypot(gx - 0.0, gy - 0.0) > 0.4 and math.hypot(gx - 0.3, gy - 0.55) > 0.4:
                    fl = rng.randint(12, 38)
                    structures.append({
                        "id": f"str-dt-{gx}_{gy}",
                        "name": f"Metro Tower {gx:+.1f},{gy:+.1f}",
                        "sector": "A",
                        "kind": "tower",
                        "x": gx + rng.uniform(-0.06, 0.06),
                        "y": gy + rng.uniform(-0.06, 0.06),
                        "w": rng.uniform(0.18, 0.26),
                        "h": rng.uniform(0.18, 0.26),
                        "floors": fl,
                        "color": "#475569" if fl < 25 else "#334155",
                    })

    # Sector B: Industrial & Port Zone (centered around 13.5, -6.5)
    structures.append({"id": "str-port-quay", "name": "Deepwater Cargo Quay", "sector": "B", "kind": "quay", "x": 13.5, "y": -2.4, "w": 5.5, "h": 0.4, "floors": 1, "color": "#475569"})
    structures.append({"id": "str-yard", "name": "Metro Intermodal Container Yard", "sector": "B", "kind": "yard", "x": 13.5, "y": -4.2, "w": 3.2, "h": 1.6, "floors": 1, "color": "#334155"})
    structures.append({"id": "str-tanks", "name": "Petrochem Strategic Tank Farm", "sector": "B", "kind": "tank_farm", "x": 14.8, "y": -7.5, "w": 2.4, "h": 2.0, "floors": 2, "color": "#64748b"})
    structures.append({"id": "str-cool1", "name": "Power Plant Cooling Tower 1", "sector": "B", "kind": "cooling_tower", "x": 11.5, "y": -7.8, "w": 0.5, "h": 0.5, "floors": 10, "color": "#94a3b8"})
    structures.append({"id": "str-cool2", "name": "Power Plant Cooling Tower 2", "sector": "B", "kind": "cooling_tower", "x": 12.1, "y": -7.9, "w": 0.5, "h": 0.5, "floors": 10, "color": "#94a3b8"})
    structures.append({"id": "str-refin", "name": "Coastal Refinery Distillation Unit", "sector": "B", "kind": "factory", "x": 13.8, "y": -7.2, "w": 1.5, "h": 1.0, "floors": 4, "color": "#e2e8f0"})
    structures.append({"id": "str-steel", "name": "Foundry & Heavy Steel Works", "sector": "B", "kind": "factory", "x": 12.0, "y": -5.6, "w": 1.6, "h": 1.0, "floors": 3, "color": "#64748b"})
    structures.append({"id": "str-grain", "name": "Port Grain Silos", "sector": "B", "kind": "silo", "x": 11.2, "y": -3.8, "w": 1.0, "h": 0.6, "floors": 6, "color": "#cbd5e1"})

    # Industrial cranes along quay
    for c_i, cx in enumerate([11.5, 12.2, 12.9, 13.6, 14.3, 15.0, 15.7, 16.4]):
        structures.append({
            "id": f"str-crane-{c_i+1}",
            "name": f"Gantry Crane #{c_i+1}",
            "sector": "B",
            "kind": "crane",
            "x": cx,
            "y": -2.2,
            "w": 0.15,
            "h": 0.18,
            "floors": 8,
            "color": "#f59e0b",
        })

    # Industrial warehouses
    for w_i in range(16):
        wx = 12.0 + (w_i % 4) * 1.1 + rng.uniform(-0.15, 0.15)
        wy = -5.0 - (w_i // 4) * 0.9 + rng.uniform(-0.1, 0.1)
        structures.append({
            "id": f"str-wh-{w_i+1}",
            "name": f"Logistics Warehouse B-{w_i+1:02d}",
            "sector": "B",
            "kind": "warehouse",
            "x": wx,
            "y": wy,
            "w": 0.65,
            "h": 0.45,
            "floors": 2,
            "color": "#475569",
        })

    # Sector C: Residential Hills (centered around -12.5, 6.0)
    structures.append({"id": "str-hosp", "name": "Kelvin Memorial Hospital", "sector": "C", "kind": "hospital", "x": -11.5, "y": 5.5, "w": 0.8, "h": 0.6, "floors": 8, "color": "#ef4444"})
    structures.append({"id": "str-univ", "name": "Hillside Science Institute & School", "sector": "C", "kind": "school", "x": -13.0, "y": 7.0, "w": 0.9, "h": 0.7, "floors": 4, "color": "#3b82f6"})
    structures.append({"id": "str-obs", "name": "Mount Kelvin Seismic Observatory", "sector": "C", "kind": "observatory", "x": -14.8, "y": 8.5, "w": 0.5, "h": 0.5, "floors": 3, "color": "#10b981"})

    # Residential clusters in C
    for h_i in range(24):
        hx = -12.5 + rng.uniform(-3.0, 3.0)
        hy = 6.0 + rng.uniform(-2.8, 2.5)
        if not is_water(hx, hy, river_points, river_width + 0.3):
            structures.append({
                "id": f"str-res-{h_i+1}",
                "name": f"Hills Residential Block C-{h_i+1:02d}",
                "sector": "C",
                "kind": "house_cluster",
                "x": hx,
                "y": hy,
                "w": 0.35,
                "h": 0.3,
                "floors": rng.randint(2, 6),
                "color": "#64748b",
            })

    # Sector D: Transit & Infrastructure Corridor (centered around 11.0, 6.5)
    structures.append({"id": "str-mall", "name": "Meadow Center Mega Mall", "sector": "D", "kind": "mall", "x": 9.8, "y": 5.5, "w": 1.6, "h": 1.1, "floors": 4, "color": "#ec4899"})
    structures.append({"id": "str-arena", "name": "Kelvin Olympic Arena & Stadium", "sector": "D", "kind": "stadium", "x": 12.2, "y": 5.8, "w": 1.4, "h": 1.2, "floors": 5, "color": "#8b5cf6"})
    structures.append({"id": "str-thub", "name": "Metropolitan Intermodal Transit Hub", "sector": "D", "kind": "transit_hub", "x": 11.0, "y": 7.2, "w": 1.0, "h": 0.7, "floors": 5, "color": "#06b6d4"})
    structures.append({"id": "str-retail", "name": "North Meadow Commercial Park", "sector": "D", "kind": "retail_park", "x": 12.8, "y": 7.5, "w": 1.3, "h": 0.8, "floors": 3, "color": "#f97316"})

    # Sector D office parks & commercial facilities
    for d_i in range(14):
        dx = 11.0 + rng.uniform(-2.5, 2.5)
        dy = 6.5 + rng.uniform(-2.2, 2.2)
        structures.append({
            "id": f"str-comm-d-{d_i+1}",
            "name": f"Commerce Park Office D-{d_i+1:02d}",
            "sector": "D",
            "kind": "office",
            "x": dx,
            "y": dy,
            "w": 0.45,
            "h": 0.35,
            "floors": rng.randint(4, 12),
            "color": "#334155",
        })

    # Sector E: Outlying Suburban Ring (centered around -11.5, -6.5)
    structures.append({"id": "str-subst", "name": "Regional 500kV Electrical Substation", "sector": "E", "kind": "substation", "x": -10.5, "y": -6.5, "w": 0.9, "h": 0.7, "floors": 2, "color": "#eab308"})
    structures.append({"id": "str-wtower", "name": "Municipal Water Storage Tower", "sector": "E", "kind": "water_tower", "x": -12.5, "y": -5.0, "w": 0.4, "h": 0.4, "floors": 8, "color": "#38bdf8"})
    structures.append({"id": "str-grain-e", "name": "Valley Agricultural Silo Complex", "sector": "E", "kind": "silo", "x": -13.5, "y": -7.5, "w": 1.0, "h": 0.7, "floors": 4, "color": "#a8a29e"})

    # Suburb residential clusters & farms in E
    for e_i in range(18):
        ex = -11.5 + rng.uniform(-3.0, 3.0)
        ey = -6.5 + rng.uniform(-2.8, 2.8)
        if not is_water(ex, ey, river_points, river_width + 0.3):
            structures.append({
                "id": f"str-suburb-{e_i+1}",
                "name": f"Suburban Subdivision E-{e_i+1:02d}",
                "sector": "E",
                "kind": "house_cluster",
                "x": ex,
                "y": ey,
                "w": 0.4,
                "h": 0.35,
                "floors": rng.randint(1, 3),
                "color": "#52525b",
            })

    # Trees (~1,800 trees placed in parks, reserves, boulevards, hills)
    trees: List[List[float]] = []  # [x, y, radius]
    for park in parks:
        # Scatter trees in park bounds
        count = int(park["w"] * park["h"] * 55)
        for _ in range(count):
            tx = park["cx"] + rng.uniform(-park["w"] / 2.0, park["w"] / 2.0)
            ty = park["cy"] + rng.uniform(-park["h"] / 2.0, park["h"] / 2.0)
            if not is_water(tx, ty, river_points, river_width):
                trees.append([round(tx, 3), round(ty, 3), round(rng.uniform(0.04, 0.08), 3)])

    # Trees along hills (Sector C)
    for _ in range(400):
        tx = -12.5 + rng.gauss(0, 2.2)
        ty = 6.0 + rng.gauss(0, 2.0)
        if -17.5 <= tx <= -7.0 and 2.0 <= ty <= 11.0 and not is_water(tx, ty, river_points, river_width):
            trees.append([round(tx, 3), round(ty, 3), round(rng.uniform(0.04, 0.09), 3)])

    # Trees in suburban outskirts (Sector E)
    for _ in range(350):
        tx = -11.5 + rng.gauss(0, 2.5)
        ty = -6.5 + rng.gauss(0, 2.2)
        if -17.5 <= tx <= -5.0 and -11.0 <= ty <= -2.0 and not is_water(tx, ty, river_points, river_width):
            trees.append([round(tx, 3), round(ty, 3), round(rng.uniform(0.04, 0.08), 3)])

    # Prominent HUD Labels for landmarks
    labels = [
        {"text": "Kelvin Reservoir", "x": -13.8, "y": 3.8, "minZoom": 0.7, "maxZoom": 4.5, "kind": "water"},
        {"text": "Kelvin Dam", "x": -10.5, "y": 3.1, "minZoom": 1.0, "maxZoom": 12.0, "kind": "infrastructure"},
        {"text": "Westgate Bridge", "x": -8.2, "y": 1.1, "minZoom": 1.5, "maxZoom": 12.0, "kind": "infrastructure"},
        {"text": "Central Crossing", "x": -2.6, "y": -2.8, "minZoom": 1.5, "maxZoom": 12.0, "kind": "infrastructure"},
        {"text": "Harbour Gate Bridge", "x": 7.4, "y": -1.2, "minZoom": 1.5, "maxZoom": 12.0, "kind": "infrastructure"},
        {"text": "Sector A: Downtown", "x": 0.0, "y": 2.6, "minZoom": 0.7, "maxZoom": 3.5, "kind": "sector"},
        {"text": "Central Railway Terminal", "x": 0.3, "y": 0.95, "minZoom": 2.2, "maxZoom": 14.0, "kind": "landmark"},
        {"text": "Kelvin Financial Tower (72F)", "x": 0.0, "y": -0.35, "minZoom": 2.2, "maxZoom": 14.0, "kind": "landmark"},
        {"text": "Central Park", "x": 0.0, "y": 1.2, "minZoom": 1.2, "maxZoom": 6.0, "kind": "park"},
        {"text": "Sector B: Industrial Port", "x": 13.5, "y": -9.0, "minZoom": 0.7, "maxZoom": 3.5, "kind": "sector"},
        {"text": "Cargo Quays & Cranes", "x": 13.5, "y": -2.8, "minZoom": 1.8, "maxZoom": 14.0, "kind": "landmark"},
        {"text": "Petrochem Tank Farm", "x": 14.8, "y": -7.2, "minZoom": 1.8, "maxZoom": 14.0, "kind": "landmark"},
        {"text": "Sector C: Residential Hills", "x": -12.5, "y": 9.0, "minZoom": 0.7, "maxZoom": 3.5, "kind": "sector"},
        {"text": "Kelvin Memorial Hospital", "x": -11.5, "y": 6.2, "minZoom": 1.8, "maxZoom": 14.0, "kind": "landmark"},
        {"text": "Sector D: Transit Corridor", "x": 11.0, "y": 9.0, "minZoom": 0.7, "maxZoom": 3.5, "kind": "sector"},
        {"text": "Meadow Center Mall", "x": 9.8, "y": 6.2, "minZoom": 1.8, "maxZoom": 14.0, "kind": "landmark"},
        {"text": "Kelvin Olympic Arena", "x": 12.2, "y": 6.6, "minZoom": 1.8, "maxZoom": 14.0, "kind": "landmark"},
        {"text": "Transit Hub", "x": 11.0, "y": 7.8, "minZoom": 2.0, "maxZoom": 14.0, "kind": "landmark"},
        {"text": "Sector E: Suburban Ring", "x": -11.5, "y": -9.0, "minZoom": 0.7, "maxZoom": 3.5, "kind": "sector"},
        {"text": "500kV Substation", "x": -10.5, "y": -5.8, "minZoom": 2.0, "maxZoom": 14.0, "kind": "landmark"},
    ]

    # Exactly 500 sensors (100 per sector) distributed realistically on infrastructure and buildings
    sensors: List[Dict[str, Any]] = []

    # Sensor builder helper
    def build_sector_sensors(sector: str, count: int, anchor_list: List[Dict[str, Any]], candidate_structures: List[Dict[str, Any]], center: Tuple[float, float], radius: float):
        sec_sensors = []
        # Add anchors first
        for a in anchor_list:
            if len(sec_sensors) < count:
                sec_sensors.append({
                    "id": "",  # will assign sequential ID
                    "sector": sector,
                    "x": round(a["x"], 4),
                    "y": round(a["y"], 4),
                    "kind": a.get("kind", "infrastructure"),
                    "site": a.get("site", f"Sector {sector} Facility"),
                })

        # Add from structures
        for s in candidate_structures:
            if len(sec_sensors) < count:
                sec_sensors.append({
                    "id": "",
                    "sector": sector,
                    "x": round(s["x"], 4),
                    "y": round(s["y"], 4),
                    "kind": "building" if s["kind"] in ("tower", "skyscraper", "office", "civic") else "infrastructure",
                    "site": s["name"],
                })

        # Fill remaining with distributed grid points in the sector
        attempts = 0
        while len(sec_sensors) < count and attempts < 1000:
            attempts += 1
            ang = rng.uniform(0, 2 * math.pi)
            dist = math.sqrt(rng.uniform(0, 1)) * radius * 0.95
            sx = center[0] + dist * math.cos(ang)
            sy = center[1] + dist * math.sin(ang)

            # Avoid open water unless on dam/bridge
            if is_water(sx, sy, river_points, river_width):
                continue

            sec_sensors.append({
                "id": "",
                "sector": sector,
                "x": round(sx, 4),
                "y": round(sy, 4),
                "kind": "ground_station",
                "site": f"District {sector} Seismic Sub-station",
            })

        return sec_sensors[:count]

    # --- Sector A Anchors (Downtown & Bridges) ---
    anchors_a = []
    # Bridges connected to Downtown (Central & Kings)
    for br in [bridges[2], bridges[3]]:
        for t in [0.25, 0.5, 0.75]:
            bx = br["x1"] + t * (br["x2"] - br["x1"])
            by = br["y1"] + t * (br["y2"] - br["y1"])
            anchors_a.append({"x": bx, "y": by, "kind": "bridge", "site": f"{br['name']} Pier"})
    # Key towers in A
    dt_structures = [s for s in structures if s.get("sector") == "A"]
    sensors_a = build_sector_sensors("A", 100, anchors_a, dt_structures, SECTOR_INFO["A"]["center_coords"], SECTOR_INFO["A"]["radius_km"])

    # --- Sector B Anchors (Industrial & Port Zone) ---
    anchors_b = []
    # Harbour bridge pier & tank farm
    anchors_b.append({"x": bridges[4]["x1"], "y": bridges[4]["y1"], "kind": "bridge", "site": "Harbour Gate Pier"})
    anchors_b.append({"x": 13.5, "y": -2.4, "kind": "quay", "site": "Deepwater Cargo Quay North"})
    anchors_b.append({"x": 14.8, "y": -7.5, "kind": "tank_farm", "site": "Petrochem Tank Farm Base"})
    b_structures = [s for s in structures if s.get("sector") == "B"]
    sensors_b = build_sector_sensors("B", 100, anchors_b, b_structures, SECTOR_INFO["B"]["center_coords"], SECTOR_INFO["B"]["radius_km"])

    # --- Sector C Anchors (Residential Hills & Kelvin Dam) ---
    anchors_c = []
    # 10 Kelvin Dam Crest Sensors!
    for i in range(10):
        t = (i + 0.5) / 10.0
        dx = dam["x1"] + t * (dam["x2"] - dam["x1"])
        dy = dam["y1"] + t * (dam["y2"] - dam["y1"])
        anchors_c.append({"x": dx, "y": dy, "kind": "dam", "site": f"Kelvin Dam Crest Piezometer #{i+1:02d}"})
    # Westgate bridge north abutment
    anchors_c.append({"x": bridges[0]["x1"], "y": bridges[0]["y1"], "kind": "bridge", "site": "Westgate Bridge Abutment"})
    c_structures = [s for s in structures if s.get("sector") == "C"]
    sensors_c = build_sector_sensors("C", 100, anchors_c, c_structures, SECTOR_INFO["C"]["center_coords"], SECTOR_INFO["C"]["radius_km"])

    # --- Sector D Anchors (Transit & Infrastructure Corridor) ---
    anchors_d = []
    # Highway overpasses & rail bridges & mall
    anchors_d.append({"x": 11.0, "y": 7.2, "kind": "transit_hub", "site": "Metro Intermodal Terminal"})
    anchors_d.append({"x": 9.8, "y": 5.5, "kind": "building", "site": "Meadow Center Mall Roof"})
    anchors_d.append({"x": 12.2, "y": 5.8, "kind": "infrastructure", "site": "Kelvin Olympic Arena Dome"})
    d_structures = [s for s in structures if s.get("sector") == "D"]
    sensors_d = build_sector_sensors("D", 100, anchors_d, d_structures, SECTOR_INFO["D"]["center_coords"], SECTOR_INFO["D"]["radius_km"])

    # --- Sector E Anchors (Suburban Ring) ---
    anchors_e = []
    anchors_e.append({"x": -10.5, "y": -6.5, "kind": "substation", "site": "500kV Substation Transformer Yard"})
    anchors_e.append({"x": -12.5, "y": -5.0, "kind": "water_tower", "site": "Water Tower Structural Base"})
    anchors_e.append({"x": -13.5, "y": -7.5, "kind": "silo", "site": "Agricultural Silo Complex Pier"})
    e_structures = [s for s in structures if s.get("sector") == "E"]
    sensors_e = build_sector_sensors("E", 100, anchors_e, e_structures, SECTOR_INFO["E"]["center_coords"], SECTOR_INFO["E"]["radius_km"])

    # Assign sequential node IDs (node-001 to node-500)
    all_sector_lists = [
        ("A", 1, 100, sensors_a),
        ("B", 101, 200, sensors_b),
        ("C", 201, 300, sensors_c),
        ("D", 301, 400, sensors_d),
        ("E", 401, 500, sensors_e),
    ]

    for sec_name, start_idx, end_idx, sec_list in all_sector_lists:
        for idx, s in enumerate(sec_list):
            node_num = start_idx + idx
            s["id"] = f"node-{node_num:03d}"
            sensors.append(s)

    # Sectors summary list for UI rendering
    sector_meta = []
    sector_colors = {
        "A": "#38bdf8",  # Sky cyan (Downtown)
        "B": "#f59e0b",  # Amber (Industrial & Port)
        "C": "#10b981",  # Emerald (Hills)
        "D": "#a855f7",  # Purple (Transit Corridor)
        "E": "#06b6d4",  # Cyan/Teal (Suburbs)
    }
    for sec_id, info in SECTOR_INFO.items():
        sector_meta.append({
            "id": sec_id,
            "name": info["name"],
            "short": f"Sector {sec_id}",
            "x": info["center_coords"][0],
            "y": info["center_coords"][1],
            "radius_km": info["radius_km"],
            "soil_amplification": info["soil_amplification"],
            "color": sector_colors.get(sec_id, "#38bdf8"),
        })

    _CACHED_LAYOUT = {
        "bounds": bounds,
        "sectors": sector_meta,
        "river": {"points": river_points, "width": river_width},
        "reservoir": reservoir,
        "dam": dam,
        "bridges": bridges,
        "parks": parks,
        "roads": roads,
        "structures": structures,
        "trees": trees,
        "labels": labels,
        "sensors": sensors,
    }

    return _CACHED_LAYOUT
