/**
 * Web Audio Seismic Sound Synthesizer
 * Generates realistic procedural earthquake audio effects:
 * - Deep sub-bass tectonic rumble (38-50 Hz)
 * - Brown-noise crustal displacement with low-pass resonance
 * - Sharp S-wave shockwave arrival impact thump
 * - High-intensity structural rattle
 */

class SeismicAudioEngine {
    constructor() {
        this.ctx = null;
        this.enabled = false;
        this.masterGain = null;
        this.rumbleGain = null;
        this.rattleGain = null;
        this.subOsc = null;
        this.noiseNode = null;
        this.filter = null;
        this.isRumbling = false;
    }

    init() {
        if (this.ctx) return;
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;

        this.ctx = new AudioCtx();
        this.masterGain = this.ctx.createGain();
        this.masterGain.gain.setValueAtTime(0.0, this.ctx.currentTime);
        this.masterGain.connect(this.ctx.destination);

        // Low-pass filter for deep muffled ground rumble
        this.filter = this.ctx.createBiquadFilter();
        this.filter.type = "lowpass";
        this.filter.frequency.setValueAtTime(90, this.ctx.currentTime);
        this.filter.Q.setValueAtTime(2.5, this.ctx.currentTime);
        this.filter.connect(this.masterGain);

        // Brown noise generator (approximates earth vibration)
        const bufferSize = this.ctx.sampleRate * 2;
        const noiseBuffer = this.ctx.createBuffer(1, bufferSize, this.ctx.sampleRate);
        const output = noiseBuffer.getChannelData(0);
        let lastOut = 0.0;
        for (let i = 0; i < bufferSize; i++) {
            const white = Math.random() * 2 - 1;
            output[i] = (lastOut + 0.02 * white) / 1.02;
            lastOut = output[i];
            output[i] *= 3.5; // gain boost
        }

        this.noiseNode = this.ctx.createBufferSource();
        this.noiseNode.buffer = noiseBuffer;
        this.noiseNode.loop = true;

        this.rumbleGain = this.ctx.createGain();
        this.rumbleGain.gain.setValueAtTime(0.0, this.ctx.currentTime);
        this.noiseNode.connect(this.rumbleGain);
        this.rumbleGain.connect(this.filter);
        this.noiseNode.start(0);

        // Sub-bass tectonic oscillator
        this.subOsc = this.ctx.createOscillator();
        this.subOsc.type = "sine";
        this.subOsc.frequency.setValueAtTime(42, this.ctx.currentTime);

        const subGain = this.ctx.createGain();
        subGain.gain.setValueAtTime(0.35, this.ctx.currentTime);
        this.subOsc.connect(subGain);
        subGain.connect(this.filter);
        this.subOsc.start(0);
    }

    setEnabled(enabled) {
        this.enabled = enabled;
        if (enabled && !this.ctx) {
            this.init();
        }
        if (this.ctx && this.ctx.state === "suspended") {
            this.ctx.resume();
        }
        if (this.masterGain) {
            const now = this.ctx.currentTime;
            this.masterGain.gain.cancelScheduledValues(now);
            this.masterGain.gain.setTargetAtTime(enabled ? 0.8 : 0.0, now, 0.05);
        }
    }

    /**
     * Trigger shockwave arrival impact & start rumble
     * @param {number} magnitude Richter magnitude (3.0 - 7.5)
     */
    triggerEarthquake(magnitude = 6.0) {
        if (!this.enabled || !this.ctx) return;
        if (this.ctx.state === "suspended") this.ctx.resume();

        const now = this.ctx.currentTime;
        const intensity = Math.min(1.0, Math.max(0.2, (magnitude - 3.0) / 4.0));

        // 1. Initial shockwave arrival impact (low frequency thump)
        const thumpOsc = this.ctx.createOscillator();
        const thumpGain = this.ctx.createGain();
        thumpOsc.type = "sine";
        thumpOsc.frequency.setValueAtTime(80, now);
        thumpOsc.frequency.exponentialRampToValueAtTime(25, now + 0.35);

        thumpGain.gain.setValueAtTime(intensity * 0.9, now);
        thumpGain.gain.exponentialRampToValueAtTime(0.001, now + 0.5);

        thumpOsc.connect(thumpGain);
        thumpGain.connect(this.masterGain);
        thumpOsc.start(now);
        thumpOsc.stop(now + 0.6);

        // 2. Swell the deep continuous tectonic rumble
        this.rumbleGain.gain.cancelScheduledValues(now);
        this.rumbleGain.gain.setValueAtTime(0.05, now);
        this.rumbleGain.gain.linearRampToValueAtTime(intensity * 0.75, now + 1.2);
        this.filter.frequency.linearRampToValueAtTime(60 + intensity * 60, now + 1.5);

        // Dynamic frequency modulation
        this.subOsc.frequency.setValueAtTime(38 + intensity * 6, now);
        this.isRumbling = true;
    }

    /**
     * Update shaking sound level from real-time peak ground acceleration
     * @param {number} pga Ground acceleration in g
     */
    updateShakeLevel(pga) {
        if (!this.enabled || !this.ctx || !this.isRumbling) return;
        const now = this.ctx.currentTime;
        const targetVol = Math.min(0.85, Math.max(0.0, pga * 1.5));
        this.rumbleGain.gain.setTargetAtTime(targetVol, now, 0.1);
    }

    stopEarthquake() {
        if (!this.ctx || !this.isRumbling) return;
        const now = this.ctx.currentTime;
        this.rumbleGain.gain.cancelScheduledValues(now);
        this.rumbleGain.gain.setTargetAtTime(0.0, now, 1.5);
        this.isRumbling = false;
    }
}

window.seismicAudio = new SeismicAudioEngine();
