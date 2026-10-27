# Case Study: City-Wide Seismic & Structural Health Monitoring Network

## 1. Context & Motivation
Urban centers in seismically active regions rely on continuous vibration monitoring across buildings, bridges, and geological fault lines. Accelerometers positioned on structural members measure ground and floor acceleration to evaluate structural fatigue and provide immediate post-earthquake damage assessments.

Modern high-sensitivity accelerometers sample at high frequencies (typically 1,000 Hz) to capture high-frequency wave arrivals ($P$-waves and $S$-waves).

---

## 2. The Computational Challenge: The Flaw of Static Infrastructure

1. **Bandwidth & Compute Waste:**
   Continuously streaming raw tri-axial 1,000 Hz data from 500 monitoring stations produces over **1.5 million data points per second** ($500 \times 3 \times 1{,}000$). Doing this 24/7 saturates cellular backhauls, generates massive database storage bills, and wastes cloud compute during weeks of calm baseline conditions.

2. **The Burst Dilemma:**
   When an earthquake strikes or a tremor occurs:
   * Ambient ground acceleration crosses trigger thresholds ($> 0.05\,\text{g}$).
   * All 500 stations switch simultaneously from quiet summary reporting (1 packet/min) to raw waveform streaming (10+ packets/sec).
   * **Result:** Traffic to the cloud ingestion layer spikes by **5,000% within 2 seconds**.

3. **Infrastructure Failures in Traditional Systems:**
   * **Monolith / Fixed Capacity:** Fixed-size virtual servers or load balancers get overwhelmed immediately. Requests queue up, memory exhausts, and the ingestion API crashes just when data collection is most critical.
   * **Data Loss on Reconnection:** Earthquakes frequently knock out cellular towers. When connectivity is restored, sensors dump buffered backlogs simultaneously ("reconnect storm"), creating a secondary shockwave for the ingestion servers.

---

## 3. The Cloud-Native Solution

This project solves the challenge through a resilient, decoupled, cloud-native architecture:

1. **Dual-Mode Edge Emulation:** 
   Nodes transmit lightweight statistical summaries during quiescent periods and high-resolution waveforms only during detected tremors.
2. **Decoupled Asynchronous Buffering (RabbitMQ):**
   Incoming HTTP requests are quickly accepted, validated, and pushed to a persistent queue. The Ingest API responds with `202 Accepted` in under 10ms, decoupling edge transmission from database writes.
3. **Horizontal Pod Autoscaling (Kubernetes HPA):**
   As CPU utilization exceeds 60% due to packet deserialization and validation, Kubernetes dynamically scales Ingest and Processor pods from **2 up to 10 replicas**, sharing the load across the cluster.
4. **Independent Priority Queues:**
   Live earthquake telemetry is processed with high priority, while reconnection backlog data (`is_backfill=true`) is funneled into a separate queue to prevent historical data from delaying real-time emergency alerts.
5. **Self-Healing Resilience:**
   If a processing container crashes due to memory pressure or unhandled exceptions, Kubernetes automatically detects the failure via liveness probes and spins up a healthy replacement pod instantly.
