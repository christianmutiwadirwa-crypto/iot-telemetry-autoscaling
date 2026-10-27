# Scenario Timeline & Cluster Sizing Guide (Task K8)

This document defines the official **minute-by-minute simulation scenario timeline** and the corresponding **capacity sizing calculations** for both the local (`kind`) cluster and the cloud (`AKS`) deployment.

---

## 1. Scenario Overview

The scenario runs over a **25-minute test lifecycle** designed to thoroughly evaluate system elasticity, priority queuing, backpressure, and self-healing:

```
[00:00 - 05:00]  Phase 1: Baseline Quiescent Monitoring (Calm Day)
[05:00 - 07:00]  Phase 2: Localized Micro-Tremor (Sector C - Residential)
[07:00 - 10:00]  Phase 3: Inter-Event Calm & Baseline Return
[10:00 - 14:00]  Phase 4: Major City-Wide Earthquake (Magnitude 6.8 Surge)
[14:00 - 17:00]  Phase 5: Telecom Outage & Local Edge Buffering (Sector B)
[17:00 - 20:00]  Phase 6: Reconnection Storm & Backfill Queue Priority Drain
[20:00 - 25:00]  Phase 7: Quiescent Calming & HPA Scale-In Cooldown
```

---

## 2. Minute-by-Minute Timeline Table

| Time Window (MM:SS) | Scenario Event | Active Fleet State | Triggered Nodes | Payload Type | Request Rate (req/s) | Bandwidth (approx) | Expected Pod Replicas (Ingest / Proc) | Cluster & Queue Reaction |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **00:00 – 05:00** | **Phase 1: Normal Day Baseline** | All 500 nodes active across Sectors A–E | 0 nodes | `summary` (1 pkt/60s per node) | **~8.3 req/s** (with jitter) *(Spikes to 500 req/s at :00 if jitter OFF)* | ~1.7 KB/s (~100 KB/s spike) | **2 / 2** (Minimum replicas) | Low baseline CPU (<10%). RabbitMQ queue depth ~0. Sub-10ms response time. |
| **05:00 – 05:15** | **Phase 2: Localized Micro-Tremor (Onset)** | Ground acceleration >0.05g detected in Sector C | 100 nodes (Sector C) | `waveform` (10 req/s per node) + 400 nodes `summary` | **~1,007 req/s** | ~2.5 MB/s | **2 / 2** $\rightarrow$ Scaling to **3–4** | Ingest CPU climbs to ~45%. RabbitMQ `telemetry.live` absorbs the initial wave buffer. |
| **05:15 – 07:00** | **Phase 2: Tremor Dissipation** | Vibration subsides back below threshold | 100 nodes revert to `summary` | `summary` across all 500 nodes | **~8.3 req/s** | ~1.7 KB/s | **3–4** $\rightarrow$ Cooldown begins | Queue quickly drains to zero. Scale-down timer initialized. |
| **07:00 – 10:00** | **Phase 3: Calm Baseline** | Normal ambient noise | 0 nodes | `summary` | **~8.3 req/s** | ~1.7 KB/s | **2 / 2** | Pods scale down back to minimum base replica count (2). |
| **10:00 – 10:10** | **Phase 4: Major Earthquake (Wave Propagation)** | Shockwave originates in Sector A and propagates across city | 500 nodes cascade into trigger state | `waveform` | **Rapid ramp: 500 $\rightarrow$ 5,000 req/s** | **~12.5 MB/s** | **2 / 2** $\rightarrow$ **6 / 6** | Rapid CPU spike (>75%). HPA triggers horizontal pod scale-out across cluster. |
| **10:10 – 12:00** | **Phase 4: Sustained Severe Shaking** | All metropolitan sectors shaking severely | 500 nodes | `waveform` (100 samples/batch, 10 batches/s/node) | **5,000 req/s (Peak)** | **~12.5 MB/s** | **10 / 10** (Maximum replicas) | 10 Ingest pods process ~500 req/s each. CPU stabilizes around 55-65%. Zero 500 errors. |
| **12:00 – 14:00** | **Phase 4: Primary Event Decay** | Main shockwave ends; minor tremors remain | 500 $\rightarrow$ 50 nodes | Mixed (`waveform` & `summary`) | **~508 req/s** | ~1.3 MB/s | **10 / 10** | Load begins to drop. Replicas remain high during stabilization window. |
| **14:00 – 17:00** | **Phase 5: Telecom Outage (Cell Tower Down)** | Cellular link severed in Sector B (Industrial). Nodes buffer locally. | 400 nodes active online; 100 nodes buffering offline | `summary` from 400 online nodes | **~6.7 req/s** | ~1.4 KB/s | **10 / 10** $\rightarrow$ Scales in to **4 / 4** | Sector B nodes store up to 5,000 samples each in memory. Ingress traffic drops. |
| **17:00 – 17:30** | **Phase 6: Reconnection Storm (Flush)** | Sector B link restored; nodes flush buffered telemetry simultaneously | 100 Sector B nodes flushing + 400 online nodes | `is_backfill: true` batches + standard `summary` | **~2,500 – 4,000 req/s** (Backfill burst) | ~6.5 – 10 MB/s | **4 / 4** $\rightarrow$ Scales up to **7–8** | **Priority Queue Validation:** Ingest routes to `telemetry.backfill`. `telemetry.live` latency remains <50ms. Processor prioritizes live queue over backfill. |
| **17:30 – 20:00** | **Phase 6: Backfill Drain** | Backlog emptied; historical records ingested | 0 buffering nodes | `summary` | **~8.3 req/s** | ~1.7 KB/s | **7–8** $\rightarrow$ Cooldown begins | Backlog queue finishes draining to TimescaleDB with idempotent batch IDs (0 duplicate rows). |
| **20:00 – 25:00** | **Phase 7: Final Cooldown & Baseline** | City network fully normal | 0 nodes | `summary` | **~8.3 req/s** | ~1.7 KB/s | **2 / 2** (Fully scaled down) | HPA scale-down stabilization window expires. Replicas return to 2. Test successfully completed. |

