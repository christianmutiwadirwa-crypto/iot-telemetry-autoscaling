// Metropolitan Seismic Command Center: Interactive Canvas Map & Oscilloscope

const SITES = {
  A: { id: "A", name: "Sector A: Downtown & High-Rise", center: [0.0, 0.0], radius: 3.5, color: "#6366f1" },
  B: { id: "B", name: "Sector B: Industrial & Port", center: [5.0, -3.0], radius: 4.5, color: "#f59e0b" },
  C: { id: "C", name: "Sector C: Residential Hills", center: [-4.0, 4.0], radius: 5.2, color: "#10b981" },
  D: { id: "D", name: "Sector D: Transit Corridor", center: [1.0, 6.0], radius: 4.8, color: "#06b6d4" },
  E: { id: "E", name: "Sector E: Suburban Perimeter", center: [-7.0, -6.0], radius: 7.2, color: "#8b5cf6" },
};

// State
let ws = null;
let reconnectTimer = null;
let fleetData = { nodes: [], stats: {}, active_nodes_count: 500, current_rps: 0 };
let activeEvent = null;
let jitterEnabled = true;

// Map Camera & Animation
let camX = 0.0, camY = 0.0;
let camTargetX = 0.0, camTargetY = 0.0;
let zoom = 1.0, zoomTarget = 1.0;
let currentSiteView = "all";
let isDragging = false, dragStartX = 0, dragStartY = 0;
let hoveredNode = null;

// Seismic Ripple Shockwave Animation
const shockwaveRipples = [];

// Seismograph History
const seismoHistory = new Array(250).fill(0.002);
let currentPeakPGA = 0.003;

// DOM Elements
let mapCanvas, mapCtx;
let seismoCanvas, seismoCtx;
const popover = document.getElementById("node-popover");

// Initialize
document.addEventListener("DOMContentLoaded", () => {
  mapCanvas = document.getElementById("metro-map-canvas");
  mapCtx = mapCanvas.getContext("2d");

  seismoCanvas = document.getElementById("seismograph-canvas");
  seismoCtx = seismoCanvas.getContext("2d");

  resizeCanvases();
  window.addEventListener("resize", resizeCanvases);

  setupControls();
  setupMapInteractions();
  connectWebSocket();

  // 60 FPS animation loop for map and oscilloscope
  requestAnimationFrame(renderLoop);
});

function resizeCanvases() {
  const mapWrapper = document.getElementById("canvas-wrapper");
  if (mapWrapper && mapCanvas) {
    mapCanvas.width = mapWrapper.clientWidth * window.devicePixelRatio;
    mapCanvas.height = mapWrapper.clientHeight * window.devicePixelRatio;
    mapCtx.scale(window.devicePixelRatio, window.devicePixelRatio);
  }

  const seismoWrapper = seismoCanvas.parentElement;
  if (seismoWrapper && seismoCanvas) {
    seismoCanvas.width = seismoWrapper.clientWidth * window.devicePixelRatio;
    seismoCanvas.height = seismoWrapper.clientHeight * window.devicePixelRatio;
    seismoCtx.scale(window.devicePixelRatio, window.devicePixelRatio);
  }
}

