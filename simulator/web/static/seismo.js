/**
 * Tri-Axial Real-Time Seismograph Canvas Renderer
 * Renders high-precision synchronized waveforms for axes X, Y, Z with phosphor glow.
 */

class Seismograph {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!canvasId || !this.canvas) return;
        this.ctx = this.canvas.getContext("2d");

        this.maxSamples = 600;
        this.xBuffer = new Float32Array(this.maxSamples);
        this.yBuffer = new Float32Array(this.maxSamples);
        this.zBuffer = new Float32Array(this.maxSamples);
        this.head = 0;
        this.count = 0;

        this.currentStationId = "node-001";
        this.currentSite = "Kelvin Financial Tower (72F)";
        this.currentSector = "A";
        this.peakPga = 0.003;

        this.targetScale = 0.05;
        this.currentScale = 0.05;

        this.resize();
        window.addEventListener("resize", () => this.resize());
        this.startLoop();
    }

    resize() {
        if (!this.canvas) return;
        const rect = this.canvas.getBoundingClientRect();
        this.dpr = window.devicePixelRatio || 1;
        this.canvas.width = Math.max(200, Math.floor(rect.width * this.dpr));
        this.canvas.height = Math.max(120, Math.floor(rect.height * this.dpr));
        this.width = rect.width;
        this.height = rect.height;
    }

    setStation(id, site, sector) {
        this.currentStationId = id;
        this.currentSite = site || id;
        this.currentSector = sector || "";
    }

    pushData(xSamples, ySamples, zSamples, peakG) {
        if (peakG !== undefined && peakG > 0) {
            this.peakPga = peakG;
        }

        const len = Math.min(xSamples.length, ySamples.length, zSamples.length);
        for (let i = 0; i < len; i++) {
            this.xBuffer[this.head] = xSamples[i];
            this.yBuffer[this.head] = ySamples[i];
            this.zBuffer[this.head] = zSamples[i];
            this.head = (this.head + 1) % this.maxSamples;
            if (this.count < this.maxSamples) this.count++;
        }

        // Dynamically adjust scale with exponential damping
        const maxObserved = Math.max(0.015, this.peakPga * 1.25);
        this.targetScale = maxObserved;
    }

    startLoop() {
        const render = () => {
            this.render();
            requestAnimationFrame(render);
        };
        requestAnimationFrame(render);
    }

    render() {
        if (!this.ctx || this.width <= 0 || this.height <= 0) return;
        const ctx = this.ctx;
        const w = this.width;
        const h = this.height;

        ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);

        // Smooth scale interpolation
        this.currentScale += (this.targetScale - this.currentScale) * 0.1;
        const scale = Math.max(0.02, this.currentScale);

        // Clear background
        ctx.fillStyle = "#070d18";
        ctx.fillRect(0, 0, w, h);

        // 3 Axis Lanes
        const laneHeight = h / 3.0;
        const lanes = [
            { label: "X", color: "#38bdf8", glow: "rgba(56, 189, 248, 0.4)", buffer: this.xBuffer, yMid: laneHeight * 0.5 },
            { label: "Y", color: "#fbbf24", glow: "rgba(251, 191, 36, 0.4)", buffer: this.yBuffer, yMid: laneHeight * 1.5 },
            { label: "Z", color: "#f472b6", glow: "rgba(244, 114, 182, 0.4)", buffer: this.zBuffer, yMid: laneHeight * 2.5 },
        ];

        // Draw horizontal centerlines & dividers
        ctx.lineWidth = 1;
        for (let i = 0; i < 3; i++) {
            const lane = lanes[i];
            // Centerline
            ctx.strokeStyle = "rgba(255, 255, 255, 0.07)";
            ctx.setLineDash([4, 6]);
            ctx.beginPath();
            ctx.moveTo(35, lane.yMid);
            ctx.lineTo(w - 10, lane.yMid);
            ctx.stroke();

            // Lane Divider
            if (i > 0) {
                ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
                ctx.setLineDash([]);
                ctx.beginPath();
                ctx.moveTo(10, i * laneHeight);
                ctx.lineTo(w - 10, i * laneHeight);
                ctx.stroke();
            }

            // Lane Axis Tag
            ctx.fillStyle = lane.color;
            ctx.font = "600 12px Inter, sans-serif";
            ctx.fillText(lane.label, 14, lane.yMid + 4);
        }

        ctx.setLineDash([]);

        // Plot Waveforms
        if (this.count > 1) {
            const plotLeft = 38;
            const plotWidth = w - plotLeft - 14;
            const stepX = plotWidth / (this.maxSamples - 1);
            const maxAmpPx = laneHeight * 0.44;

            for (let li = 0; li < 3; li++) {
                const lane = lanes[li];
                ctx.save();
                ctx.beginPath();

                for (let i = 0; i < this.count; i++) {
                    const bufIdx = (this.head - this.count + i + this.maxSamples) % this.maxSamples;
                    const val = lane.buffer[bufIdx];
                    const px = plotLeft + i * stepX;
                    const py = lane.yMid - (val / scale) * maxAmpPx;

                    if (i === 0) {
                        ctx.moveTo(px, py);
                    } else {
                        ctx.lineTo(px, py);
                    }
                }

                // Phosphor trace glow
                ctx.shadowColor = lane.glow;
                ctx.shadowBlur = 6;
                ctx.strokeStyle = lane.color;
                ctx.lineWidth = 1.7;
                ctx.stroke();
                ctx.restore();
            }
        }
    }
}

window.Seismograph = Seismograph;
