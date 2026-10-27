# City Seismic Simulation Controller & Dashboard

## 1. Overview & Purpose
This document specifies the design and implementation of the **City-Wide Virtual Seismic Simulation Engine & Control Dashboard**. 

In place of physical ESP32 microcontrollers, the edge layer is modeled as an interactive, simulated fleet of **500 virtual seismic sensor nodes** deployed across a metropolitan area. This architecture eliminates physical hardware bottlenecks, guarantees 100% demo reproducibility, and allows on-demand triggering of real-world load patterns (earthquakes, network blackouts, reconnection storms) to test Kubernetes autoscaling (HPA) and self-healing.

---

## 2. City Grid & Virtual Fleet Specification

### 2.1 Geographic Sectors
The 500 virtual sensor stations are distributed across five metropolitan zones:
* **Sector A - Downtown & High-Rise District (Nodes 001–100):** High structural density, accelerated vibration monitoring.
* **Sector B - Industrial & Port Zone (Nodes 101–200):** Heavy machinery baseline noise, waterfront soil conditions.
* **Sector C - Residential Hills (Nodes 201–300):** Low baseline ambient noise, susceptible to seismic amplification.
* **Sector D - Transit & Infrastructure Corridor (Nodes 301–400):** Bridges, highways, and tunnels with periodic traffic vibration.
* **Sector E - Outlying Suburban Ring (Nodes 401–500):** Sparse perimeter stations for early-warning shockwave detection.

### 2.2 Node Emulation Profiles
Each virtual node is an asynchronous worker running within a Python `asyncio` fleet manager:
* **Unique Node ID:** e.g., `seismic-node-042`
* **Assigned Coordinates:** `(x, y)` relative to city center.
* **Operating States:**
  1. **Quiescent (Summary Mode):** Node samples at 1,000 Hz locally, computes statistical summary (Peak Ground Acceleration `pga`, Root-Mean-Square `rms`, temperature/health) and transmits **one 200-byte summary packet every 60 seconds**.
  2. **Triggered (Event Mode):** Ground motion exceeds threshold ($> 0.05\,\text{g}$). The node switches to streaming high-resolution 1,000 Hz raw waveform windows (100 samples per batch, 10 batches/sec = 10 req/sec per triggered node).
  3. **Severed Link (Buffering Mode):** Simulates cellular/Wi-Fi tower failure. Node buffers telemetry in a capped circular memory queue (up to 5,000 samples).
  4. **Backlog Flush (Reconnecting):** Network restored. Dumps queued historical data to the Ingest API with `is_backfill: true` at full network speed.

---

## 3. Simulation Control Dashboard

The dashboard is a lightweight, responsive web interface served directly from the Python simulator (via FastAPI + WebSockets), accessible locally at `http://localhost:8080`.

### 3.1 Control Capabilities
1. **Earthquake Event Generator:**
   * **Epicenter Selector:** Choose sector (A through E) or click anywhere on the city map.
   * **Magnitude Slider:** 3.0 to 7.5 Richter scale. Determines propagation radius and wave amplitude.
   * **Trigger Button:** Generates a seismic wave that expands outward from the epicenter. Nodes switch from Green to Red as the wave reaches their coordinates, creating a realistic cascading traffic surge.
2. **Network Disruption Simulator:**
   * **Kill Sector Network:** Simulates localized telecommunications outage (nodes turn Yellow and buffer).
   * **Restore Network:** Triggers an immediate "Reconnection Storm" to test RabbitMQ backpressure and database ingestion without dropping live telemetry.
3. **Thundering Herd / Jitter Toggle:**
   * **Jitter OFF:** All 500 nodes align their 60-second summary report to exact minute boundaries (`:00`), inducing sharp periodic traffic spikes.
   * **Jitter ON:** Reports are uniformly distributed across the 60-second window, flattening baseline load.
4. **Fleet Scale Slider:**
   * Dynamically adjust active nodes between 50 and 500 to evaluate baseline cloud cost and resource usage.

### 3.2 Visual Interface Layout

```
+----------------------------------------------------------------------------------------------------+
|  CITY SEISMIC SIMULATION CONTROLLER                                           Status: CONNECTED    |
+----------------------------------------------------------------------------------------------------+
|  [Fleet: 500 Nodes]   [Ingest Target: http://localhost:8000]   [Outgoing Rate: 1,420 msgs/sec]     |
|                                                                                                    |
|  SCENARIO INJECTION:                                                                               |
|  [ Trigger Minor Tremor (M3.5) ]  [ Trigger Major Quake (M6.8) ]  [ Reset Fleet to Baseline ]      |
|  [ Cut Sector B Network        ]  [ Reconnect & Flush Backfill ]  [ Jitter: [ ON / OFF ] ]         |
+----------------------------------------------------------------------------------------------------+
|  METROPOLITAN SENSOR MATRIX (500 Nodes):                                                           |
|                                                                                                    |
|  Sector A (Downtown)    [●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●]                |
|  Sector B (Industrial)  [●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●]                |
|  Sector C (Residential) [●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●]                |
|  Sector D (Transit)     [●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●]                |
|  Sector E (Suburbs)     [●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●][●]                |
|                                                                                                    |
|  Legend: [● Green: Quiescent Summary]  [● Red: Active Quake Event]  [● Yellow: Backlog Buffering]  |
+----------------------------------------------------------------------------------------------------+
|  LIVE TELEMETRY STREAM & CLUSTER REACTION:                                                         |
|  [ Active Pods: 8 ]   [ Ingest CPU: 68% ]   [ Queue Depth: 4,120 msgs ]   [ Latency: 42ms ]         |
+----------------------------------------------------------------------------------------------------+
```

---

## 4. Cloud Infrastructure Mapping

This dashboard directly triggers and verifies the evaluation criteria outlined in the course proposal:

| Dashboard Action | Cloud / Cluster Phenomenon Triggered | Verifiable Success Metric |
| :--- | :--- | :--- |
| **Major Quake Trigger** | Traffic jumps from ~8 req/sec to 2,000+ req/sec. | Ingest API CPU $> 60\%$. HPA scales pods from 2 to 10 replicas. |
| **Reset Fleet** | Traffic drops back to quiescent baseline. | Scale-in cooldown engages. Pods safely scale down to 2 after ~5 min. |
| **Network Reconnect** | 50,000 buffered backfill packets arrive simultaneously. | Ingest API routes to `backfill_queue`; `live_queue` maintains sub-50ms latency. |
| **Pod Kill (Manual)** | One of the Ingest or Processor pods is terminated mid-burst. | Kubernetes replica controller auto-restarts pod; 0 HTTP 500 errors. |
| **Jitter OFF** | 500 nodes report at the same second. | Micro-burst absorption tested in RabbitMQ queue buffer. |

---

## 5. Technology Stack & Execution
* **Backend:** Python 3.11+, `asyncio`, `aiohttp` / `httpx` (for high-concurrency non-blocking HTTP requests).
* **Control Server:** `FastAPI` (serves the dashboard endpoints and WebSocket event stream).
* **Frontend:** Single-page dashboard built with modern vanilla HTML, CSS (clean dark mode, responsive grid), and JavaScript WebSockets.
* **Portability:** Runs locally on the laptop outside the cluster or can be deployed into Kubernetes as a load-testing Job (`Z26`).