// ============================================================================
// 1. WebSocket Telemetry Stream
// ============================================================================
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

  const wsPill = document.getElementById("ws-status");
  const wsText = document.getElementById("ws-text");

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    wsPill.classList.remove("disconnected");
    wsText.textContent = "LIVE ONLINE";
    if (reconnectTimer) clearInterval(reconnectTimer);
  };

  ws.onmessage = (evt) => {
    try {
      const data = JSON.parse(evt.data);
      fleetData = data;
      updateHUD(data);

      // Handle active event
      if (data.active_event && (!activeEvent || activeEvent.start_time_s !== data.active_event.start_time_s)) {
        activeEvent = data.active_event;
        createShockwave(activeEvent.epicenter[0], activeEvent.epicenter[1], activeEvent.magnitude);
      } else if (!data.active_event) {
        activeEvent = null;
      }

      // Feed waveform into seismograph
      if (data.latest_waveform && data.latest_waveform.length > 0) {
        for (const sample of data.latest_waveform) {
          seismoHistory.shift();
          seismoHistory.push(sample);
          if (Math.abs(sample) > currentPeakPGA) currentPeakPGA = Math.abs(sample);
        }
      } else {
        // Ambient noise
        seismoHistory.shift();
        const noise = (Math.random() - 0.5) * 0.005;
        seismoHistory.push(noise);
        currentPeakPGA = Math.max(0.003, currentPeakPGA * 0.95);
      }
      document.getElementById("seismo-peak-val").textContent = `${currentPeakPGA.toFixed(3)} g`;

    } catch (err) {
      console.error("WebSocket message error:", err);
    }
  };

  ws.onclose = () => {
    wsPill.classList.add("disconnected");
    wsText.textContent = "OFFLINE";
    if (!reconnectTimer) reconnectTimer = setInterval(connectWebSocket, 2000);
  };

  ws.onerror = () => ws.close();
}

function updateHUD(data) {
  document.getElementById("val-rps").textContent = data.current_rps.toFixed(1);
  document.getElementById("val-active-nodes").textContent = data.active_nodes_count;

  const quiet = data.active_nodes_count - (data.triggered_nodes_count || 0) - (data.buffering_nodes_count || 0);
  document.getElementById("count-quiet").textContent = `${Math.max(0, quiet)} Normal`;
  document.getElementById("count-triggered").textContent = `${data.triggered_nodes_count || 0} Shaking`;
  document.getElementById("count-buffering").textContent = `${data.buffering_nodes_count || 0} Buffering`;

  const stats = data.stats || {};
  document.getElementById("val-total-batches").textContent = (stats.total_sent || 0).toLocaleString();
  document.getElementById("val-batch-sub").textContent = 
    `${(stats.summaries_sent || 0).toLocaleString()} summaries • ${(stats.waveforms_sent || 0).toLocaleString()} waveforms`;

  document.getElementById("val-backfill-sent").textContent = (stats.backfill_sent || 0).toLocaleString();
  document.getElementById("val-queue-buffer").textContent = `${data.total_buffered_batches || 0} in memory`;
  document.getElementById("val-429-count").textContent = `${stats.rate_limited_429 || 0} rate limits`;

  // Traffic indicator text
  const trafficEl = document.getElementById("traffic-state-indicator");
  if (data.current_rps > 1000) {
    trafficEl.innerHTML = `<span class="text-red font-bold">CRITICAL QUAKE SURGE &bull; HPA SCALING TO 10 REPLICAS</span>`;
  } else if (data.current_rps > 100) {
    trafficEl.innerHTML = `<span class="text-yellow font-bold">ELEVATED SHOCKWAVE LOAD</span>`;
  } else {
    trafficEl.textContent = `Baseline Quiescent (~8 req/s)`;
  }

  // Scenario pill
  const phasePill = document.getElementById("phase-pill");
  const phaseText = document.getElementById("phase-text");
  const runBtn = document.getElementById("btn-run-scenario");
  const stopBtn = document.getElementById("btn-stop-scenario");

  if (data.scenario && data.scenario.is_running) {
    phaseText.textContent = `PHASE ${data.scenario.current_step_index + 1}/${data.scenario.total_steps} (${data.scenario.elapsed_seconds}s)`;
    phasePill.style.borderColor = "var(--accent-amber)";
    runBtn.classList.add("hidden");
    stopBtn.classList.remove("hidden");
  } else {
    phaseText.textContent = "MANUAL";
    phasePill.style.borderColor = "var(--border-subtle)";
    runBtn.classList.remove("hidden");
    stopBtn.classList.add("hidden");
  }

  // Jitter
  jitterEnabled = data.jitter_enabled;
  document.getElementById("jitter-txt").textContent = jitterEnabled ? "ON" : "OFF";
  document.getElementById("jitter-txt").className = jitterEnabled ? "text-green" : "text-red";
}

