/**
 * Metro Seismic Command Dashboard Application
 * Connects UI widgets, WebSockets, Living City Canvas, and Seismograph.
 */

document.addEventListener("DOMContentLoaded", async () => {
    // 1. Initialize Subsystems
    const metroMap = new MetroMap("city-canvas", {
        onSelectStation: (sensor) => {
            seismo.selectStation(sensor.id, sensor.site);
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: "select", node_id: sensor.id }));
            }
        },
        onSetEpicenter: (x, y) => {
            currentEpicenter = [x, y];
            triggerEarthquake(parseFloat(document.getElementById("slider-mag").value) || 6.5, currentEpicenter);
        },
    });

    const seismo = new Seismograph("seismo-canvas");
    
    // Safely initialize or reference seismicAudio
    if (!window.seismicAudio) {
        if (typeof SeismicAudioEngine !== "undefined") {
            window.seismicAudio = new SeismicAudioEngine();
        } else if (typeof SeismicAudio !== "undefined") {
            window.seismicAudio = new SeismicAudio();
        }
    }

    let currentEpicenter = [0.0, 0.0];
    let isSectorBCut = false;
    let isScenarioPlaying = false;
    let ws = null;
    let wsRetryTimeout = null;

    // 2. Load Geography & Layout
    try {
        const layoutResp = await fetch("/api/city/layout");
        const layout = await layoutResp.json();
        metroMap.setLayout(layout);
    } catch (e) {
        console.error("Failed to load city layout:", e);
    }

    // 3. Audio Toggle
    const soundBtn = document.getElementById("btn-sound-toggle");
    if (soundBtn) {
        soundBtn.addEventListener("click", () => {
            if (!window.seismicAudio) return;
            const enabled = window.seismicAudio.toggle();
            soundBtn.classList.toggle("btn-outline", !enabled);
            soundBtn.classList.toggle("btn-active", enabled);
            document.getElementById("sound-label").textContent = enabled ? "Sound on" : "Sound off";
            soundBtn.querySelector(".sound-icon").textContent = enabled ? "🔊" : "🔇";
        });
    }

    // 4. WebSocket Streaming Connection
    function connectWebSocket() {
        if (wsRetryTimeout) clearTimeout(wsRetryTimeout);

        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log("WebSocket telemetry stream connected.");
            if (seismo.currentStationId) {
                ws.send(JSON.stringify({ type: "select", node_id: seismo.currentStationId }));
            }
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === "wave") {
                    seismo.pushData(msg.x || [], msg.y || [], msg.z || [], msg.peak_g || 0.0);
                    document.getElementById("seismo-pga").textContent = `${(msg.peak_g || 0.0).toFixed(3)} g`;
                    if (window.seismicAudio) {
                        window.seismicAudio.updateShakeLevel(msg.peak_g || 0.0);
                    }
                } else if (msg.type === "snapshot" && msg.data) {
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
        if (snap.active_event) {
            const ev = snap.active_event;
            const det = snap.detecting_nodes_count || 0;
            const trig = snap.triggered_nodes_count || 0;
            if (trig === 0 && det > 0) {
                document.getElementById("pill-scenario-phase").textContent =
                    `⚡ Wave Approaching: M${ev.magnitude.toFixed(1)} (${det} detecting P-wave)`;
            } else if (trig > 0) {
                document.getElementById("pill-scenario-phase").textContent =
                    `🚨 Active Quake: M${ev.magnitude.toFixed(1)} (${trig} shaking, ${det} detecting)`;
            } else {
                document.getElementById("pill-scenario-phase").textContent =
                    `⚡ Rupture active: M${ev.magnitude.toFixed(1)}`;
            }
        } else if (snap.scenario) {
            const sc = snap.scenario;
            isScenarioPlaying = sc.is_running;
            const desc = sc.current_description || (sc.is_running ? "Scenario active" : "quiescent baseline");
            document.getElementById("pill-scenario-phase").textContent = `Scenario: ${desc}`;
            document.getElementById("btn-scenario-toggle").textContent = sc.is_running ? "⏹ Stop scenario" : "▶ Play scenario";
        } else {
            document.getElementById("pill-scenario-phase").textContent = "Scenario: quiescent baseline";
        }

        // Top 4 KPI Cards
        const rps = snap.current_rps || 0.0;
        document.getElementById("kpi-throughput").textContent = rps.toFixed(1);

        const totalActive = snap.active_nodes_count || 500;
        const shaking = snap.triggered_nodes_count || 0;
        const detecting = snap.detecting_nodes_count || 0;
        const buffering = snap.buffering_nodes_count || 0;
        const normal = Math.max(0, totalActive - shaking - detecting - buffering);

        document.getElementById("kpi-fleet-total").textContent = totalActive;
        document.getElementById("kpi-normal-count").textContent = `${normal} normal`;
        const detEl = document.getElementById("kpi-detecting-count");
        if (detEl) detEl.textContent = `${detecting} detecting`;
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
            const statusBadge = document.getElementById("cluster-status-badge");
            if (statusBadge) {
                statusBadge.textContent = cl.status;
                statusBadge.className = "hpa-badge";
                if (cl.status === "scaling out") statusBadge.classList.add("scaling-out");
                else if (cl.status === "at max capacity") statusBadge.classList.add("max-capacity");
                else if (cl.status === "scaled") statusBadge.classList.add("scaled");
                else if (cl.status === "cooling down" || cl.status === "scaling in") statusBadge.classList.add("cooling-down");
            }

            const decisionBanner = document.getElementById("hpa-decision-banner");
            if (decisionBanner && cl.hpa_reason) {
                decisionBanner.textContent = cl.hpa_reason;
            }

            function updateSegments(barId, ready, replicas) {
                const bar = document.getElementById(barId);
                if (!bar) return;
                const segs = bar.children;
                for (let i = 0; i < 10; i++) {
                    if (i < ready) {
                        segs[i].className = "pod-seg active";
                    } else if (i < replicas) {
                        segs[i].className = "pod-seg starting";
                    } else {
                        segs[i].className = "pod-seg";
                    }
                }
            }

            function updateCpuBadge(badgeId, cpuPct) {
                const el = document.getElementById(badgeId);
                if (!el) return;
                const val = Math.round(cpuPct || 1);
                el.textContent = `CPU ${val}% / 30%`;
                el.className = "cpu-pill";
                if (val >= 45) el.classList.add("cpu-high");
                else if (val >= 25) el.classList.add("cpu-elevated");
            }

            // Ingest API Pods (HPA)
            const ing = cl.ingest || { ready_pods: cl.ready_pods, replicas: cl.replicas, starting_pods: 0, cpu_percent: cl.cpu_percent };
            const ingVal = document.getElementById("ingest-pods-val");
            if (ingVal) {
                const startTxt = ing.starting_pods > 0 ? ` (+${ing.starting_pods} starting)` : "";
                ingVal.textContent = `${ing.ready_pods} / 10${startTxt}`;
            }
            updateSegments("ingest-pod-segments", ing.ready_pods, ing.replicas);
            updateCpuBadge("ingest-cpu-badge", ing.cpu_percent);

            // Processor Worker Pods (HPA)
            const proc = cl.processor || { ready_pods: cl.ready_pods, replicas: cl.replicas, starting_pods: 0, cpu_percent: cl.cpu_percent };
            const procVal = document.getElementById("processor-pods-val");
            if (procVal) {
                const startTxt = proc.starting_pods > 0 ? ` (+${proc.starting_pods} starting)` : "";
                procVal.textContent = `${proc.ready_pods} / 10${startTxt}`;
            }
            updateSegments("processor-pod-segments", proc.ready_pods, proc.replicas);
            updateCpuBadge("processor-cpu-badge", proc.cpu_percent);

            // Queue depth meter
            document.getElementById("cluster-queue-val").textContent = cl.queue_depth.toLocaleString();
            const queuePct = cl.queue_depth > 0 ? Math.max(5, Math.min(100, (cl.queue_depth / 1200) * 100)) : 0;
            document.getElementById("meter-queue").style.width = `${queuePct}%`;

            // DB writes meter
            document.getElementById("cluster-db-val").textContent = cl.db_writes_per_sec.toLocaleString();
            const dbPct = cl.db_writes_per_sec > 0 ? Math.max(4, Math.min(100, (cl.db_writes_per_sec / 3500) * 100)) : 2;
            document.getElementById("meter-db").style.width = `${dbPct}%`;
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
                    duration_s: 55.0,
                }),
            });
            if (resp.ok && window.seismicAudio) {
                window.seismicAudio.triggerEarlyWarning(magnitude, 1.5);
            }
        } catch (e) {
            console.error("Failed to trigger earthquake:", e);
        }
    }

    document.getElementById("btn-trigger-quake").addEventListener("click", () => {
        const sliderEl = document.getElementById("slider-mag");
        const mag = parseFloat(sliderEl.value) || 6.5;
        triggerEarthquake(mag, currentEpicenter);
    });

    document.getElementById("slider-mag").addEventListener("input", (e) => {
        document.getElementById("val-mag").textContent = parseFloat(e.target.value).toFixed(1);
    });

    document.querySelectorAll(".preset-chip").forEach((btn) => {
        btn.addEventListener("click", () => {
            const mag = parseFloat(btn.dataset.mag) || 5.0;
            const sliderEl = document.getElementById("slider-mag");
            if (sliderEl) sliderEl.value = mag.toFixed(1);
            const valEl = document.getElementById("val-mag");
            if (valEl) valEl.textContent = mag.toFixed(1);
            triggerEarthquake(mag, currentEpicenter);
        });
    });

    document.getElementById("btn-clear-quake").addEventListener("click", async () => {
        try {
            await fetch("/api/scenario/clear", { method: "POST" });
            if (window.seismicAudio) {
                window.seismicAudio.stopEarthquake();
            }
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

    // Sector Navigation Views (Coordinates matched to 50km x 24km layout)
    const sectorViews = {
        all: { x: 0.0, y: 0.0, z: 1.0 },
        A: { x: 0.0, y: 0.0, z: 2.5 },       // Downtown
        B: { x: 16.0, y: -5.5, z: 2.2 },     // Industrial & Port
        C: { x: -16.0, y: 5.5, z: 2.2 },     // Kelvin Dam & Residential Hills
        D: { x: 15.5, y: 5.5, z: 2.2 },      // Transit Corridor & Meadow Mall
        E: { x: -15.5, y: -5.5, z: 2.2 },    // Suburban Ring
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
        try {
            if (isScenarioPlaying) {
                await fetch("/api/scenario/stop", { method: "POST" });
                isScenarioPlaying = false;
                btnScenario.textContent = "▶ Play scenario";
            } else {
                await fetch("/api/scenario/start", { method: "POST" });
                isScenarioPlaying = true;
                btnScenario.textContent = "⏹ Stop scenario";
            }
        } catch (err) {
            console.error("Failed to toggle scenario:", err);
        }
    });
});
