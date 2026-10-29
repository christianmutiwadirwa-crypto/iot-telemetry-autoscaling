"""
Configuration constants and settings for the City Seismic Simulator.
"""

from typing import Dict, Tuple

# Ingestion Endpoint & Authentication
DEFAULT_INGEST_URL = "http://20.239.8.235:8000/api/v1/telemetry"
DEFAULT_API_KEY = "dev-secret-key-123"

# Sensor Sampling & Batching Parameters
SAMPLING_RATE_HZ = 1000
WAVEFORM_BATCH_SIZE = 100             # 100 samples per batch (10 batches/sec at 1,000 Hz)
SUMMARY_INTERVAL_SECONDS = 60        # Emit 1 summary every 60s during quiescent mode
SEISMIC_TRIGGER_THRESHOLD_G = 0.05   # Acceleration magnitude threshold triggering raw waveform mode

# Circular Memory Buffer for Offline Link
MAX_BUFFERED_BATCHES = 5000          # Capped circular queue size per disconnected node

# Sector Assignments and Coordinates (x, y in km relative to city center)
SECTOR_INFO: Dict[str, Dict] = {
    "A": {
        "name": "Downtown & High-Rise District",
        "node_range": (1, 100),
        "center_coords": (0.0, 0.0),
        "radius_km": 6.5,
        "soil_amplification": 1.1,
    },
    "B": {
        "name": "Industrial & Port Zone",
        "node_range": (101, 200),
        "center_coords": (16.0, -5.5),
        "radius_km": 8.0,
        "soil_amplification": 1.4,
    },
    "C": {
        "name": "Residential Hills & Kelvin Dam",
        "node_range": (201, 300),
        "center_coords": (-16.0, 5.5),
        "radius_km": 8.0,
        "soil_amplification": 1.25,
    },
    "D": {
        "name": "Transit & Infrastructure Corridor",
        "node_range": (301, 400),
        "center_coords": (15.5, 5.5),
        "radius_km": 7.8,
        "soil_amplification": 1.0,
    },
    "E": {
        "name": "Outlying Suburban Ring",
        "node_range": (401, 500),
        "center_coords": (-15.5, -5.5),
        "radius_km": 7.8,
        "soil_amplification": 0.9,
    },
}

TOTAL_NODES = 500