---

## 3. Computational Load & Bandwidth Calculations

### 3.1 Payload Sizes
* **Quiescent Summary Payload:**
  * JSON body: ~200 bytes.
  * HTTP overhead + headers: ~300 bytes.
  * Total packet wire size: **~500 bytes**.
* **High-Resolution Waveform Batch (100 samples tri-axial):**
  * JSON body: ~2,000 bytes.
  * HTTP overhead + headers: ~500 bytes.
  * Total packet wire size: **~2.5 KB**.

### 3.2 Ingestion Throughput
* **Baseline Load (500 nodes in Summary Mode):**
  $$\text{Throughput} = \frac{500 \text{ requests}}{60 \text{ seconds}} \approx 8.33 \text{ req/s}$$
  $$\text{Bandwidth} = 8.33 \times 500 \text{ B} \approx 4.16 \text{ KB/s}$$
* **Peak Earthquake Load (500 nodes in Waveform Mode):**
  $$\text{Throughput} = 500 \text{ nodes} \times 10 \text{ req/s/node} = 5{,}000 \text{ req/s}$$
  $$\text{Bandwidth} = 5{,}000 \times 2.5 \text{ KB} = 12.5 \text{ MB/s} \approx 100 \text{ Mbps}$$
* **Reconnection Storm Backfill:**
  * 100 nodes $\times$ 500 batches buffered = 50,000 total batches.
  * Flushed over ~15 seconds: $50{,}000 / 15 \approx 3{,}333 \text{ req/s}$.

---

## 4. Kubernetes Cluster Sizing & Quota Alignment

### 4.1 Resource Allocation per Pod

| Service | CPU Request | CPU Limit | Memory Request | Memory Limit | Target Autoscaling Metric |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Ingest API** (FastAPI) | `100m` (0.1 core) | `500m` (0.5 core) | `128Mi` | `256Mi` | Target CPU: `60%` (Min: 2, Max: 10 replicas) |
| **Processor Worker** | `100m` (0.1 core) | `500m` (0.5 core) | `128Mi` | `256Mi` | Target CPU: `60%` (Min: 2, Max: 10 replicas) |
| **RabbitMQ** | `200m` | `1000m` (1.0 core) | `256Mi` | `512Mi` | Buffer queue during bursts |
| **TimescaleDB** | `250m` | `1000m` (1.0 core) | `256Mi` | `1024Mi` | Time-series hypertable storage |

### 4.2 Cloud Quota & Cost Protection (Azure Track)
* **Subscription:** Azure for Students ($100 credit limit).
* **Regional vCPU Quota:** Typically **4 vCPUs** per region for student subscriptions.
* **Recommended VM Node Sizing:**
  * **Option A (2-Node Cluster):** 2 $\times$ `Standard_B2s` (2 vCPUs, 4 GiB RAM each = 4 vCPUs total).
    * Cost: ~$0.0416/hr $\times$ 2 nodes $\approx$ **$0.083/hr** (~$2.00/day).
  * **Option B (Single Burstable Node for testing):** 1 $\times$ `Standard_B4ms` (4 vCPUs, 16 GiB RAM).
* **Local Cluster (`kind`):**
  * Configured as a 3-node local Kubernetes cluster (1 control-plane, 2 workers) running seamlessly inside Docker Desktop with no financial cost.

---

## 5. Experiment Verification Criteria

This timeline directly powers and validates the key experiments in the project roadmap:

1. **HPA Elasticity (`E1`, `E2`):** Verify Ingest and Processor scale from 2 to 10 replicas under 5,000 req/s, and scale back down after the 5-minute cooldown.
2. **Priority Queue Separation (`E3`):** During Phase 6, confirm `telemetry.live` latency remains $<50\text{ms}$ while the 50,000 backfill items are processed.
3. **Thundering Herd Mitigation (`E4`):** Compare jitter ON vs. jitter OFF during Phase 1 to visualize the 500 req/s micro-burst in Grafana.
4. **Idempotency & Resiliency (`E5`, `E6`):** Confirm zero duplicate rows in TimescaleDB despite retransmitted batch UUIDs, and zero dropped batches when an Ingest pod is killed mid-quake.
