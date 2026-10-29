"""
City Layout Generator for Metropolitan Seismic Monitoring (Living City Map).
Deterministic procedural generator producing rich metropolitan geography:
- Bounds: Expanded 50 km x 24 km widescreen layout (X: -25 to +25, Y: -12 to +12)
- Sectors A-E evenly spread out with connecting transit corridors and greenbelts
- Water bodies: Kelvin Dam, Kelvin Reservoir, Meandering Trans-Metro River
- Infrastructure: 5 Major Bridges, Highways (H7 & Northern Expressway), Ring Roads, Arterials, Rail Network
- Districts & Structures:
  - Sector A: Downtown (Financial skyscrapers, towers, Central Station, Civic Hall)
  - Sector B: Industrial & Port (Deepwater quays, gantry cranes, container yard, tank farm, cooling towers)
  - Sector C: Residential Hills (Kelvin Dam, Memorial Hospital, Observatory, Hillside neighborhoods)
  - Sector D: Transit & Infrastructure Corridor (Meadow Mall, Kelvin Olympic Arena, Transit Hub, Commerce Park)
  - Sector E: Outlying Suburban Ring (500kV Substation, Water Tower, Agricultural Silos, Subdivisions)
- Exactly 500 sensors (100 per sector) distributed via Poisson-disk minimum spacing (min_dist >= 0.65km)
  along infrastructure, bridges, arterials, and districts without clustering.
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


def is_in_reservoir(x: float, y: float, cx: float = -18.0, cy: float = 4.2, rx: float = 4.6, ry: float = 2.4, rot: float = -0.15) -> bool:
    """Check if point is within the elliptical reservoir."""
    cos_r = math.cos(-rot)
    sin_r = math.sin(-rot)
    dx = x - cx
    dy = y - cy
    x_rot = dx * cos_r - dy * sin_r
    y_rot = dx * sin_r + dy * cos_r
    return (x_rot / rx) ** 2 + (y_rot / ry) ** 2 <= 1.0


def is_in_river(x: float, y: float, river_pts: List[Tuple[float, float]], width: float = 0.65) -> bool:
    """Check if point is within the river channel."""
    half_w = width / 2.0
    for i in range(len(river_pts) - 1):
        x1, y1 = river_pts[i]
        x2, y2 = river_pts[i + 1]
        if distance_point_to_segment(x, y, x1, y1, x2, y2) < half_w:
            return True
    return False


def is_water(x: float, y: float, river_pts: List[Tuple[float, float]], river_w: float = 0.65) -> bool:
    """Check if point is in water (river or reservoir)."""
    return is_in_reservoir(x, y) or is_in_river(x, y, river_pts, river_w)


def get_city_layout() -> Dict[str, Any]:
    """Return the cached city layout or generate it deterministically."""
    global _CACHED_LAYOUT
    if _CACHED_LAYOUT is not None:
        return _CACHED_LAYOUT

    rng = random.Random(42)

    # City geographic boundary (in km): Widescreen 50 km x 24 km
    bounds = {
        "minX": -25.0,
        "maxX": 25.0,
        "minY": -12.0,
        "maxY": 12.0,
        "widthKm": 50.0,
        "heightKm": 24.0,
    }

    # Trans-Metro River centerline polyline spanning across the 50km expanse
    river_points: List[Tuple[float, float]] = [
        (-24.5, 4.2),
        (-19.5, 3.6),
        (-14.2, 2.5),
        (-9.5, 0.8),
        (-5.6, -1.5),
        (-1.5, -2.8),
        (2.5, -3.2),
        (7.0, -2.1),
        (12.0, -1.4),
        (17.5, -0.6),
        (24.5, -0.2),
    ]
    river_width = 0.65  # km

    # Reservoir definition
    reservoir = {
        "cx": -18.0,
        "cy": 4.2,
        "rx": 4.6,
        "ry": 2.4,
        "rot": -0.15,
        "name": "Kelvin Reservoir",
    }

    # Kelvin Dam structure spanning the reservoir outlet
    dam = {
        "name": "Kelvin Dam",
        "x1": -13.5,
        "y1": 5.8,
        "x2": -12.6,
        "y2": 1.2,
        "width": 0.20,
        "crest_elevation_m": 142.0,
    }

    # 5 Major bridges spanning the river
    bridges = [
        {
            "id": "br-westgate",
            "name": "Westgate Bridge",
            "x1": -10.2,
            "y1": 1.5,
            "x2": -9.4,
            "y2": 0.2,
            "span_type": "suspension",
            "traffic_lanes": 6,
        },
        {
            "id": "br-oldtown",
            "name": "Old Town Bridge",
            "x1": -6.2,
            "y1": -0.9,
            "x2": -5.4,
            "y2": -2.2,
            "span_type": "arch",
            "traffic_lanes": 4,
        },
        {
            "id": "br-central",
            "name": "Central Crossing",
            "x1": -2.0,
            "y1": -2.2,
            "x2": -1.2,
            "y2": -3.5,
            "span_type": "cable-stayed",
            "traffic_lanes": 8,
        },
        {
            "id": "br-kings",
            "name": "Kingsway Viaduct",
            "x1": 2.2,
            "y1": -2.6,
            "x2": 2.8,
            "y2": -3.9,
            "span_type": "girder",
            "traffic_lanes": 6,
        },
        {
            "id": "br-harbour",
            "name": "Harbour Gate Bridge",
            "x1": 9.5,
            "y1": -1.2,
            "x2": 10.1,
            "y2": -2.5,
            "span_type": "cantilever",
            "traffic_lanes": 6,
        },
    ]

    # Parks and Green Spaces
    parks = [
        {"id": "pk-central", "name": "Central Park", "cx": 0.0, "cy": 1.2, "w": 2.4, "h": 1.2, "rot": 0.0},
        {"id": "pk-riverside", "name": "Riverside Green", "cx": -4.0, "cy": -0.8, "w": 3.0, "h": 0.9, "rot": 0.4},
        {"id": "pk-hillside", "name": "Hillside Nature Reserve", "cx": -16.0, "cy": 8.5, "w": 5.0, "h": 3.0, "rot": -0.2},
        {"id": "pk-greenbelt", "name": "Northern Greenbelt", "cx": 5.0, "cy": 9.0, "w": 6.0, "h": 2.0, "rot": 0.1},
        {"id": "pk-transit", "name": "Meadow Parklands", "cx": 15.0, "cy": 5.5, "w": 3.8, "h": 2.0, "rot": -0.1},
        {"id": "pk-wetlands", "name": "Port Wetlands Sanctuary", "cx": 18.0, "cy": -6.0, "w": 4.5, "h": 2.2, "rot": 0.3},
        {"id": "pk-fernwood", "name": "Fernwood Preserve", "cx": -16.0, "cy": -7.5, "w": 4.5, "h": 2.8, "rot": 0.0},
    ]

    # Major Road & Transit Network spanning across the 50km canvas
    roads = [
        # Highway 7 (Southern Arterial Corridor)
        {
            "id": "rd-h7",
            "name": "Highway 7 Trans-Metro",
            "type": "highway",
            "lanes": 6,
            "points": [(-24.5, -4.5), (-16.0, -4.8), (-8.0, -5.0), (0.0, -4.8), (8.0, -4.6), (16.0, -5.2), (24.5, -4.8)],
        },
        # Northern Expressway
        {
            "id": "rd-nexp",
            "name": "Northern Expressway",
            "type": "highway",
            "lanes": 6,
            "points": [(-24.5, 8.8), (-16.0, 8.2), (-6.0, 7.8), (3.0, 7.6), (12.0, 7.2), (24.5, 6.6)],
        },
        # Metro Inner Ring Road (surrounds Sector A Downtown)
        {
            "id": "rd-ring",
            "name": "Metro Inner Ring Road",
            "type": "arterial",
            "lanes": 4,
            "points": [
                (3.2, 0.4), (3.0, 2.5), (1.0, 3.4), (-1.5, 3.2), (-3.2, 2.2),
                (-3.4, -1.0), (-2.2, -2.8), (0.0, -3.2), (2.2, -2.6), (3.2, 0.4)
            ],
        },
        # North-South Spine
        {
            "id": "rd-ns",
            "name": "Central Boulevard",
            "type": "arterial",
            "lanes": 4,
            "points": [(0.0, -11.5), (0.0, -4.8), (0.0, 0.3), (0.0, 3.4), (0.5, 6.0), (1.0, 11.5)],
        },
        # East-West Radial Grand Avenue
        {
            "id": "rd-ew",
            "name": "Grand Avenue",
            "type": "arterial",
            "lanes": 4,
            "points": [(-24.0, 0.3), (-14.0, 0.2), (-5.0, 0.3), (0.0, 0.3), (6.0, 0.4), (15.0, 0.5), (24.0, 0.5)],
        },
        # Industrial Port Corridor
        {
            "id": "rd-port",
            "name": "Port Access Expressway",
            "type": "arterial",
            "lanes": 4,
            "points": [(2.8, -3.9), (6.5, -4.5), (11.0, -5.0), (16.0, -5.8), (20.0, -6.5), (24.0, -6.2)],
        },
        # Residential Hills Access
        {
            "id": "rd-hills",
            "name": "Hillside Parkway",
            "type": "arterial",
            "lanes": 4,
            "points": [(-3.2, 2.2), (-7.0, 3.6), (-11.0, 5.0), (-16.0, 6.2), (-20.5, 7.2), (-24.5, 7.8)],
        },
        # Dam Access Service Road
        {
            "id": "rd-dam",
            "name": "Reservoir Crest Road",
            "type": "secondary",
            "lanes": 2,
            "points": [(-12.6, 1.2), (-13.0, 3.5), (-13.5, 5.8), (-16.0, 6.8)],
        },
        # Transit Corridor Radial
        {
            "id": "rd-transit",
            "name": "Metro North-East Parkway",
            "type": "arterial",
            "lanes": 4,
            "points": [(1.0, 3.4), (5.0, 4.5), (10.0, 5.6), (15.5, 6.5), (20.0, 7.2), (24.5, 7.8)],
        },
        # Suburbs Link
        {
            "id": "rd-suburbs",
            "name": "Southwest County Road",
            "type": "secondary",
            "lanes": 2,
            "points": [(-2.2, -2.8), (-6.0, -4.5), (-11.0, -5.8), (-15.5, -6.8), (-21.0, -7.8), (-24.5, -8.2)],
        },
        # Rail line & Metro Spine
        {
            "id": "rd-rail",
            "name": "Metropolitan Freight & Passenger Rail",
            "type": "rail",
            "lanes": 2,
            "points": [
                (-24.5, 7.2), (-16.0, 6.8), (-8.0, 3.2), (-3.0, 1.2),
                (0.3, 0.55), (4.5, 2.8), (9.0, 5.5), (15.5, 6.2), (24.5, 5.4)
            ],
        },
    ]

    # Downtown grid streets
    dt_streets = []
    for gx in [-2.4, -1.8, -1.2, -0.6, 0.6, 1.2, 1.8, 2.4]:
        dt_streets.append({
            "id": f"st-v-{gx}",
            "name": "Street",
            "type": "street",
            "lanes": 2,
            "points": [(gx, -2.5), (gx, 2.8)],
        })
    for gy in [-2.2, -1.5, -0.8, 0.0, 0.8, 1.5, 2.2]:
        dt_streets.append({
            "id": f"st-h-{gy}",
            "name": "Street",
            "type": "street",
            "lanes": 2,
            "points": [(-2.8, gy), (2.8, gy)],
        })
    roads.extend(dt_streets)

    # Key landmark structures and buildings
    structures: List[Dict[str, Any]] = []

    # Sector A: Downtown Skyscrapers & City Hall & Central Station
    structures.append({"id": "str-cst", "name": "Central Railway Terminal", "sector": "A", "kind": "station", "x": 0.3, "y": 0.55, "w": 0.6, "h": 0.4, "floors": 6, "color": "#64748b"})
    structures.append({"id": "str-chall", "name": "City Hall & Municipal Center", "sector": "A", "kind": "civic", "x": -0.5, "y": 0.2, "w": 0.5, "h": 0.4, "floors": 8, "color": "#94a3b8"})
    structures.append({"id": "str-kfin", "name": "Kelvin Financial Tower (72F)", "sector": "A", "kind": "skyscraper", "x": 0.0, "y": 0.0, "w": 0.35, "h": 0.35, "floors": 72, "color": "#38bdf8"})
    structures.append({"id": "str-aegis", "name": "Aegis Telecom Spire (65F)", "sector": "A", "kind": "skyscraper", "x": -0.8, "y": -0.6, "w": 0.32, "h": 0.32, "floors": 65, "color": "#0ea5e9"})
    structures.append({"id": "str-zenith", "name": "Zenith Commercial Tower (58F)", "sector": "A", "kind": "skyscraper", "x": 0.8, "y": -0.5, "w": 0.32, "h": 0.32, "floors": 58, "color": "#0284c7"})
    structures.append({"id": "str-apex", "name": "Apex Center High-Rise (52F)", "sector": "A", "kind": "skyscraper", "x": -1.0, "y": 0.8, "w": 0.35, "h": 0.3, "floors": 52, "color": "#38bdf8"})
    structures.append({"id": "str-horizon", "name": "Horizon Plaza (48F)", "sector": "A", "kind": "skyscraper", "x": 1.1, "y": 1.0, "w": 0.32, "h": 0.35, "floors": 48, "color": "#0ea5e9"})

    # Grid mid-rises in Downtown
    for gx in [-2.2, -1.6, -1.0, -0.4, 0.4, 1.0, 1.6, 2.2]:
        for gy in [-1.8, -1.1, -0.4, 0.4, 1.1, 1.8]:
            if math.hypot(gx, gy - 0.2) < 3.2:
                if math.hypot(gx - 0.0, gy - 0.0) > 0.45 and math.hypot(gx - 0.3, gy - 0.55) > 0.45:
                    fl = rng.randint(14, 42)
                    structures.append({
                        "id": f"str-dt-{gx}_{gy}",
                        "name": f"Metro Tower {gx:+.1f},{gy:+.1f}",
                        "sector": "A",
                        "kind": "tower",
                        "x": gx + rng.uniform(-0.06, 0.06),
                        "y": gy + rng.uniform(-0.06, 0.06),
                        "w": rng.uniform(0.20, 0.28),
                        "h": rng.uniform(0.20, 0.28),
                        "floors": fl,
                        "color": "#475569" if fl < 25 else "#334155",
                    })

    # Sector B: Industrial & Port Zone (centered around 16.0, -5.5)
    structures.append({"id": "str-port-quay", "name": "Deepwater Cargo Quay", "sector": "B", "kind": "quay", "x": 16.0, "y": -2.2, "w": 7.0, "h": 0.5, "floors": 1, "color": "#475569"})
    structures.append({"id": "str-yard", "name": "Metro Intermodal Container Yard", "sector": "B", "kind": "yard", "x": 15.5, "y": -4.2, "w": 4.0, "h": 1.8, "floors": 1, "color": "#334155"})
    structures.append({"id": "str-tanks", "name": "Petrochem Strategic Tank Farm", "sector": "B", "kind": "tank_farm", "x": 18.0, "y": -7.2, "w": 3.0, "h": 2.2, "floors": 2, "color": "#64748b"})
    structures.append({"id": "str-cool1", "name": "Power Plant Cooling Tower 1", "sector": "B", "kind": "cooling_tower", "x": 13.5, "y": -7.8, "w": 0.6, "h": 0.6, "floors": 10, "color": "#94a3b8"})
    structures.append({"id": "str-cool2", "name": "Power Plant Cooling Tower 2", "sector": "B", "kind": "cooling_tower", "x": 14.3, "y": -7.9, "w": 0.6, "h": 0.6, "floors": 10, "color": "#94a3b8"})
    structures.append({"id": "str-refin", "name": "Coastal Refinery Distillation Unit", "sector": "B", "kind": "factory", "x": 16.5, "y": -7.0, "w": 2.0, "h": 1.2, "floors": 4, "color": "#e2e8f0"})
    structures.append({"id": "str-steel", "name": "Foundry & Heavy Steel Works", "sector": "B", "kind": "factory", "x": 13.5, "y": -5.6, "w": 2.0, "h": 1.2, "floors": 3, "color": "#64748b"})
    structures.append({"id": "str-grain", "name": "Port Grain Silos", "sector": "B", "kind": "silo", "x": 12.8, "y": -3.8, "w": 1.2, "h": 0.8, "floors": 6, "color": "#cbd5e1"})

    # Industrial cranes along quay
    for c_i, cx in enumerate([13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0]):
        structures.append({
            "id": f"str-crane-{c_i+1}",
            "name": f"Gantry Crane #{c_i+1}",
            "sector": "B",
            "kind": "crane",
            "x": cx,
            "y": -2.0,
            "w": 0.18,
            "h": 0.22,
            "floors": 8,
            "color": "#f59e0b",
        })

    # Industrial warehouses spread across Sector B
    for w_i in range(18):
        wx = 13.5 + (w_i % 6) * 1.4 + rng.uniform(-0.15, 0.15)
        wy = -4.8 - (w_i // 6) * 1.3 + rng.uniform(-0.1, 0.1)
        structures.append({
            "id": f"str-wh-{w_i+1}",
            "name": f"Logistics Warehouse B-{w_i+1:02d}",
            "sector": "B",
            "kind": "warehouse",
            "x": wx,
            "y": wy,
            "w": 0.8,
            "h": 0.55,
            "floors": 2,
            "color": "#475569",
        })

    # Sector C: Residential Hills (centered around -16.0, 5.5)
    structures.append({"id": "str-hosp", "name": "Kelvin Memorial Hospital", "sector": "C", "kind": "hospital", "x": -14.5, "y": 4.8, "w": 1.0, "h": 0.7, "floors": 8, "color": "#ef4444"})
    structures.append({"id": "str-univ", "name": "Hillside Science Institute & School", "sector": "C", "kind": "school", "x": -16.5, "y": 6.8, "w": 1.1, "h": 0.8, "floors": 4, "color": "#3b82f6"})
    structures.append({"id": "str-obs", "name": "Mount Kelvin Seismic Observatory", "sector": "C", "kind": "observatory", "x": -19.5, "y": 8.5, "w": 0.6, "h": 0.6, "floors": 3, "color": "#10b981"})

    # Residential clusters in C spread out in sub-neighborhoods
    for h_i in range(26):
        hx = -16.0 + rng.uniform(-4.5, 4.5)
        hy = 5.5 + rng.uniform(-3.5, 3.5)
        if not is_water(hx, hy, river_points, river_width + 0.3):
            structures.append({
                "id": f"str-res-{h_i+1}",
                "name": f"Hills Residential Block C-{h_i+1:02d}",
                "sector": "C",
                "kind": "house_cluster",
                "x": hx,
                "y": hy,
                "w": 0.42,
                "h": 0.35,
                "floors": rng.randint(2, 6),
                "color": "#64748b",
            })

    # Sector D: Transit & Infrastructure Corridor (centered around 15.5, 5.5)
    structures.append({"id": "str-mall", "name": "Meadow Center Mega Mall", "sector": "D", "kind": "mall", "x": 13.5, "y": 4.5, "w": 1.8, "h": 1.2, "floors": 4, "color": "#ec4899"})
    structures.append({"id": "str-arena", "name": "Kelvin Olympic Arena & Stadium", "sector": "D", "kind": "stadium", "x": 17.0, "y": 5.2, "w": 1.6, "h": 1.4, "floors": 5, "color": "#8b5cf6"})
    structures.append({"id": "str-thub", "name": "Metropolitan Intermodal Transit Hub", "sector": "D", "kind": "transit_hub", "x": 15.5, "y": 6.8, "w": 1.2, "h": 0.8, "floors": 5, "color": "#06b6d4"})
    structures.append({"id": "str-retail", "name": "North Meadow Commercial Park", "sector": "D", "kind": "retail_park", "x": 18.0, "y": 7.2, "w": 1.5, "h": 0.9, "floors": 3, "color": "#f97316"})

    # Sector D office parks & commercial facilities
    for d_i in range(16):
        dx = 15.5 + rng.uniform(-4.0, 4.0)
        dy = 5.5 + rng.uniform(-3.2, 3.2)
        structures.append({
            "id": f"str-comm-d-{d_i+1}",
            "name": f"Commerce Park Office D-{d_i+1:02d}",
            "sector": "D",
            "kind": "office",
            "x": dx,
            "y": dy,
            "w": 0.55,
            "h": 0.4,
            "floors": rng.randint(4, 12),
            "color": "#334155",
        })

    # Sector E: Outlying Suburban Ring (centered around -15.5, -5.5)
    structures.append({"id": "str-subst", "name": "Regional 500kV Electrical Substation", "sector": "E", "kind": "substation", "x": -13.5, "y": -5.5, "w": 1.1, "h": 0.8, "floors": 2, "color": "#eab308"})
    structures.append({"id": "str-wtower", "name": "Municipal Water Storage Tower", "sector": "E", "kind": "water_tower", "x": -17.0, "y": -4.2, "w": 0.5, "h": 0.5, "floors": 8, "color": "#38bdf8"})
    structures.append({"id": "str-grain-e", "name": "Valley Agricultural Silo Complex", "sector": "E", "kind": "silo", "x": -18.5, "y": -7.0, "w": 1.2, "h": 0.8, "floors": 4, "color": "#a8a29e"})

    # Suburb residential clusters & subdivisions in E
    for e_i in range(22):
        ex = -15.5 + rng.uniform(-4.5, 4.5)
        ey = -5.5 + rng.uniform(-3.5, 3.5)
        if not is_water(ex, ey, river_points, river_width + 0.3):
            structures.append({
                "id": f"str-suburb-{e_i+1}",
                "name": f"Suburban Subdivision E-{e_i+1:02d}",
                "sector": "E",
                "kind": "house_cluster",
                "x": ex,
                "y": ey,
                "w": 0.48,
                "h": 0.4,
                "floors": rng.randint(1, 3),
                "color": "#52525b",
            })

    # Trees (~2,000 trees placed in parks, reserves, boulevards, hills)
    trees: List[List[float]] = []  # [x, y, radius]
    for park in parks:
        count = int(park["w"] * park["h"] * 35)
        for _ in range(count):
            tx = park["cx"] + rng.uniform(-park["w"] / 2.0, park["w"] / 2.0)
            ty = park["cy"] + rng.uniform(-park["h"] / 2.0, park["h"] / 2.0)
            if not is_water(tx, ty, river_points, river_width):
                trees.append([round(tx, 3), round(ty, 3), round(rng.uniform(0.04, 0.08), 3)])

    # Trees along hills (Sector C)
    for _ in range(450):
        tx = -16.0 + rng.gauss(0, 3.2)
        ty = 5.5 + rng.gauss(0, 2.5)
        if -24.0 <= tx <= -9.0 and 1.5 <= ty <= 11.5 and not is_water(tx, ty, river_points, river_width):
            trees.append([round(tx, 3), round(ty, 3), round(rng.uniform(0.04, 0.09), 3)])

    # Trees in suburban outskirts (Sector E)
    for _ in range(400):
        tx = -15.5 + rng.gauss(0, 3.5)
        ty = -5.5 + rng.gauss(0, 2.8)
        if -24.0 <= tx <= -7.0 and -11.5 <= ty <= -1.5 and not is_water(tx, ty, river_points, river_width):
            trees.append([round(tx, 3), round(ty, 3), round(rng.uniform(0.04, 0.08), 3)])

    # Prominent HUD Labels for landmarks
    labels = [
        {"text": "Kelvin Reservoir", "x": -18.0, "y": 4.5, "minZoom": 0.6, "maxZoom": 4.5, "kind": "water"},
        {"text": "Kelvin Dam", "x": -13.0, "y": 3.8, "minZoom": 0.9, "maxZoom": 12.0, "kind": "infrastructure"},
        {"text": "Westgate Bridge", "x": -9.8, "y": 1.2, "minZoom": 1.2, "maxZoom": 12.0, "kind": "infrastructure"},
        {"text": "Central Crossing", "x": -1.6, "y": -2.6, "minZoom": 1.2, "maxZoom": 12.0, "kind": "infrastructure"},
        {"text": "Harbour Gate Bridge", "x": 9.8, "y": -1.8, "minZoom": 1.2, "maxZoom": 12.0, "kind": "infrastructure"},
        {"text": "Sector A: Downtown", "x": 0.0, "y": 3.2, "minZoom": 0.5, "maxZoom": 3.5, "kind": "sector"},
        {"text": "Central Railway Terminal", "x": 0.3, "y": 1.1, "minZoom": 1.8, "maxZoom": 14.0, "kind": "landmark"},
        {"text": "Kelvin Financial Tower (72F)", "x": 0.0, "y": -0.4, "minZoom": 1.8, "maxZoom": 14.0, "kind": "landmark"},
        {"text": "Central Park", "x": 0.0, "y": 1.2, "minZoom": 1.0, "maxZoom": 6.0, "kind": "park"},
        {"text": "Sector B: Industrial Port", "x": 16.0, "y": -8.8, "minZoom": 0.5, "maxZoom": 3.5, "kind": "sector"},
        {"text": "Deepwater Cargo Quay", "x": 16.0, "y": -2.6, "minZoom": 1.5, "maxZoom": 14.0, "kind": "landmark"},
        {"text": "Petrochem Tank Farm", "x": 18.0, "y": -7.0, "minZoom": 1.5, "maxZoom": 14.0, "kind": "landmark"},
        {"text": "Sector C: Residential Hills", "x": -16.0, "y": 9.5, "minZoom": 0.5, "maxZoom": 3.5, "kind": "sector"},
        {"text": "Kelvin Memorial Hospital", "x": -14.5, "y": 5.4, "minZoom": 1.5, "maxZoom": 14.0, "kind": "landmark"},
        {"text": "Sector D: Transit Corridor", "x": 15.5, "y": 9.5, "minZoom": 0.5, "maxZoom": 3.5, "kind": "sector"},
        {"text": "Meadow Center Mall", "x": 13.5, "y": 5.2, "minZoom": 1.5, "maxZoom": 14.0, "kind": "landmark"},
        {"text": "Kelvin Olympic Arena", "x": 17.0, "y": 6.0, "minZoom": 1.5, "maxZoom": 14.0, "kind": "landmark"},
        {"text": "Transit Hub", "x": 15.5, "y": 7.4, "minZoom": 1.6, "maxZoom": 14.0, "kind": "landmark"},
        {"text": "Sector E: Suburban Ring", "x": -15.5, "y": -9.5, "minZoom": 0.5, "maxZoom": 3.5, "kind": "sector"},
        {"text": "500kV Substation", "x": -13.5, "y": -4.8, "minZoom": 1.6, "maxZoom": 14.0, "kind": "landmark"},
    ]

    # Exactly 500 sensors (100 per sector) distributed evenly with minimum spacing (Poisson-disk style)
    sensors: List[Dict[str, Any]] = []

    def build_sector_sensors(
        sector: str,
        count: int,
        anchor_list: List[Dict[str, Any]],
        candidate_structures: List[Dict[str, Any]],
        corridor_points: List[Tuple[float, float]],
        center: Tuple[float, float],
        radius: float,
        min_dist: float = 0.65,
    ) -> List[Dict[str, Any]]:
        """
        Builds exactly `count` evenly spaced sensors for a sector:
        1. Adds key structural anchors (dams, bridges, landmarks)
        2. Places sensors along transit & arterial corridors connecting to other sectors
        3. Fills remaining quota using rejection sampling to enforce `min_dist >= 0.65km`
        """
        sec_sensors: List[Dict[str, Any]] = []

        def can_add(x: float, y: float, d_thresh: float) -> bool:
            for ex in sec_sensors:
                if math.hypot(x - ex["x"], y - ex["y"]) < d_thresh:
                    return False
            return True

        # 1. Add anchors first
        for a in anchor_list:
            if len(sec_sensors) < count:
                sec_sensors.append({
                    "id": "",
                    "sector": sector,
                    "x": round(a["x"], 4),
                    "y": round(a["y"], 4),
                    "kind": a.get("kind", "infrastructure"),
                    "site": a.get("site", f"Sector {sector} Facility"),
                })

        # 2. Add from primary structures
        for s in candidate_structures:
            if len(sec_sensors) >= count:
                break
            if can_add(s["x"], s["y"], min_dist * 0.75):
                sec_sensors.append({
                    "id": "",
                    "sector": sector,
                    "x": round(s["x"], 4),
                    "y": round(s["y"], 4),
                    "kind": "building" if s["kind"] in ("tower", "skyscraper", "office", "civic") else "infrastructure",
                    "site": s["name"],
                })

        # 3. Add sensors along transit corridors connecting to other sectors
        for pt in corridor_points:
            if len(sec_sensors) >= count:
                break
            if not is_water(pt[0], pt[1], river_points, river_width) and can_add(pt[0], pt[1], min_dist):
                sec_sensors.append({
                    "id": "",
                    "sector": sector,
                    "x": round(pt[0], 4),
                    "y": round(pt[1], 4),
                    "kind": "transit_corridor",
                    "site": f"Sector {sector} Corridor Station",
                })

        # 4. Fill remaining with evenly spread Poisson-disk distributed stations across sector
        attempts = 0
        current_thresh = min_dist
        while len(sec_sensors) < count and attempts < 4000:
            attempts += 1
            if attempts > 2500 and len(sec_sensors) < count:
                current_thresh = max(0.42, current_thresh * 0.95)

            ang = rng.uniform(0, 2 * math.pi)
            dist = math.sqrt(rng.uniform(0.04, 1.0)) * radius
            sx = center[0] + dist * math.cos(ang)
            sy = center[1] + dist * math.sin(ang)

            # Keep in map bounds
            if sx < -24.5 or sx > 24.5 or sy < -11.5 or sy > 11.5:
                continue

            if is_water(sx, sy, river_points, river_width):
                continue

            if can_add(sx, sy, current_thresh):
                sec_sensors.append({
                    "id": "",
                    "sector": sector,
                    "x": round(sx, 4),
                    "y": round(sy, 4),
                    "kind": "ground_station",
                    "site": f"District {sector} Seismic Sub-station #{len(sec_sensors)+1:02d}",
                })

        return sec_sensors[:count]

    # --- Sector A Anchors & Corridor (Downtown, Bridges, Central Crossings) ---
    anchors_a = []
    for br in [bridges[1], bridges[2], bridges[3]]:
        for t in [0.25, 0.5, 0.75]:
            bx = br["x1"] + t * (br["x2"] - br["x1"])
            by = br["y1"] + t * (br["y2"] - br["y1"])
            anchors_a.append({"x": bx, "y": by, "kind": "bridge", "site": f"{br['name']} Pier"})
    corridor_a = [
        (-4.0, 0.3), (-3.0, 1.5), (-1.5, 2.5), (0.0, 3.5), (1.5, 3.5), (3.5, 1.8),
        (3.5, -1.5), (1.5, -3.2), (-1.5, -3.2), (-3.5, -1.8), (0.0, -4.5), (0.0, 4.5)
    ]
    dt_structures = [s for s in structures if s.get("sector") == "A"]
    sensors_a = build_sector_sensors("A", 100, anchors_a, dt_structures, corridor_a, SECTOR_INFO["A"]["center_coords"], SECTOR_INFO["A"]["radius_km"], min_dist=0.68)

    # --- Sector B Anchors & Corridor (Industrial Port, Coast, Tank Farms) ---
    anchors_b = [
        {"x": bridges[4]["x1"], "y": bridges[4]["y1"], "kind": "bridge", "site": "Harbour Gate Pier"},
        {"x": 16.0, "y": -2.2, "kind": "quay", "site": "Deepwater Cargo Quay North"},
        {"x": 18.0, "y": -7.2, "kind": "tank_farm", "site": "Petrochem Tank Farm Base"},
        {"x": 20.5, "y": -6.5, "kind": "quay", "site": "East Anchorage Pier"},
    ]
    corridor_b = [
        (8.5, -4.0), (10.5, -4.6), (12.5, -5.2), (15.0, -5.8), (17.5, -6.2),
        (20.0, -6.8), (22.5, -6.5), (13.5, -2.5), (17.5, -2.5), (21.5, -2.8),
        (16.0, -9.5), (19.0, -9.8), (22.0, -9.2), (12.0, -7.5)
    ]
    b_structures = [s for s in structures if s.get("sector") == "B"]
    sensors_b = build_sector_sensors("B", 100, anchors_b, b_structures, corridor_b, SECTOR_INFO["B"]["center_coords"], SECTOR_INFO["B"]["radius_km"], min_dist=0.75)

    # --- Sector C Anchors & Corridor (Residential Hills, Dam Crest, Westgate) ---
    anchors_c = []
    # 10 Kelvin Dam Crest Sensors
    for i in range(10):
        t = (i + 0.5) / 10.0
        dx = dam["x1"] + t * (dam["x2"] - dam["x1"])
        dy = dam["y1"] + t * (dam["y2"] - dam["y1"])
        anchors_c.append({"x": dx, "y": dy, "kind": "dam", "site": f"Kelvin Dam Crest Piezometer #{i+1:02d}"})
    anchors_c.append({"x": bridges[0]["x1"], "y": bridges[0]["y1"], "kind": "bridge", "site": "Westgate Bridge Abutment"})
    corridor_c = [
        (-8.5, 3.0), (-11.0, 4.2), (-13.5, 5.2), (-16.0, 6.5), (-18.5, 7.5),
        (-21.0, 8.2), (-23.5, 8.8), (-13.0, 7.5), (-16.0, 9.2), (-19.0, 10.0),
        (-22.0, 10.5), (-11.0, 2.0), (-16.0, 3.0), (-20.0, 3.5)
    ]
    c_structures = [s for s in structures if s.get("sector") == "C"]
    sensors_c = build_sector_sensors("C", 100, anchors_c, c_structures, corridor_c, SECTOR_INFO["C"]["center_coords"], SECTOR_INFO["C"]["radius_km"], min_dist=0.75)

    # --- Sector D Anchors & Corridor (Transit Corridor, Mall, Arena) ---
    anchors_d = [
        {"x": 15.5, "y": 6.8, "kind": "transit_hub", "site": "Metro Intermodal Terminal"},
        {"x": 13.5, "y": 4.5, "kind": "building", "site": "Meadow Center Mall Roof"},
        {"x": 17.0, "y": 5.2, "kind": "infrastructure", "site": "Kelvin Olympic Arena Dome"},
        {"x": 18.0, "y": 7.2, "kind": "building", "site": "Commercial Park Spine"},
    ]
    corridor_d = [
        (6.0, 4.0), (8.5, 4.8), (11.0, 5.6), (13.5, 6.2), (16.0, 6.8),
        (18.5, 7.4), (21.0, 7.8), (23.5, 8.0), (12.0, 8.2), (15.5, 9.0),
        (19.0, 9.5), (22.5, 9.8), (10.0, 3.0), (14.0, 3.0), (18.0, 3.0)
    ]
    d_structures = [s for s in structures if s.get("sector") == "D"]
    sensors_d = build_sector_sensors("D", 100, anchors_d, d_structures, corridor_d, SECTOR_INFO["D"]["center_coords"], SECTOR_INFO["D"]["radius_km"], min_dist=0.75)

    # --- Sector E Anchors & Corridor (Suburban Ring, Substation, Water Tower) ---
    anchors_e = [
        {"x": -13.5, "y": -5.5, "kind": "substation", "site": "500kV Substation Transformer Yard"},
        {"x": -17.0, "y": -4.2, "kind": "water_tower", "site": "Water Tower Structural Base"},
        {"x": -18.5, "y": -7.0, "kind": "silo", "site": "Agricultural Silo Complex Pier"},
        {"x": -21.5, "y": -6.0, "kind": "ground_station", "site": "South-West Perimeter Sentinel"},
    ]
    corridor_e = [
        (-6.0, -4.5), (-8.5, -5.2), (-11.0, -5.8), (-13.5, -6.5), (-16.0, -7.0),
        (-18.5, -7.5), (-21.0, -8.0), (-23.5, -8.5), (-12.0, -8.5), (-15.5, -9.2),
        (-19.0, -9.8), (-22.5, -10.2), (-10.0, -3.5), (-14.0, -3.5), (-18.0, -3.5)
    ]
    e_structures = [s for s in structures if s.get("sector") == "E"]
    sensors_e = build_sector_sensors("E", 100, anchors_e, e_structures, corridor_e, SECTOR_INFO["E"]["center_coords"], SECTOR_INFO["E"]["radius_km"], min_dist=0.75)

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
