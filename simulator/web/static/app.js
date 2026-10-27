// City Seismic Fleet Controller Frontend Logic

const SECTORS_META = {
  A: { name: "Sector A: Downtown & High-Rise", range: [1, 100] },
  B: { name: "Sector B: Industrial & Port", range: [101, 200] },
  C: { name: "Sector C: Residential Hills", range: [201, 300] },
  D: { name: "Sector D: Transit Corridor", range: [301, 400] },
  E: { name: "Sector E: Suburban Perimeter", range: [401, 500] },
};

let ws = null;
let reconnectTimer = null;
let jitterEnabled = true;
const nodeElementMap = new Map();

// Tooltip element
const tooltip = document.getElementById("node-tooltip");

function initDashboard() {
  buildSectorGrids();
  setupEventListeners();
  connectWebSocket();
}

// 1. Build DOM matrix for all 500 nodes across 5 sectors
function buildSectorGrids() {
  const container = document.getElementById("sectors-container");
  container.innerHTML = "";

  for (const [sectorId, meta] of Object.entries(SECTORS_META)) {
    const block = document.createElement("div");
    block.className = "sector-block";
    block.id = `sector-block-${sectorId}`;

    const titleRow = document.createElement("div");
    titleRow.className = "sector-title-row";
    titleRow.innerHTML = `
      <span class="sector-name">${meta.name}</span>
      <span class="sector-badge" id="sector-badge-${sectorId}">100 Nodes</span>
    `;

    const matrix = document.createElement("div");
    matrix.className = "node-dots-matrix";

    const [startNum, endNum] = meta.range;
    for (let i = startNum; i <= endNum; i++) {
      const nodeId = `node-${String(i).padStart(3, "0")}`;
      const dot = document.createElement("div");
      dot.className = "node-dot dot-quiescent";
      dot.id = `dot-${nodeId}`;
      dot.dataset.nodeId = nodeId;
      dot.dataset.sector = sectorId;

      dot.addEventListener("mouseenter", (e) => showTooltip(e, dot));
      dot.addEventListener("mouseleave", hideTooltip);
      dot.addEventListener("click", () => triggerShockOnNode(dot));

      matrix.appendChild(dot);
      nodeElementMap.set(nodeId, dot);
    }

    block.appendChild(titleRow);
    block.appendChild(matrix);
    container.appendChild(block);
  }
}

// 2. WebSocket Connection
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

  const wsStatusEl = document.getElementById("ws-status");
  const wsStatusText = document.getElementById("ws-status-text");

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    wsStatusEl.classList.remove("disconnected");
    wsStatusText.textContent = "CONNECTED (LIVE)";
    if (reconnectTimer) {
      clearInterval(reconnectTimer);
      reconnectTimer = null;
    }
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      updateDashboardData(data);
    } catch (err) {
      console.error("Error parsing websocket frame:", err);
    }
  };

  ws.onclose = () => {
    wsStatusEl.classList.add("disconnected");
    wsStatusText.textContent = "DISCONNECTED (RETRYING)";
    if (!reconnectTimer) {
      reconnectTimer = setInterval(connectWebSocket, 2000);
    }
  };

  ws.onerror = () => {
    ws.close();
  };
}

// 3. UI Updates from Snapshot
function updateDashboardData(data) {
  // Update Top Metrics
  document.getElementById("val-rps").textContent = data.current_rps.toFixed(1);
  document.getElementById("val-active-nodes").textContent = data.active_nodes_count;
  
  const stats = data.stats || {};
  document.getElementById("val-total-batches").textContent = (stats.total_sent || 0).toLocaleString();
  document.getElementById("sub-batch-breakdown").textContent = 
    `${(stats.summaries_sent || 0).toLocaleString()} summaries • ${(stats.waveforms_sent || 0).toLocaleString()} waveforms`;
  
  document.getElementById("val-backfill").textContent = (stats.backfill_sent || 0).toLocaleString();
  document.getElementById("sub-buffered-queue").textContent = `${data.total_buffered_batches || 0} queued`;
  document.getElementById("sub-429-count").textContent = `${stats.rate_limited_429 || 0} rate-limits (429)`;

  // Breakdown sub counts
  const quietCount = data.active_nodes_count - (data.triggered_nodes_count || 0) - (data.buffering_nodes_count || 0);
  document.getElementById("count-quiescent").textContent = `${Math.max(0, quietCount)} quiet`;
  document.getElementById("count-triggered").textContent = `${data.triggered_nodes_count || 0} active quake`;
  document.getElementById("count-buffering").textContent = `${data.buffering_nodes_count || 0} buffering`;

  // Traffic status pill
  const trafficSub = document.getElementById("sub-traffic");
  if (data.current_rps > 1000) {
    trafficSub.innerHTML = `<span class="text-red font-bold">⚡ CRITICAL QUAKE BURST (Scaling HPA)</span>`;
  } else if (data.current_rps > 100) {
    trafficSub.innerHTML = `<span class="text-yellow font-bold">⚠️ ELEVATED ACTIVITY</span>`;
  } else {
    trafficSub.innerHTML = `Quiescent baseline (1 pkt/60s)`;
  }

  // Jitter indicator
  jitterEnabled = data.jitter_enabled;
  const jitterLabel = document.getElementById("jitter-state-label");
  if (jitterEnabled) {
    jitterLabel.textContent = "ENABLED";
    jitterLabel.className = "text-green font-bold";
  } else {
    jitterLabel.textContent = "OFF (THUNDERING HERD)";
    jitterLabel.className = "text-red font-bold";
  }

  // Update Scenario timeline pill
  const scenarioPill = document.getElementById("scenario-status-pill");
  const runBtn = document.getElementById("btn-run-timeline");
  const stopBtn = document.getElementById("btn-stop-timeline");

  if (data.scenario && data.scenario.is_running) {
    scenarioPill.textContent = `Phase ${data.scenario.current_step_index + 1}/${data.scenario.total_steps} (${data.scenario.elapsed_seconds}s)`;
    scenarioPill.style.borderColor = "var(--color-yellow)";
    runBtn.classList.add("hidden");
    stopBtn.classList.remove("hidden");
  } else {
    scenarioPill.textContent = "Manual Injection Mode";
    scenarioPill.style.borderColor = "rgba(99, 102, 241, 0.3)";
    runBtn.classList.remove("hidden");
    stopBtn.classList.add("hidden");
  }

  // Update 500 Node Matrix Dots
  if (data.nodes) {
    for (const node of data.nodes) {
      const dot = nodeElementMap.get(node.id);
      if (dot) {
        dot.className = `node-dot dot-${node.status}`;
        dot.dataset.status = node.status;
        dot.dataset.coords = node.coords ? `(${node.coords[0]}, ${node.coords[1]})` : "";
        dot.dataset.bufferLen = node.buffer_len || 0;
      }
    }
  }
}

