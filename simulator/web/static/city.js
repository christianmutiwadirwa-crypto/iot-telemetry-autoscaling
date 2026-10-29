/**
 * Living City Canvas Map (MetroMap)
 * High-performance interactive vector canvas rendering:
 * - Meandering river, Kelvin reservoir, Kelvin Dam & 5 bridges
 * - Highway networks (H7, Northern Expressway), ring roads, arterials, downtown grid & rail line
 * - Detailed architectural structures (skyscrapers, quays, gantry cranes, container yards,
 *   tank farm, cooling towers, hospitals, malls, arena, suburban houses)
 * - ~2,000 trees & parks
 * - Dynamic moving traffic (cars, freight train)
 * - Chronological physical wave propagation:
 *   - Fast P-wave (2.8 km/s): sensors turn AMBER in distance order
 *   - S-wave (1.5 km/s): sensors turn RED and burst-fire to AKS
 * - 500 sensors spread across 50 km x 24 km widescreen layout.
 */

class MetroMap {
    constructor(canvasId, options = {}) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext("2d");

        this.onSelectStation = options.onSelectStation || (() => {});
        this.onSetEpicenter = options.onSetEpicenter || (() => {});

        // Data layers
        this.layout = null;
        this.sensors = [];
        this.activeEvent = null;
        this.selectedSensorId = "node-001";
        this.hoveredSensor = null;

        // Viewport transform (World coordinates in km: X [-25.0, 25.0], Y [-12.0, 12.0])
        this.centerX = 0.0;
        this.centerY = 0.0;
        this.zoom = 1.0;
        this.targetCenterX = 0.0;
        this.targetCenterY = 0.0;
        this.targetZoom = 1.0;

        // Mouse interaction state
        this.isDragging = false;
        this.dragStartX = 0;
        this.dragStartY = 0;
        this.dragStartCenterX = 0;
        this.dragStartCenterY = 0;
        this.mouseX = 0;
        this.mouseY = 0;

        // Dynamic entities (traffic & trains)
        this.vehicles = [];
        this.train = { progress: 0.2, speed: 0.025 };
        this.trafficInitialized = false;

        this.simTimeS = 0.0;
        this.lastFrameTime = performance.now();