// ============================================================================
// 2. Interactive Map & Camera Zoom Engine
// ============================================================================
function setSiteView(siteKey) {
  currentSiteView = siteKey;

  // Update site buttons
  document.querySelectorAll(".site-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.site === siteKey);
  });

  const labelEl = document.getElementById("map-site-label");

  if (siteKey === "all") {
    camTargetX = 0.0;
    camTargetY = 0.0;
    zoomTarget = 1.0;
    labelEl.textContent = "ALL METROPOLITAN SECTORS";
  } else if (SITES[siteKey]) {
    const s = SITES[siteKey];
    camTargetX = s.center[0];
    camTargetY = s.center[1];
    zoomTarget = 2.6; // High-detail zoom
    labelEl.textContent = s.name.toUpperCase();
  }
}

function createShockwave(x, y, magnitude) {
  shockwaveRipples.push({
    x,
    y,
    currentRadiusKm: 0.2,
    maxRadiusKm: Math.max(12.0, magnitude * 2.8),
    speedKmPerSec: 4.5,
    opacity: 1.0,
    created: performance.now(),
  });
}

function worldToScreen(wx, wy, width, height) {
  // 1 km = 24 pixels at 1.0 zoom
  const scale = 24.0 * zoom;
  const cx = width / 2;
  const cy = height / 2;

  const sx = cx + (wx - camX) * scale;
  const sy = cy - (wy - camY) * scale; // Invert y for standard Cartesian
  return [sx, sy];
}

function screenToWorld(sx, sy, width, height) {
  const scale = 24.0 * zoom;
  const cx = width / 2;
  const cy = height / 2;

  const wx = camX + (sx - cx) / scale;
  const wy = camY - (sy - cy) / scale;
  return [wx, wy];
}

function drawMap() {
  if (!mapCanvas || !mapCtx) return;
  const w = mapCanvas.width / window.devicePixelRatio;
  const h = mapCanvas.height / window.devicePixelRatio;

  mapCtx.clearRect(0, 0, w, h);

  // Smooth camera interpolation
  camX += (camTargetX - camX) * 0.08;
  camY += (camTargetY - camY) * 0.08;
  zoom += (zoomTarget - zoom) * 0.08;

  // 1. Draw Grid & Distance Rings
  drawMetropolitanGrid(w, h);

  // 2. Draw 5 Site Perimeters
  drawSiteBoundaries(w, h);

  // 3. Draw Shockwave Ripples
  drawShockwaves(w, h);

  // 4. Draw 500 Sensor Stations
  drawSensorNodes(w, h);
}

function drawMetropolitanGrid(w, h) {
  const [originX, originY] = worldToScreen(0, 0, w, h);

  mapCtx.save();
  mapCtx.strokeStyle = "rgba(255, 255, 255, 0.04)";
  mapCtx.lineWidth = 1;

  // Concentric distance rings: 5km, 10km, 15km
  const scale = 24.0 * zoom;
  for (const radiusKm of [5, 10, 15]) {
    mapCtx.beginPath();
    mapCtx.arc(originX, originY, radiusKm * scale, 0, Math.PI * 2);
    mapCtx.stroke();
  }

  // Crosshairs
  mapCtx.strokeStyle = "rgba(6, 182, 212, 0.15)";
  mapCtx.beginPath();
  mapCtx.moveTo(originX - 15, originY);
  mapCtx.lineTo(originX + 15, originY);
  mapCtx.moveTo(originX, originY - 15);
  mapCtx.lineTo(originX, originY + 15);
  mapCtx.stroke();
  mapCtx.restore();
}

