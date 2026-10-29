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
        this.warningTimeouts = [];
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

        // Sub-bass tectonic sine tone (42 Hz)
        this.subOsc = this.ctx.createOscillator();
        this.subOsc.type = "sine";
        this.subOsc.frequency.setValueAtTime(42, this.ctx.currentTime);
        this.subOsc.connect(this.rumbleGain);
        this.subOsc.start(0);
    }

    toggle() {
        this.init();
        if (this.ctx && this.ctx.state === "suspended") {
            this.ctx.resume();
        }
        this.enabled = !this.enabled;
        if (this.masterGain && this.ctx) {
            this.masterGain.gain.setValueAtTime(this.enabled ? 0.8 : 0.0, this.ctx.currentTime);
        }
        if (!this.enabled) {
            this.clearWarningTimers();
        }
        return this.enabled;
    }

    clearWarningTimers() {
        for (const t of this.warningTimeouts) {
            clearTimeout(t);
        }
        this.warningTimeouts = [];
    }

    /**
     * Trigger Early Warning audible siren pulses followed by destructive S-wave rumble.
     */
    triggerEarlyWarning(magnitude, leadTimeSeconds = 15.0) {
        if (!this.enabled || !this.ctx) return;
        this.clearWarningTimers();

        // Warning chime at rupture
        this.playWarningPulse(880, 0.14);

        // Warning chimes during the 15-second countdown
        const checkpoints = [5, 10, 12, 13, 14];
        for (const sec of checkpoints) {
            if (sec < leadTimeSeconds) {
                const timer = setTimeout(() => {
                    const freq = sec >= 12 ? 1046 : 880;
                    this.playWarningPulse(freq, 0.12);
                }, sec * 1000);
                this.warningTimeouts.push(timer);
            }
        }

        // Schedule surface impact rumble at leadTimeSeconds (15.0s)
        const impactTimer = setTimeout(() => {
            this.startEarthquake(magnitude);
        }, Math.max(0, leadTimeSeconds * 1000));
        this.warningTimeouts.push(impactTimer);
    }

    /**
     * Synthesize clean civil defense early warning beep tone
     */
    playWarningPulse(freq = 880, dur = 0.12) {
        if (!this.enabled || !this.ctx) return;
        try {
            const now = this.ctx.currentTime;
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();

            osc.type = "sine";
            osc.frequency.setValueAtTime(freq, now);

            gain.gain.setValueAtTime(0.0, now);
            gain.gain.linearRampToValueAtTime(0.35, now + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.001, now + dur);

            osc.connect(gain);
            gain.connect(this.masterGain);

            osc.start(now);
            osc.stop(now + dur + 0.05);
        } catch (e) {
            console.error("Warning tone error:", e);
        }
    }

    /**
     * High-energy shockwave arrival: thump impulse + continuous building rumble
     */
    startEarthquake(magnitude) {
        if (!this.enabled || !this.ctx) return;
        this.clearWarningTimers();

        const intensity = Math.min(1.0, Math.max(0.2, (magnitude - 3.5) / 3.5));
        const now = this.ctx.currentTime;

        // 1. Initial Shockwave Thump
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

        this.subOsc.frequency.setValueAtTime(38 + intensity * 6, now);
        this.isRumbling = true;
    }

    /**
     * Update shaking sound level from real-time peak ground acceleration
     */
    updateShakeLevel(pga) {
        if (!this.enabled || !this.ctx || !this.isRumbling) return;
        const now = this.ctx.currentTime;
        const targetVol = Math.min(0.85, Math.max(0.0, pga * 1.5));
        this.rumbleGain.gain.setTargetAtTime(targetVol, now, 0.1);
    }

    stopEarthquake() {
        this.clearWarningTimers();
        if (!this.ctx || !this.isRumbling) return;
        const now = this.ctx.currentTime;
        this.rumbleGain.gain.cancelScheduledValues(now);
        this.rumbleGain.gain.setTargetAtTime(0.0, now, 1.5);
        this.isRumbling = false;
    }
}

// Global class exports and default instance
window.SeismicAudioEngine = SeismicAudioEngine;
window.SeismicAudio = SeismicAudioEngine;
window.seismicAudio = new SeismicAudioEngine();