        this.initEvents();
        this.resize();
        window.addEventListener("resize", () => this.resize());
        this.startRenderLoop();
    }

    setLayout(layout) {
        this.layout = layout;
        if (layout.sensors) {
            this.sensors = layout.sensors.map(s => ({
                ...s,
                status: "quiescent",
                buffer_len: 0,
            }));
        }
        this.initTraffic();
    }

    updateSnapshot(snapshot) {
        if (!snapshot) return;
        if (snapshot.sim_time_s !== undefined) {
            this.simTimeS = snapshot.sim_time_s;
            this.lastSnapshotPerfTime = performance.now();
        }
        this.activeEvent = snapshot.active_event || null;

        // Update sensor states
        if (snapshot.nodes && this.sensors.length > 0) {
            const statusMap = new Map();
            for (const n of snapshot.nodes) {
                statusMap.set(n.id, n);
            }
            for (const s of this.sensors) {
                const live = statusMap.get(s.id);
                if (live) {
                    s.status = live.status;
                    s.buffer_len = live.buffer_len || 0;
                }
            }
        }
    }

    initEvents() {
        const c = this.canvas;

        c.addEventListener("mousedown", (e) => {
            if (e.button === 0) {
                this.isDragging = true;
                this.dragStartX = e.clientX;
                this.dragStartY = e.clientY;
                this.dragStartCenterX = this.centerX;
                this.dragStartCenterY = this.centerY;
            }
        });

        window.addEventListener("mousemove", (e) => {
            const rect = c.getBoundingClientRect();
            this.mouseX = e.clientX - rect.left;
            this.mouseY = e.clientY - rect.top;

            if (this.isDragging) {
                const dx = e.clientX - this.dragStartX;
                const dy = e.clientY - this.dragStartY;
                const scale = this.getKmToPixelRatio();
                this.centerX = this.dragStartCenterX - dx / scale;
                this.centerY = this.dragStartCenterY + dy / scale; // invert Y
                this.targetCenterX = this.centerX;
                this.targetCenterY = this.centerY;
            } else {
                this.checkHover(this.mouseX, this.mouseY);
            }
        });

        window.addEventListener("mouseup", (e) => {
            if (this.isDragging) {
                const dist = Math.hypot(e.clientX - this.dragStartX, e.clientY - this.dragStartY);
                this.isDragging = false;
                if (dist < 4) {
                    this.handleClick(e);
                }
            }
        });

        c.addEventListener("wheel", (e) => {
            e.preventDefault();
            const rect = c.getBoundingClientRect();
            const mx = e.clientX - rect.left;
            const my = e.clientY - rect.top;

            const w = Math.max(300, this.width || 800);
            const h = Math.max(200, this.height || 500);
            const baseFit = Math.min(w / 52.0, h / 25.0);
            const oldScale = baseFit * (this.zoom || 1.0);

            // World coordinate under cursor right now
            const wx = this.centerX + (mx - this.width / 2) / oldScale;
            const wy = this.centerY - (my - this.height / 2) / oldScale;

            const factor = e.deltaY < 0 ? 1.15 : 0.87;
            const newZoom = Math.min(14.0, Math.max(0.65, (this.targetZoom || 1.0) * factor));
            const newScale = baseFit * newZoom;

            this.zoom = newZoom;
            this.targetZoom = newZoom;

            // Shift center so world point stays under cursor
            this.centerX = wx - (mx - this.width / 2) / newScale;
            this.centerY = wy + (my - this.height / 2) / newScale;

            this.clampCenter();
            this.targetCenterX = this.centerX;
            this.targetCenterY = this.centerY;
        }, { passive: false });

        c.addEventListener("dblclick", (e) => {
            const rect = c.getBoundingClientRect();
            const worldPos = this.screenToWorld(e.clientX - rect.left, e.clientY - rect.top);
            this.flyTo(worldPos.x, worldPos.y, Math.min(10.0, this.zoom * 1.8));
        });
    }

    clampCenter() {
        if (isNaN(this.centerX)) this.centerX = 0.0;
        if (isNaN(this.centerY)) this.centerY = 0.0;
        if (isNaN(this.targetCenterX)) this.targetCenterX = 0.0;
        if (isNaN(this.targetCenterY)) this.targetCenterY = 0.0;
        if (isNaN(this.zoom)) this.zoom = 1.0;
        if (isNaN(this.targetZoom)) this.targetZoom = 1.0;

        const minX = -25.0;
        const maxX = 25.0;
        const minY = -12.0;
        const maxY = 12.0;
        this.centerX = Math.max(minX, Math.min(maxX, this.centerX));
        this.centerY = Math.max(minY, Math.min(maxY, this.centerY));
        this.targetCenterX = Math.max(minX, Math.min(maxX, this.targetCenterX));
        this.targetCenterY = Math.max(minY, Math.min(maxY, this.targetCenterY));
        this.zoom = Math.max(0.65, Math.min(14.0, this.zoom));
        this.targetZoom = Math.max(0.65, Math.min(14.0, this.targetZoom));
    }

    handleClick(e) {
        const rect = this.canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        // 1. Check if clicked a sensor
        const clicked = this.findSensorAtScreen(mx, my, 12);
        if (clicked) {
            this.selectedSensorId = clicked.id;
            this.onSelectStation(clicked);
            return;
        }

        // 2. Otherwise clicked map to set earthquake epicenter
        const worldPos = this.screenToWorld(mx, my);
        this.onSetEpicenter(worldPos.x, worldPos.y);
    }

    checkHover(mx, my) {
        const hovered = this.findSensorAtScreen(mx, my, 10);
        if (hovered !== this.hoveredSensor) {
            this.hoveredSensor = hovered;
            this.canvas.style.cursor = hovered ? "pointer" : (this.isDragging ? "grabbing" : "crosshair");
        }
    }

    findSensorAtScreen(sx, sy, tolerancePx = 10) {
        if (!this.sensors) return null;
        for (const s of this.sensors) {
            const sc = this.worldToScreen(s.x, s.y);
            const d = Math.hypot(sc.x - sx, sc.y - sy);
            if (d <= tolerancePx) return s;
        }
        return null;
    }

    flyTo(x, y, zoom = 2.2) {
        this.targetCenterX = x;
        this.targetCenterY = y;
        this.targetZoom = Math.min(12.0, Math.max(0.65, zoom));
        this.clampCenter();
    }

    zoomIn() {
        this.targetZoom = Math.min(14.0, this.zoom * 1.35);
        this.zoom = this.targetZoom;
        this.clampCenter();
    }

    zoomOut() {
        this.targetZoom = Math.max(0.65, this.zoom * 0.74);
        this.zoom = this.targetZoom;
        this.clampCenter();
    }

    resetView() {
        this.centerX = 0.0;
        this.centerY = 0.0;
        this.zoom = 1.0;
        this.targetCenterX = 0.0;
        this.targetCenterY = 0.0;
        this.targetZoom = 1.0;
    }

    resize() {
        if (!this.canvas) return;
        const rect = this.canvas.getBoundingClientRect();
        this.dpr = window.devicePixelRatio || 1;
        this.canvas.width = Math.max(300, Math.floor(rect.width * this.dpr));
        this.canvas.height = Math.max(200, Math.floor(rect.height * this.dpr));
        this.width = rect.width;
        this.height = rect.height;
    }

    getKmToPixelRatio() {
        // Base fit: fit 50 km width into canvas width
        const w = Math.max(300, this.width || 800);
        const h = Math.max(200, this.height || 500);
        const baseFit = Math.min(w / 52.0, h / 25.0);
        return baseFit * Math.max(0.65, this.zoom || 1.0);
    }

    worldToScreen(wx, wy) {
        const scale = this.getKmToPixelRatio();
        const sx = this.width / 2 + (wx - this.centerX) * scale;
        const sy = this.height / 2 - (wy - this.centerY) * scale; // inverted Y
        return { x: sx, y: sy };
    }

    screenToWorld(sx, sy) {
        const scale = this.getKmToPixelRatio();
        const wx = this.centerX + (sx - this.width / 2) / scale;
        const wy = this.centerY - (sy - this.height / 2) / scale;
        return { x: wx, y: wy };
    }

    initTraffic() {
        if (this.trafficInitialized || !this.layout || !this.layout.roads) return;
        this.vehicles = [];
        const majorRoads = this.layout.roads.filter(r => r.type === "highway" || r.type === "arterial");

        for (let i = 0; i < 50; i++) {
            const road = majorRoads[i % majorRoads.length];
            this.vehicles.push({
                road: road,
                progress: Math.random(),
                speed: (0.012 + Math.random() * 0.02) * (Math.random() > 0.5 ? 1 : -1),
                color: ["#cbd5e1", "#e2e8f0", "#94a3b8", "#f59e0b", "#38bdf8", "#ef4444"][i % 6],
                type: i % 7 === 0 ? "bus" : "car",
            });
        }
        this.trafficInitialized = true;
    }

    startRenderLoop() {
        const loop = (timestamp) => {
            const dt = Math.min(0.1, (timestamp - this.lastFrameTime) / 1000.0);
            this.lastFrameTime = timestamp;

            this.update(dt);
            this.render();
            requestAnimationFrame(loop);
        };
        requestAnimationFrame(loop);
    }

    update(dt) {
        // Smooth camera movement
        this.centerX += (this.targetCenterX - this.centerX) * 0.15;
        this.centerY += (this.targetCenterY - this.centerY) * 0.15;
        this.zoom += (this.targetZoom - this.zoom) * 0.15;
        this.clampCenter();

        const isQuake = !!this.activeEvent;

        // Update vehicles
        for (const v of this.vehicles) {
            const currentSpeed = isQuake ? v.speed * 0.2 : v.speed;
            v.progress += currentSpeed * dt;
            if (v.progress > 1.0) v.progress -= 1.0;
            if (v.progress < 0.0) v.progress += 1.0;
        }

        // Update train
        this.train.progress += this.train.speed * dt * (isQuake ? 0.3 : 1.0);
        if (this.train.progress > 1.0) this.train.progress -= 1.0;
    }

    render() {
        if (!this.ctx || this.width <= 0 || this.height <= 0) return;
        const ctx = this.ctx;
        ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);

        // 1. Clear background ground
        ctx.fillStyle = "#09101d";
        ctx.fillRect(0, 0, this.width, this.height);

        if (!this.layout) return;

        // Sector territory subtle glow tints
        this.renderSectorTints(ctx);

        // 2. Parks & Woods
        this.renderParks(ctx);

        // 3. Roads & Highways & Rail
        this.renderRoads(ctx);

        // 4. Meandering River & Kelvin Reservoir
        this.renderWater(ctx);

        // 5. Kelvin Dam & Bridges
        this.renderDamAndBridges(ctx);

        // 6. Buildings & Infrastructure Structures (LOD aware)
        this.renderStructures(ctx);

        // 7. Trees (~2,000)
        this.renderTrees(ctx);

        // 8. Traffic (cars & trains)
        this.renderTraffic(ctx);

        // 9. Chronological Shockwave Propagation Waves
        this.renderShockwaves(ctx);

        // 10. Sensor Nodes (500)
        this.renderSensors(ctx);

        // 11. Landmark Labels
        this.renderLabels(ctx);

        // 12. Minimap & HUD Overlays
        this.renderMinimap(ctx);
        this.renderScaleBar(ctx);
        this.renderTooltip(ctx);
    }

    renderSectorTints(ctx) {
        if (!this.layout.sectors) return;
        for (const sec of this.layout.sectors) {
            const sc = this.worldToScreen(sec.x, sec.y);
            const rPx = sec.radius_km * this.getKmToPixelRatio();
            const grad = ctx.createRadialGradient(sc.x, sc.y, rPx * 0.2, sc.x, sc.y, rPx);
            grad.addColorStop(0, `${sec.color}14`);
            grad.addColorStop(0.8, `${sec.color}08`);
            grad.addColorStop(1, "transparent");
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(sc.x, sc.y, rPx, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    renderParks(ctx) {
        if (!this.layout.parks) return;
        ctx.fillStyle = "rgba(16, 185, 129, 0.12)";
        ctx.strokeStyle = "rgba(16, 185, 129, 0.25)";
        ctx.lineWidth = 1;

        for (const p of this.layout.parks) {
            const sc = this.worldToScreen(p.cx, p.cy);
            const scale = this.getKmToPixelRatio();
            const pw = p.w * scale;
            const ph = p.h * scale;

            ctx.save();
            ctx.translate(sc.x, sc.y);
            ctx.rotate(p.rot || 0);
            ctx.beginPath();
            ctx.roundRect(-pw / 2, -ph / 2, pw, ph, 8);
            ctx.fill();
            ctx.stroke();
            ctx.restore();
        }
    }

    renderRoads(ctx) {
        if (!this.layout.roads) return;
        const scale = this.getKmToPixelRatio();

        for (const rd of this.layout.roads) {
            if (rd.points.length < 2) continue;

            const isRail = rd.type === "rail";
            const isHwy = rd.type === "highway";
            const isArt = rd.type === "arterial";
            const isSt = rd.type === "street";

            // LOD skip street grid at low zoom
            if (isSt && this.zoom < 1.1) continue;

            let wPx = isHwy ? Math.max(3, 0.08 * scale) : (isArt ? Math.max(2, 0.05 * scale) : Math.max(1, 0.03 * scale));
            if (isRail) wPx = Math.max(2, 0.04 * scale);

            ctx.beginPath();
            for (let i = 0; i < rd.points.length; i++) {
                const sc = this.worldToScreen(rd.points[i][0], rd.points[i][1]);
                if (i === 0) ctx.moveTo(sc.x, sc.y);
                else ctx.lineTo(sc.x, sc.y);
            }

            if (isRail) {
                ctx.strokeStyle = "#475569";
                ctx.lineWidth = wPx;
                ctx.setLineDash([]);
                ctx.stroke();
                ctx.strokeStyle = "#cbd5e1";
                ctx.lineWidth = 1;
                ctx.setLineDash([3, 4]);
                ctx.stroke();
                ctx.setLineDash([]);
            } else if (isHwy) {
                ctx.strokeStyle = "#1e293b";
                ctx.lineWidth = wPx + 2;
                ctx.setLineDash([]);
                ctx.stroke();
                ctx.strokeStyle = "#334155";
                ctx.lineWidth = wPx;
                ctx.stroke();
                if (this.zoom > 1.2) {
                    ctx.strokeStyle = "rgba(251, 191, 36, 0.6)";
                    ctx.lineWidth = 1;
                    ctx.setLineDash([6, 6]);
                    ctx.stroke();
                    ctx.setLineDash([]);
                }
            } else {
                ctx.strokeStyle = isArt ? "#1e293b" : "#172033";
                ctx.lineWidth = wPx;
                ctx.setLineDash([]);
                ctx.stroke();
            }
        }
    }

    renderWater(ctx) {
        const scale = this.getKmToPixelRatio();

        // 1. Reservoir (Northwest)
        if (this.layout.reservoir) {
            const res = this.layout.reservoir;
            const sc = this.worldToScreen(res.cx, res.cy);
            ctx.save();
            ctx.translate(sc.x, sc.y);
            ctx.rotate(res.rot || 0);

            ctx.beginPath();
            ctx.ellipse(0, 0, res.rx * scale, res.ry * scale, 0, 0, Math.PI * 2);
            ctx.fillStyle = "#0c2847";
            ctx.fill();
            ctx.strokeStyle = "#1e4976";
            ctx.lineWidth = 2;
            ctx.stroke();
            ctx.restore();
        }

        // 2. Meandering Trans-Metro River
        if (this.layout.river && this.layout.river.points) {
            const pts = this.layout.river.points;
            const riverW = (this.layout.river.width || 0.65) * scale;

            ctx.beginPath();
            for (let i = 0; i < pts.length; i++) {
                const sc = this.worldToScreen(pts[i][0], pts[i][1]);
                if (i === 0) ctx.moveTo(sc.x, sc.y);
                else ctx.lineTo(sc.x, sc.y);
            }
            ctx.lineCap = "round";
            ctx.lineJoin = "round";

            ctx.strokeStyle = "#081d33";
            ctx.lineWidth = riverW + 4;
            ctx.stroke();

            ctx.strokeStyle = "#0d2b4d";
            ctx.lineWidth = riverW;
            ctx.stroke();

            ctx.strokeStyle = "rgba(56, 189, 248, 0.15)";
            ctx.lineWidth = riverW * 0.4;
            ctx.stroke();
        }
    }

    renderDamAndBridges(ctx) {
        const scale = this.getKmToPixelRatio();

        // Kelvin Dam
        if (this.layout.dam) {
            const dam = this.layout.dam;
            const p1 = this.worldToScreen(dam.x1, dam.y1);
            const p2 = this.worldToScreen(dam.x2, dam.y2);
            const damW = Math.max(4, dam.width * scale);

            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.strokeStyle = "#94a3b8";
            ctx.lineWidth = damW;
            ctx.lineCap = "square";
            ctx.stroke();

            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.strokeStyle = "#334155";
            ctx.lineWidth = Math.max(2, damW * 0.4);
            ctx.stroke();
        }

        // 5 Major Bridges
        if (this.layout.bridges) {
            for (const br of this.layout.bridges) {
                const p1 = this.worldToScreen(br.x1, br.y1);
                const p2 = this.worldToScreen(br.x2, br.y2);

                ctx.beginPath();
                ctx.moveTo(p1.x, p1.y);
                ctx.lineTo(p2.x, p2.y);
                ctx.strokeStyle = "#cbd5e1";
                ctx.lineWidth = Math.max(3, 0.08 * scale);
                ctx.lineCap = "round";
                ctx.stroke();

                const mx = (p1.x + p2.x) / 2;
                const my = (p1.y + p2.y) / 2;
                ctx.fillStyle = "#f59e0b";
                ctx.beginPath();
                ctx.arc(mx, my, Math.max(2.5, 0.04 * scale), 0, Math.PI * 2);
                ctx.fill();
            }
        }
    }

    renderStructures(ctx) {
        if (!this.layout.structures) return;
        const scale = this.getKmToPixelRatio();

        for (const s of this.layout.structures) {
            if (s.kind === "house_cluster" && this.zoom < 1.15) continue;
            if (s.kind === "warehouse" && this.zoom < 0.9) continue;

            const sc = this.worldToScreen(s.x, s.y);
            const w = Math.max(3, s.w * scale);
            const h = Math.max(3, s.h * scale);

            ctx.save();
            ctx.translate(sc.x, sc.y);

            if (s.floors && s.floors > 10) {
                const shadowOff = Math.min(10, s.floors * 0.15 * (this.zoom * 0.8));
                ctx.fillStyle = "rgba(0, 0, 0, 0.45)";
                ctx.fillRect(-w / 2 + shadowOff, -h / 2 + shadowOff, w, h);
            }

            ctx.fillStyle = s.color || "#475569";
            ctx.fillRect(-w / 2, -h / 2, w, h);
            ctx.strokeStyle = "rgba(255, 255, 255, 0.15)";
            ctx.lineWidth = 1;
            ctx.strokeRect(-w / 2, -h / 2, w, h);

            if (s.kind === "skyscraper" && this.zoom > 1.8) {
                ctx.fillStyle = "#38bdf8";
                ctx.beginPath();
                ctx.arc(0, 0, Math.max(1.5, w * 0.15), 0, Math.PI * 2);
                ctx.fill();
            } else if (s.kind === "hospital") {
                ctx.fillStyle = "#ffffff";
                const cSize = Math.max(2, w * 0.35);
                ctx.fillRect(-cSize / 6, -cSize / 2, cSize / 3, cSize);
                ctx.fillRect(-cSize / 2, -cSize / 6, cSize, cSize / 3);
            } else if (s.kind === "crane") {
                ctx.strokeStyle = "#f59e0b";
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.moveTo(0, 0);
                ctx.lineTo(w * 1.5, -h * 0.8);
                ctx.stroke();
            }

            ctx.restore();
        }
    }

    renderTrees(ctx) {
        if (!this.layout.trees || this.zoom < 1.1) return;
        const scale = this.getKmToPixelRatio();

        ctx.fillStyle = "rgba(16, 185, 129, 0.45)";
        for (const t of this.layout.trees) {
            const sc = this.worldToScreen(t[0], t[1]);
            const rPx = Math.max(1.2, t[2] * scale);

            if (sc.x < -10 || sc.x > this.width + 10 || sc.y < -10 || sc.y > this.height + 10) continue;

            ctx.beginPath();
            ctx.arc(sc.x, sc.y, rPx, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    renderTraffic(ctx) {
        const scale = this.getKmToPixelRatio();

        for (const v of this.vehicles) {
            const pts = v.road.points;
            if (!pts || pts.length < 2) continue;

            const totalSegs = pts.length - 1;
            const fIdx = v.progress * totalSegs;
            const seg = Math.min(totalSegs - 1, Math.floor(fIdx));
            const t = fIdx - seg;

            const p1 = pts[seg];
            const p2 = pts[seg + 1];
            const wx = p1[0] + t * (p2[0] - p1[0]);
            const wy = p1[1] + t * (p2[1] - p1[1]);
            const sc = this.worldToScreen(wx, wy);

            ctx.fillStyle = v.color;
            ctx.beginPath();
            ctx.arc(sc.x, sc.y, v.type === "bus" ? 3 : 2, 0, Math.PI * 2);
            ctx.fill();
        }

        const railRoad = this.layout.roads.find(r => r.type === "rail");
        if (railRoad && railRoad.points) {
            const pts = railRoad.points;
            const totalSegs = pts.length - 1;
            const fIdx = this.train.progress * totalSegs;
            const seg = Math.min(totalSegs - 1, Math.floor(fIdx));
            const t = fIdx - seg;
            const p1 = pts[seg];
            const p2 = pts[seg + 1];
            const wx = p1[0] + t * (p2[0] - p1[0]);
            const wy = p1[1] + t * (p2[1] - p1[1]);
            const sc = this.worldToScreen(wx, wy);

            ctx.fillStyle = "#38bdf8";
            ctx.beginPath();
            ctx.arc(sc.x, sc.y, 4, 0, Math.PI * 2);
            ctx.fill();
            ctx.shadowColor = "#38bdf8";
            ctx.shadowBlur = 8;
            ctx.stroke();
            ctx.shadowBlur = 0;
        }
    }

    renderShockwaves(ctx) {
        if (!this.activeEvent) return;
        const ev = this.activeEvent;
        const epicenter = ev.epicenter || [0, 0];
        const sc = this.worldToScreen(epicenter[0], epicenter[1]);
        const scale = this.getKmToPixelRatio();
        const duration = ev.duration_s || 90.0;

        // Smooth interpolated simulation time
        const dtSinceSnap = this.lastSnapshotPerfTime ? (performance.now() - this.lastSnapshotPerfTime) / 1000.0 : 0.0;
        const liveSimTime = this.simTimeS + Math.min(0.6, Math.max(0.0, dtSinceSnap));

        const age = Math.max(0.0, liveSimTime - ev.start_time_s);
        const pVel = ev.p_velocity_km_s || 2.8;
        const sVel = ev.s_velocity_km_s || 1.5;
        const ewDelay = ev.early_warning_delay_s !== undefined ? ev.early_warning_delay_s : 15.0;
        const countdownRem = Math.max(0.0, ewDelay - age);
        const isEarlyWarning = countdownRem > 0.0;
        const sAge = Math.max(0.0, age - ewDelay);

        const pRadiusKm = age * pVel; // Expanding P-wave front (Amber)
        const sRadiusKm = sAge * sVel; // Expanding S-wave front (Red)
        const triggerRadiusKm = ev.trigger_radius_km || 25.0;
        const maxWaveReachKm = Math.min(48.0, Math.max(6.0, triggerRadiusKm * 1.25));

        // 0. Draw 0.05g Sensor Activation Radius Zone
        if (triggerRadiusKm < 35.0) {
            const trigPx = triggerRadiusKm * scale;
            ctx.save();
            ctx.fillStyle = isEarlyWarning ? "rgba(245, 158, 11, 0.04)" : "rgba(239, 68, 68, 0.035)";
            ctx.strokeStyle = isEarlyWarning ? "rgba(251, 191, 36, 0.55)" : "rgba(245, 158, 11, 0.45)";
            ctx.lineWidth = 1.3;
            ctx.setLineDash([4, 4]);
            ctx.beginPath();
            ctx.arc(sc.x, sc.y, trigPx, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.fillStyle = "rgba(253, 230, 138, 0.88)";
            ctx.font = "500 10px JetBrains Mono, monospace";
            ctx.textAlign = "center";
            ctx.fillText(`0.05g Trigger Radius (${triggerRadiusKm.toFixed(1)} km)`, sc.x, sc.y - trigPx - 6);
            ctx.restore();
        }

        // 1. Epicenter Marker with pulsing reticle
        const epiPulse = (performance.now() % 900) / 900;
        ctx.save();
        ctx.fillStyle = isEarlyWarning ? "#f59e0b" : "#ef4444";
        ctx.shadowColor = isEarlyWarning ? "#f59e0b" : "#ef4444";
        ctx.shadowBlur = 14;
        ctx.beginPath();
        ctx.arc(sc.x, sc.y, 6, 0, Math.PI * 2);
        ctx.fill();

        ctx.strokeStyle = isEarlyWarning ? `rgba(251, 191, 36, ${1.0 - epiPulse})` : `rgba(239, 68, 68, ${1.0 - epiPulse})`;
        ctx.lineWidth = 2.2;
        ctx.beginPath();
        ctx.arc(sc.x, sc.y, 8 + epiPulse * 22, 0, Math.PI * 2);
        ctx.stroke();

        ctx.font = "600 11px JetBrains Mono, monospace";
        ctx.textAlign = "left";
        if (isEarlyWarning) {
            ctx.fillStyle = "#fde68a";
            ctx.fillText(`T-${countdownRem.toFixed(1)}s EARLY WARNING`, sc.x + 14, sc.y + 4);
        } else {
            ctx.fillStyle = "#fca5a5";
            ctx.fillText(`EPICENTER M${ev.magnitude.toFixed(1)} [T+${age.toFixed(1)}s]`, sc.x + 14, sc.y + 4);
        }
        ctx.restore();

        // 2. Trailing concentric reverberation waves behind leading S-wave (after 15s impact)
        if (!isEarlyWarning && sAge > 0) {
            const ripplePeriod = 2.2;
            const maxRipples = Math.min(10, Math.floor(Math.min(sAge, duration) / ripplePeriod));
            for (let i = 1; i <= maxRipples; i++) {
                const ringAge = sAge - i * ripplePeriod;
                if (ringAge > 0) {
                    const ringRadiusKm = ringAge * sVel;
                    if (ringRadiusKm > 0 && ringRadiusKm < maxWaveReachKm) {
                        const rPx = ringRadiusKm * scale;
                        const alpha = Math.max(0.05, 0.42 * (1.0 - ringRadiusKm / maxWaveReachKm));
                        ctx.save();
                        ctx.strokeStyle = `rgba(239, 68, 68, ${alpha})`;
                        ctx.lineWidth = 1.6;
                        ctx.beginPath();
                        ctx.arc(sc.x, sc.y, rPx, 0, Math.PI * 2);
                        ctx.stroke();
                        ctx.restore();
                    }
                }
            }

            // 3. Leading S-wave Front (intense Red shockwave)
            if (sRadiusKm > 0 && sRadiusKm < maxWaveReachKm) {
                const rPx = sRadiusKm * scale;
                const sAlpha = Math.max(0.2, 0.95 * (1.0 - sRadiusKm / (maxWaveReachKm * 1.05)));
                ctx.save();
                ctx.strokeStyle = `rgba(239, 68, 68, ${sAlpha})`;
                ctx.lineWidth = 3.5;
                ctx.shadowColor = "#ef4444";
                ctx.shadowBlur = 14;
                ctx.beginPath();
                ctx.arc(sc.x, sc.y, rPx, 0, Math.PI * 2);
                ctx.stroke();
                ctx.restore();
            }
        }

        // 4. Leading P-wave Front (fast expanding Amber wave during and after Early Warning)
        if (pRadiusKm > 0 && pRadiusKm < maxWaveReachKm * 1.15) {
            const rPx = pRadiusKm * scale;
            const pAlpha = Math.max(0.18, 0.75 * (1.0 - pRadiusKm / (maxWaveReachKm * 1.2)));
            ctx.save();
            ctx.strokeStyle = `rgba(245, 158, 11, ${pAlpha})`;
            ctx.lineWidth = 2.4;
            ctx.setLineDash([6, 6]);
            ctx.shadowColor = "#f59e0b";
            ctx.shadowBlur = 10;
            ctx.beginPath();
            ctx.arc(sc.x, sc.y, rPx, 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();
        }

        // 5. Top-Center Map HUD Alert Banner (15s Early Warning Countdown -> S-Wave Impact)
        ctx.save();
        const bannerW = 540;
        const bannerH = 40;
        const bx = (this.width - bannerW) / 2;
        const by = 14;

        ctx.fillStyle = isEarlyWarning ? "rgba(18, 14, 8, 0.92)" : "rgba(28, 8, 12, 0.92)";
        ctx.strokeStyle = isEarlyWarning ? "rgba(245, 158, 11, 0.85)" : "rgba(239, 68, 68, 0.85)";
        ctx.lineWidth = 1.5;
        ctx.roundRect(bx, by, bannerW, bannerH, 6);
        ctx.fill();
        ctx.stroke();

        ctx.font = "600 12px JetBrains Mono, monospace";
        ctx.textAlign = "center";
        if (isEarlyWarning) {
            ctx.fillStyle = "#fde68a";
            ctx.fillText(
                `⚠️ SEISMIC EARLY WARNING (M${ev.magnitude.toFixed(1)}) • SURFACE IMPACT IN ${countdownRem.toFixed(1)}s`,
                bx + bannerW / 2,
                by + 20
            );
            // Depleting progress bar across the 15s delay
            const pct = Math.max(0, Math.min(1, countdownRem / ewDelay));
            ctx.fillStyle = "rgba(245, 158, 11, 0.25)";
            ctx.fillRect(bx + 12, by + 28, bannerW - 24, 4);
            ctx.fillStyle = "#f59e0b";
            ctx.fillRect(bx + 12, by + 28, (bannerW - 24) * pct, 4);
        } else {
            ctx.fillStyle = "#fca5a5";
            ctx.fillText(
                `🚨 S-WAVE SURFACE IMPACT ACTIVE (M${ev.magnitude.toFixed(1)}) • SENSORS FIRING [T+${age.toFixed(1)}s]`,
                bx + bannerW / 2,
                by + 24
            );
        }
        ctx.restore();
    }

    renderSensors(ctx) {
        if (!this.sensors) return;

        for (const s of this.sensors) {
            const sc = this.worldToScreen(s.x, s.y);

            // Frustum cull
            if (sc.x < -15 || sc.x > this.width + 15 || sc.y < -15 || sc.y > this.height + 15) continue;

            const isSelected = s.id === this.selectedSensorId;
            const isHovered = s === this.hoveredSensor;
            const isShaking = s.status === "triggered";
            const isDetecting = s.status === "detecting";
            const isBuffering = s.status === "buffering";

            let color = "#10b981"; // quiescent emerald
            if (isShaking) color = "#ef4444"; // shaking red
            else if (isDetecting) color = "#f59e0b"; // P-wave detection amber!
            else if (isBuffering) color = "#f97316"; // link severed orange

            const radius = isSelected ? 5.5 : (isHovered ? 4.5 : 3.0);

            // Detecting P-wave pulse animation
            if (isDetecting) {
                const pulse = (performance.now() % 600) / 600;
                ctx.strokeStyle = `rgba(245, 158, 11, ${1.0 - pulse})`;
                ctx.lineWidth = 1.6;
                ctx.beginPath();
                ctx.arc(sc.x, sc.y, radius + pulse * 9, 0, Math.PI * 2);
                ctx.stroke();
            }

            // Shaking shockwave pulse animation
            if (isShaking) {
                const pulse = (performance.now() % 750) / 750;
                ctx.strokeStyle = `rgba(239, 68, 68, ${1.0 - pulse})`;
                ctx.lineWidth = 2.0;
                ctx.beginPath();
                ctx.arc(sc.x, sc.y, radius + pulse * 14, 0, Math.PI * 2);
                ctx.stroke();
            }

            // Buffering badge ring
            if (isBuffering) {
                ctx.strokeStyle = "#f97316";
                ctx.lineWidth = 1.2;
                ctx.setLineDash([2, 2]);
                ctx.beginPath();
                ctx.arc(sc.x, sc.y, radius + 3, 0, Math.PI * 2);
                ctx.stroke();
                ctx.setLineDash([]);
            }

            // Sensor body
            ctx.fillStyle = color;
            ctx.shadowColor = color;
            ctx.shadowBlur = isShaking || isSelected ? 8 : (isDetecting ? 6 : 4);

            if (s.kind === "dam" || s.kind === "bridge") {
                ctx.beginPath();
                ctx.moveTo(sc.x, sc.y - radius * 1.3);
                ctx.lineTo(sc.x + radius * 1.3, sc.y);
                ctx.lineTo(sc.x, sc.y + radius * 1.3);
                ctx.lineTo(sc.x - radius * 1.3, sc.y);
                ctx.closePath();
                ctx.fill();
            } else {
                ctx.beginPath();
                ctx.arc(sc.x, sc.y, radius, 0, Math.PI * 2);
                ctx.fill();
            }

            ctx.shadowBlur = 0;

            // Selected targeting reticle ring
            if (isSelected) {
                ctx.strokeStyle = "#ffffff";
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                ctx.arc(sc.x, sc.y, radius + 5, 0, Math.PI * 2);
                ctx.stroke();
            }
        }
    }

    renderLabels(ctx) {
        if (!this.layout.labels) return;

        for (const l of this.layout.labels) {
            if (this.zoom < l.minZoom || this.zoom > l.maxZoom) continue;

            const sc = this.worldToScreen(l.x, l.y);
            const isSector = l.kind === "sector";

            ctx.save();
            ctx.font = isSector ? "600 13px Inter, sans-serif" : "500 11px Inter, sans-serif";
            ctx.fillStyle = isSector ? "#94a3b8" : "rgba(226, 232, 240, 0.75)";
            ctx.textAlign = "center";
            ctx.shadowColor = "#000000";
            ctx.shadowBlur = 4;
            ctx.fillText(l.text, sc.x, sc.y);
            ctx.restore();
        }
    }

    renderMinimap(ctx) {
        const mw = 120;
        const mh = 75;
        const pad = 16;
        const x = this.width - mw - pad;
        const y = this.height - mh - pad;

        ctx.save();
        ctx.fillStyle = "rgba(7, 13, 24, 0.85)";
        ctx.strokeStyle = "rgba(255, 255, 255, 0.12)";
        ctx.lineWidth = 1;
        ctx.roundRect(x, y, mw, mh, 6);
        ctx.fill();
        ctx.stroke();

        // City outline in minimap
        ctx.strokeStyle = "rgba(56, 189, 248, 0.35)";
        ctx.strokeRect(x + 4, y + 4, mw - 8, mh - 8);

        // Current camera viewport frustum (bounds: X [-25, 25], Y [-12, 12])
        const normX = (this.centerX + 25.0) / 50.0;
        const normY = (12.0 - this.centerY) / 24.0;
        const camX = x + 4 + normX * (mw - 8);
        const camY = y + 4 + normY * (mh - 8);
        const boxW = Math.max(8, (mw - 8) / this.zoom);
        const boxH = Math.max(6, (mh - 8) / this.zoom);

        ctx.strokeStyle = "#38bdf8";
        ctx.lineWidth = 1.5;
        ctx.strokeRect(camX - boxW / 2, camY - boxH / 2, boxW, boxH);
        ctx.restore();
    }

    renderScaleBar(ctx) {
        const scale = this.getKmToPixelRatio();
        const targetKm = 80 / scale;
        const niceValues = [0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0];
        let kmVal = 2.0;
        for (const v of niceValues) {
            if (v >= targetKm * 0.7) {
                kmVal = v;
                break;
            }
        }
        const barPx = Math.max(30, Math.min(160, kmVal * scale));
        const x = 20;
        const y = this.height - 20;

        ctx.save();
        ctx.strokeStyle = "rgba(255, 255, 255, 0.4)";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x, y - 4);
        ctx.lineTo(x, y);
        ctx.lineTo(x + barPx, y);
        ctx.lineTo(x + barPx, y - 4);
        ctx.stroke();

        ctx.fillStyle = "rgba(255, 255, 255, 0.75)";
        ctx.font = "10px Inter, sans-serif";
        const label = kmVal < 1.0 ? `${Math.round(kmVal * 1000)} m` : `${kmVal} km`;
        ctx.fillText(label, x + barPx / 2 - 12, y - 6);
        ctx.restore();
    }

    renderTooltip(ctx) {
        if (!this.hoveredSensor) return;
        const s = this.hoveredSensor;
        const sc = this.worldToScreen(s.x, s.y);

        const text1 = `${s.id} • ${s.site}`;
        const text2 = `Sector ${s.sector} • Status: ${s.status.toUpperCase()}`;

        ctx.save();
        ctx.font = "500 11px Inter, sans-serif";
        const w = Math.max(ctx.measureText(text1).width, ctx.measureText(text2).width) + 16;
        const h = 42;

        let tx = sc.x + 12;
        let ty = sc.y - h - 6;
        if (tx + w > this.width) tx = sc.x - w - 12;
        if (ty < 10) ty = sc.y + 16;

        ctx.fillStyle = "rgba(10, 18, 32, 0.92)";
        ctx.strokeStyle = "rgba(56, 189, 248, 0.4)";
        ctx.lineWidth = 1;
        ctx.roundRect(tx, ty, w, h, 6);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = "#ffffff";
        ctx.fillText(text1, tx + 8, ty + 16);
        ctx.fillStyle = s.status === "triggered" ? "#ef4444" : (s.status === "detecting" ? "#f59e0b" : (s.status === "buffering" ? "#f97316" : "#10b981"));
        ctx.fillText(text2, tx + 8, ty + 32);
        ctx.restore();
    }
}

window.MetroMap = MetroMap;