function drawSiteBoundaries(w, h) {
  const scale = 24.0 * zoom;

  for (const [key, site] of Object.entries(SITES)) {
    const [sx, sy] = worldToScreen(site.center[0], site.center[1], w, h);
    const radiusPx = site.radius * scale;

    mapCtx.save();

    // Fill highlight when selected or hovering
    const isSelected = currentSiteView === key;
    mapCtx.fillStyle = isSelected ? "rgba(99, 102, 241, 0.1)" : "rgba(255, 255, 255, 0.015)";
    mapCtx.strokeStyle = isSelected ? site.color : "rgba(255, 255, 255, 0.12)";
    mapCtx.lineWidth = isSelected ? 2 : 1;

    mapCtx.beginPath();
    mapCtx.arc(sx, sy, radiusPx, 0, Math.PI * 2);
    mapCtx.fill();
    mapCtx.stroke();

    // Site Name Tag
    mapCtx.font = "600 11px 'Inter', sans-serif";
    mapCtx.fillStyle = isSelected ? "#fff" : "rgba(255, 255, 255, 0.4)";
    mapCtx.textAlign = "center";
    mapCtx.fillText(site.name.toUpperCase(), sx, sy - radiusPx - 6);

    mapCtx.restore();
  }
}

function drawShockwaves(w, h) {
  const now = performance.now();
  const scale = 24.0 * zoom;

  for (let i = shockwaveRipples.length - 1; i >= 0; i--) {
    const r = shockwaveRipples[i];
    const dt = (now - r.created) / 1000.0;
    r.currentRadiusKm = dt * r.speedKmPerSec;
    r.opacity = Math.max(0, 1.0 - r.currentRadiusKm / r.maxRadiusKm);

    if (r.opacity <= 0) {
      shockwaveRipples.splice(i, 1);
      continue;
    }

    const [sx, sy] = worldToScreen(r.x, r.y, w, h);
    const radiusPx = r.currentRadiusKm * scale;

    mapCtx.save();
    mapCtx.strokeStyle = `rgba(239, 68, 68, ${r.opacity.toFixed(2)})`;
    mapCtx.lineWidth = 3;
    mapCtx.shadowColor = "#ef4444";
    mapCtx.shadowBlur = 12;

    mapCtx.beginPath();
    mapCtx.arc(sx, sy, radiusPx, 0, Math.PI * 2);
    mapCtx.stroke();

    // Epicenter star
    mapCtx.fillStyle = "#ef4444";
    mapCtx.beginPath();
    mapCtx.arc(sx, sy, 4, 0, Math.PI * 2);
    mapCtx.fill();

    mapCtx.restore();
  }
}

function drawSensorNodes(w, h) {
  const nodes = fleetData.nodes || [];
  const nodeRadius = zoom > 2.0 ? 4.5 : 3.0;

  for (const node of nodes) {
    if (!node.coords) continue;
    const [sx, sy] = worldToScreen(node.coords[0], node.coords[1], w, h);

    // Skip if offscreen
    if (sx < -20 || sx > w + 20 || sy < -20 || sy > h + 20) continue;

    mapCtx.save();

    if (node.status === "triggered") {
      // Pulsing Crimson
      mapCtx.fillStyle = "#ef4444";
      mapCtx.shadowColor = "#ef4444";
      mapCtx.shadowBlur = 10;
      mapCtx.beginPath();
      mapCtx.arc(sx, sy, nodeRadius * 1.4, 0, Math.PI * 2);
      mapCtx.fill();
    } else if (node.status === "buffering") {
      // Amber
      mapCtx.fillStyle = "#f59e0b";
      mapCtx.shadowColor = "#f59e0b";
      mapCtx.shadowBlur = 6;
      mapCtx.beginPath();
      mapCtx.arc(sx, sy, nodeRadius, 0, Math.PI * 2);
      mapCtx.fill();
    } else if (node.status === "quiescent") {
      // Emerald
      mapCtx.fillStyle = "#10b981";
      mapCtx.beginPath();
      mapCtx.arc(sx, sy, nodeRadius, 0, Math.PI * 2);
      mapCtx.fill();
    } else {
      // Inactive
      mapCtx.fillStyle = "rgba(255, 255, 255, 0.15)";
      mapCtx.beginPath();
      mapCtx.arc(sx, sy, nodeRadius * 0.8, 0, Math.PI * 2);
      mapCtx.fill();
    }

    // When zoomed in, draw station ID label
    if (zoom > 2.2) {
      mapCtx.font = "500 9px 'JetBrains Mono'";
      mapCtx.fillStyle = "rgba(255, 255, 255, 0.6)";
      mapCtx.textAlign = "center";
      mapCtx.fillText(node.id.replace("node-", "#"), sx, sy + 12);
    }

    mapCtx.restore();
  }
}

