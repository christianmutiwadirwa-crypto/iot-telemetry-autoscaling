/**
 * Application Orchestrator & Telemetry Stream Manager
 * Connects UI controls, WebSocket streaming, MetroMap, Seismograph, and Audio.
 */

document.addEventListener("DOMContentLoaded", async () => {
    // 1. Initialize Seismograph
    const seismo = new Seismograph("seismo-canvas");

    // State
    let currentEpicenter = [0.0, 0.3];
    let isSectorBCut = false;
    let isScenarioPlaying = false;
    let ws = null;
    let wsRetryTimeout = null;

    // 2. Initialize MetroMap
    const metroMap = new MetroMap("city-canvas", {
        onSelectStation: (sensor) => {
            seismo.setStation(sensor.id, sensor.site, sensor.sector);
            document.getElementById("seismo-station-id").textContent = sensor.id;
            document.getElementById("seismo-site-name").textContent = sensor.site || `Sector ${sensor.sector}`;

            // Send subscription update over WebSocket
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: "select", node_id: sensor.id }));
            }
        },
        onSetEpicenter: (wx, wy) => {
            currentEpicenter = [Math.round(wx * 10) / 10, Math.round(wy * 10) / 10];
            // If earthquake already ongoing, update it immediately
            const mag = parseFloat(document.getElementById("slider-mag").value) || 6.5;
            triggerEarthquake(mag, currentEpicenter);
        },
    });

    // Fetch and apply city layout
    try {
        const resp = await fetch("/api/city/layout");
        if (resp.ok) {
            const layout = await resp.json();
            metroMap.setLayout(layout);
        }
    } catch (e) {
        console.error("Failed to load city layout:", e);
    }

    // 3. Audio Controller
    const btnSound = document.getElementById("btn-sound-toggle");
    const soundLabel = document.getElementById("sound-label");
    let soundEnabled = false;

    btnSound.addEventListener("click", () => {
        soundEnabled = !soundEnabled;
        window.seismicAudio.setEnabled(soundEnabled);
        btnSound.classList.toggle("active", soundEnabled);
        soundLabel.textContent = soundEnabled ? "Sound on" : "Sound muted";
    });

    // 4. WebSocket Streaming Connection
    function connectWebSocket() {
        if (wsRetryTimeout) clearTimeout(wsRetryTimeout);

        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log("WebSocket telemetry stream connected.");
            // Subscribe to current station
            if (seismo.currentStationId) {
                ws.send(JSON.stringify({ type: "select", node_id: seismo.currentStationId }));
            }
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === "wave") {
                    // Fast wave packet (10 Hz)
                    seismo.pushData(msg.x || [], msg.y || [], msg.z || [], msg.peak_g || 0.0);
                    document.getElementById("seismo-pga").textContent = `${(msg.peak_g || 0.0).toFixed(3)} g`;
                    if (window.seismicAudio) {
                        window.seismicAudio.updateShakeLevel(msg.peak_g || 0.0);
                    }
                } else if (msg.type === "snapshot" && msg.data) {
                    // Full snapshot packet (2 Hz)
                    handleSnapshot(msg.data);
                }
            } catch (err) {
                console.error("Error parsing WS packet:", err);
            }
        };

        ws.onclose = () => {
            wsRetryTimeout = setTimeout(connectWebSocket, 1500);
        };

        ws.onerror = () => {
            if (ws) ws.close();
        };
    }

    connectWebSocket();

    // 5. Snapshot Data Dispatch
    function handleSnapshot(snap) {
        metroMap.updateSnapshot(snap);

        // Header pills
        if (snap.ingest_url) {
            document.getElementById("pill-ingest-target").textContent = `Ingest target ${snap.ingest_url.replace("http://", "").replace("/api/v1/telemetry", "")}`;
        }
        if (snap.scenario) {
            const sc = snap.scenario;
            isScenarioPlaying = sc.is_running;
            const desc = sc.current_description || (sc.is_running ? "Scenario active" : "quiescent baseline");
            document.getElementById("pill-scenario-phase").textContent = `Scenario: ${desc}`;
            document.getElementById("btn-scenario-toggle").textContent = sc.is_running ? "⏹ Stop scenario" : "▶ Play scenario";
        }

        // Top 4 KPI Cards
        const rps = snap.current_rps || 0.0;
        document.getElementById("kpi-throughput").textContent = rps.toFixed(1);

        const totalActive = snap.active_nodes_count || 500;
        const shaking = snap.triggered_nodes_count || 0;
        const buffering = snap.buffering_nodes_count || 0;
        const normal = Math.max(0, totalActive - shaking - buffering);

        document.getElementById("kpi-fleet-total").textContent = totalActive;
        document.getElementById("kpi-normal-count").textContent = `${normal} normal`;
        document.getElementById("kpi-shaking-count").textContent = `${shaking} shaking`;
        document.getElementById("kpi-buffering-count").textContent = `${buffering} buffering`;

        const stats = snap.stats || {};
        const totalBatches = stats.total_sent || 0;
        const summaries = stats.summaries_sent || 0;
        const waveforms = stats.waveforms_sent || 0;
        const rateLimits = stats.rate_limited_429 || 0;

        document.getElementById("kpi-batches-total").textContent = totalBatches.toLocaleString();
        document.getElementById("kpi-summaries-count").textContent = summaries.toLocaleString();
        document.getElementById("kpi-waveforms-count").textContent = waveforms.toLocaleString();

        const flushed = stats.backfill_sent || 0;
        const memBuffer = snap.total_buffered_batches || 0;
        document.getElementById("kpi-flushed-count").textContent = flushed.toLocaleString();
        document.getElementById("kpi-buffered-count").textContent = memBuffer.toLocaleString();
        document.getElementById("kpi-rate-limits").textContent = rateLimits.toLocaleString();

        // Cluster Telemetry (AKS)
        if (snap.cluster) {
            const cl = snap.cluster;
            document.getElementById("cluster-pods-val").textContent = `${cl.ready_pods} / ${cl.max_pods}`;
            document.getElementById("cluster-status-badge").textContent = cl.status;

            // Update 10 pod segments
            const podBar = document.getElementById("pod-segments");
            const segs = podBar.children;
            for (let i = 0; i < 10; i++) {
                if (i < cl.ready_pods) {
                    segs[i].className = "pod-seg active";
                } else if (i < cl.replicas) {
                    segs[i].className = "pod-seg starting";
                } else {
                    segs[i].className = "pod-seg";
                }
            }

            // Queue depth meter (0 - 5000)
            document.getElementById("cluster-queue-val").textContent = cl.queue_depth.toLocaleString();
            const queuePct = Math.min(100, (cl.queue_depth / 2000) * 100);
            document.getElementById("meter-queue").style.width = `${queuePct}%`;

            // DB writes meter (0 - 4500)
            document.getElementById("cluster-db-val").textContent = cl.db_writes_per_sec.toLocaleString();
            const dbPct = Math.min(100, (cl.db_writes_per_sec / 4000) * 100);
            document.getElementById("meter-db").style.width = `${Math.max(4, dbPct)}%`;
        }
    }

    // 6. Action Button Handlers
    async function triggerEarthquake(magnitude, epicenter) {
        try {
            const resp = await fetch("/api/scenario/earthquake", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    magnitude: magnitude,
                    epicenter_x: epicenter[0],
                    epicenter_y: epicenter[1],
                    duration_s: 30.0,
                }),
            });
            if (resp.ok) {
                window.seismicAudio.triggerEarthquake(magnitude);
            }
        } catch (e) {
            console.error("Failed to trigger earthquake:", e);
        }
    }

    document.getElementById("btn-trigger-quake").addEventListener("click", () => {
        const mag = parseFloat(document.getElementById("slider-mag").value) || 6.5;
        triggerEarthquake(mag, currentEpicenter);
    });

    document.getElementById("slider-mag").addEventListener("input", (e) => {
        document.getElementById("val-mag").textContent = parseFloat(e.target.value).toFixed(1);
    });

    document.getElementById("btn-clear-quake").addEventListener("click", async () => {
        try {
            await fetch("/api/scenario/clear", { method: "POST" });
            window.seismicAudio.stopEarthquake();
        } catch (e) {
            console.error("Failed to clear quake:", e);
        }
    });

    const btnNet = document.getElementById("btn-network-toggle");
    btnNet.addEventListener("click", async () => {
        isSectorBCut = !isSectorBCut;
        btnNet.textContent = isSectorBCut ? "Restore link" : "Sever link";
        btnNet.classList.toggle("btn-danger", isSectorBCut);
        try {
            await fetch("/api/scenario/network", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ sector: "B", online: !isSectorBCut }),
            });
        } catch (e) {
            console.error("Failed to toggle network:", e);
        }
    });

    // Sector quick zoom chips
    const sectorViews = {
        all: { x: 0.0, y: 0.0, z: 1.0 },
        A: { x: 0.0, y: 0.3, z: 3.4 },       // Downtown
        B: { x: 7.0, y: -5.0, z: 2.7 },      // Industrial & Port
        C: { x: -6.2, y: 4.5, z: 2.3 },      // Kelvin Dam & Residential Hills
        D: { x: 5.5, y: 5.5, z: 2.8 },       // Transit Corridor & Meadow Mall
        E: { x: -8.2, y: -5.6, z: 2.3 },     // Suburban Ring
    };

    document.querySelectorAll(".sector-chips .chip").forEach((chip) => {
        chip.addEventListener("click", () => {
            document.querySelectorAll(".sector-chips .chip").forEach(c => c.classList.remove("active"));
            chip.classList.add("active");
            const target = sectorViews[chip.dataset.zoom] || sectorViews.all;
            metroMap.flyTo(target.x, target.y, target.z);
        });
    });

    // Zoom Buttons
    document.getElementById("btn-zoom-in").addEventListener("click", () => metroMap.zoomIn());
    document.getElementById("btn-zoom-out").addEventListener("click", () => metroMap.zoomOut());
    document.getElementById("btn-zoom-reset").addEventListener("click", () => {
        document.querySelectorAll(".sector-chips .chip").forEach(c => c.classList.remove("active"));
        document.querySelector(".sector-chips .chip[data-zoom='all']").classList.add("active");
        metroMap.resetView();
    });

    // Fleet Size Slider
    const sliderFleet = document.getElementById("slider-fleet");
    const valFleet = document.getElementById("fleet-size-val");
    let fleetDebounce = null;

    sliderFleet.addEventListener("input", (e) => {
        valFleet.textContent = e.target.value;
        if (fleetDebounce) clearTimeout(fleetDebounce);
        fleetDebounce = setTimeout(async () => {
            try {
                await fetch("/api/scenario/fleet-size", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ target_nodes: parseInt(e.target.value, 10) }),
                });
            } catch (err) {
                console.error("Failed to set fleet size:", err);
            }
        }, 300);
    });

    // Jitter Toggle
    document.getElementById("chk-jitter").addEventListener("change", async (e) => {
        try {
            await fetch("/api/scenario/jitter", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ enabled: e.target.checked }),
            });
        } catch (err) {
            console.error("Failed to set jitter:", err);
        }
    });

    // Scenario Play/Stop Button
    const btnScenario = document.getElementById("btn-scenario-toggle");
    btnScenario.addEventListener("click", async () => {
        const action = isScenarioPlaying ? "stop" : "start";
        try {
            await fetch(`/api/scenario/timeline/${action}`, { method: "POST" });
        } catch (e) {
            console.error("Failed to toggle scenario:", e);
        }
    });
});