// 4. Tooltips
function showTooltip(e, dot) {
  const nid = dot.dataset.nodeId;
  const sector = dot.dataset.sector;
  const status = dot.dataset.status || "quiescent";
  const coords = dot.dataset.coords || "(0, 0)";
  const bufferLen = dot.dataset.bufferLen || 0;

  tooltip.innerHTML = `
    <strong>${nid}</strong> [Sector ${sector}]<br>
    Status: <em>${status.toUpperCase()}</em><br>
    Coords: ${coords} km<br>
    Buffer: ${bufferLen} batches
  `;
  tooltip.style.left = `${e.pageX + 12}px`;
  tooltip.style.top = `${e.pageY + 12}px`;
  tooltip.style.opacity = "1";
}

function hideTooltip() {
  tooltip.style.opacity = "0";
}

// 5. Click on node triggers shockwave centered on that node
async function triggerShockOnNode(dot) {
  const coords = dot.dataset.coords.replace(/[()]/g, "").split(",").map(Number);
  const x = coords[0] || 0.0;
  const y = coords[1] || 0.0;

  await fetch("/api/scenario/earthquake", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      magnitude: 5.8,
      epicenter_x: x,
      epicenter_y: y,
      duration_s: 25.0,
    }),
  });
}

// 6. Setup Buttons & Slider Handlers
function setupEventListeners() {
  // Minor Tremor
  document.getElementById("btn-tremor").addEventListener("click", async () => {
    await fetch("/api/scenario/earthquake", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ magnitude: 3.8, epicenter_x: -4.0, epicenter_y: 4.0, duration_s: 15.0 }),
    });
  });

  // Major Quake Surge
  document.getElementById("btn-quake").addEventListener("click", async () => {
    await fetch("/api/scenario/earthquake", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ magnitude: 6.8, epicenter_x: 0.0, epicenter_y: 0.0, duration_s: 45.0 }),
    });
  });

  // Clear / Reset
  document.getElementById("btn-clear-quake").addEventListener("click", async () => {
    await fetch("/api/scenario/clear", { method: "POST" });
  });

  // Cut Sector B
  document.getElementById("btn-cut-network").addEventListener("click", async () => {
    await fetch("/api/scenario/network", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sector: "B", online: false }),
    });
  });

  // Restore Sector B & Backfill Flush
  document.getElementById("btn-restore-network").addEventListener("click", async () => {
    await fetch("/api/scenario/network", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sector: "B", online: true }),
    });
  });

  // Jitter Toggle
  document.getElementById("btn-toggle-jitter").addEventListener("click", async () => {
    await fetch("/api/scenario/jitter", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !jitterEnabled }),
    });
  });

  // Fleet Slider
  const slider = document.getElementById("fleet-scale-range");
  const sliderVal = document.getElementById("slider-nodes-val");

  let sliderDebounce = null;
  slider.addEventListener("input", (e) => {
    const val = parseInt(e.target.value, 10);
    sliderVal.textContent = `${val} Nodes`;

    if (sliderDebounce) clearTimeout(sliderDebounce);
    sliderDebounce = setTimeout(async () => {
      await fetch("/api/scenario/fleet-size", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_nodes: val }),
      });
    }, 200);
  });

  // Automated Scenario Play / Stop
  document.getElementById("btn-run-timeline").addEventListener("click", async () => {
    await fetch("/api/scenario/timeline/start", { method: "POST" });
  });

  document.getElementById("btn-stop-timeline").addEventListener("click", async () => {
    await fetch("/api/scenario/timeline/stop", { method: "POST" });
  });
}

// Start
document.addEventListener("DOMContentLoaded", initDashboard);