// ============================================================================
// 3. Live Seismograph Oscilloscope Canvas
// ============================================================================
function drawSeismograph() {
  if (!seismoCanvas || !seismoCtx) return;
  const w = seismoCanvas.width / window.devicePixelRatio;
  const h = seismoCanvas.height / window.devicePixelRatio;

  seismoCtx.clearRect(0, 0, w, h);

  const midY = h / 2;
  const maxG = 0.5; // Display scale: +/- 0.5g

  // 1. Threshold Line (0.05g)
  const threshY = midY - (0.05 / maxG) * (midY - 10);
  seismoCtx.save();
  seismoCtx.strokeStyle = "rgba(245, 158, 11, 0.4)";
  seismoCtx.setLineDash([4, 4]);
  seismoCtx.beginPath();
  seismoCtx.moveTo(0, threshY);
  seismoCtx.lineTo(w, threshY);
  seismoCtx.stroke();
  seismoCtx.restore();

  // 2. Center Zero Axis
  seismoCtx.strokeStyle = "rgba(255, 255, 255, 0.1)";
  seismoCtx.beginPath();
  seismoCtx.moveTo(0, midY);
  seismoCtx.lineTo(w, midY);
  seismoCtx.stroke();

  // 3. Rolling Waveform Path
  const pts = seismoHistory.length;
  const dx = w / (pts - 1);

  seismoCtx.save();
  const isQuake = currentPeakPGA > 0.05;
  seismoCtx.strokeStyle = isQuake ? "#ef4444" : "#06b6d4";
  seismoCtx.shadowColor = isQuake ? "#ef4444" : "#06b6d4";
  seismoCtx.shadowBlur = isQuake ? 8 : 4;
  seismoCtx.lineWidth = 1.8;

  seismoCtx.beginPath();
  for (let i = 0; i < pts; i++) {
    const val = seismoHistory[i];
    const clampedVal = Math.max(-maxG, Math.min(maxG, val));
    const y = midY - (clampedVal / maxG) * (midY - 10);
    const x = i * dx;

    if (i === 0) seismoCtx.moveTo(x, y);
    else seismoCtx.lineTo(x, y);
  }
  seismoCtx.stroke();
  seismoCtx.restore();
}

// ============================================================================
// 4. Main 60 FPS Render Loop
// ============================================================================
function renderLoop() {
  drawMap();
  drawSeismograph();
  requestAnimationFrame(renderLoop);
}

// ============================================================================
// 5. Map Interactions (Click to Shock, Hover, Pan, Zoom)
// ============================================================================
function setupMapInteractions() {
  const canvas = mapCanvas;

  // Click on site or coordinates to inject epicenter shockwave
  canvas.addEventListener("click", async (e) => {
    if (isDragging) return;
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;
    const [wx, wy] = screenToWorld(sx, sy, canvas.width / window.devicePixelRatio, canvas.height / window.devicePixelRatio);

    // Trigger earthquake centered at clicked coordinates
    createShockwave(wx, wy, 5.5);

    await fetch("/api/scenario/earthquake", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        magnitude: 5.5,
        epicenter_x: parseFloat(wx.toFixed(2)),
        epicenter_y: parseFloat(wy.toFixed(2)),
        duration_s: 25.0,
      }),
    });
  });

  // Mouse wheel zoom
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const delta = e.deltaY < 0 ? 0.2 : -0.2;
    zoomTarget = Math.max(0.6, Math.min(4.5, zoomTarget + delta));
  }, { passive: false });

  // Hover popover
  canvas.addEventListener("mousemove", (e) => {
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;
    const [wx, wy] = screenToWorld(sx, sy, canvas.width / window.devicePixelRatio, canvas.height / window.devicePixelRatio);

    // Find nearest node within 1.5 km
    const nodes = fleetData.nodes || [];
    let closest = null;
    let closestDist = 1.2;

    for (const n of nodes) {
      if (!n.coords) continue;
      const d = Math.hypot(n.coords[0] - wx, n.coords[1] - wy);
      if (d < closestDist) {
        closestDist = d;
        closest = n;
      }
    }

    if (closest) {
      popover.innerHTML = `
        <strong>${closest.id}</strong> [Sector ${closest.sector}]<br>
        Status: <em>${closest.status.toUpperCase()}</em><br>
        Coords: (${closest.coords[0]}, ${closest.coords[1]}) km<br>
        Buffer: ${closest.buffer_len || 0} batches
      `;
      popover.style.left = `${e.clientX + 14}px`;
      popover.style.top = `${e.clientY + 14}px`;
      popover.style.opacity = "1";
    } else {
      popover.style.opacity = "0";
    }
  });

  canvas.addEventListener("mouseleave", () => {
    popover.style.opacity = "0";
  });
}

// ============================================================================
// 6. Action Center & Toolbar Controls
// ============================================================================
function setupControls() {
  // Site Nav buttons
  document.querySelectorAll(".site-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      setSiteView(btn.dataset.site);
    });
  });

  // Reset View button
  document.getElementById("btn-reset-view").addEventListener("click", () => {
    setSiteView("all");
  });

  // Scenario Triggers
  document.getElementById("btn-tremor").addEventListener("click", async () => {
    createShockwave(-4.0, 4.0, 3.8);
    await fetch("/api/scenario/earthquake", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ magnitude: 3.8, epicenter_x: -4.0, epicenter_y: 4.0, duration_s: 15.0 }),
    });
  });

  document.getElementById("btn-quake").addEventListener("click", async () => {
    createShockwave(0.0, 0.0, 6.8);
    await fetch("/api/scenario/earthquake", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ magnitude: 6.8, epicenter_x: 0.0, epicenter_y: 0.0, duration_s: 45.0 }),
    });
  });

  document.getElementById("btn-clear-quake").addEventListener("click", async () => {
    shockwaveRipples.length = 0;
    await fetch("/api/scenario/clear", { method: "POST" });
  });

  // Sector B Cut & Restore
  document.getElementById("btn-cut-b").addEventListener("click", async () => {
    await fetch("/api/scenario/network", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sector: "B", online: false }),
    });
  });

  document.getElementById("btn-restore-b").addEventListener("click", async () => {
    await fetch("/api/scenario/network", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sector: "B", online: true }),
    });
  });

  // Jitter
  document.getElementById("btn-jitter").addEventListener("click", async () => {
    await fetch("/api/scenario/jitter", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !jitterEnabled }),
    });
  });

  // Fleet Slider
  const slider = document.getElementById("fleet-slider");
  const sliderTxt = document.getElementById("slider-txt");
  let sliderDebounce = null;

  slider.addEventListener("input", (e) => {
    const val = parseInt(e.target.value, 10);
    sliderTxt.textContent = `${val} Nodes`;
    if (sliderDebounce) clearTimeout(sliderDebounce);
    sliderDebounce = setTimeout(async () => {
      await fetch("/api/scenario/fleet-size", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_nodes: val }),
      });
    }, 200);
  });

  // Auto Scenario Timeline
  document.getElementById("btn-run-scenario").addEventListener("click", async () => {
    await fetch("/api/scenario/timeline/start", { method: "POST" });
  });

  document.getElementById("btn-stop-scenario").addEventListener("click", async () => {
    await fetch("/api/scenario/timeline/stop", { method: "POST" });
  });
}
