"""
Unit tests for Processor SeismicMathEngine (Task L13)
Verifies PGA, RMS, and FFT dominant frequency calculation accuracy.
"""

import math
import numpy as np
import pytest
import sys
from pathlib import Path

PROCESSOR_DIR = Path(__file__).resolve().parent.parent
if str(PROCESSOR_DIR) not in sys.path:
    sys.path.insert(0, str(PROCESSOR_DIR))

from math_engine import SeismicMathEngine


def test_pga_and_rms_calculation():
    """Verify Peak Ground Acceleration and RMS on known values."""
    # z = [-0.1, 0.05, 0.25, -0.2] -> peak = 0.25
    z_arr = np.array([-0.1, 0.05, 0.25, -0.2])
    peak = SeismicMathEngine.compute_peak(z_arr)
    rms = SeismicMathEngine.compute_rms(z_arr)

    assert peak == 0.25
    expected_rms = math.sqrt(((-0.1)**2 + 0.05**2 + 0.25**2 + (-0.2)**2) / 4)
    assert np.isclose(rms, expected_rms, atol=1e-5)


def test_fft_dominant_frequency_detection():
    """
    Synthesize a 5.0 Hz oscillation at 1,000 Hz sampling rate for 1.0 second.
    Verify FFT identifies 5.0 Hz as the dominant frequency.
    """
    sampling_rate = 1000
    duration_s = 1.0
    t = np.arange(int(sampling_rate * duration_s)) / sampling_rate
    target_freq = 5.0

    # 5 Hz sinusoidal wave with small noise
    z_signal = 0.5 * np.sin(2.0 * np.pi * target_freq * t) + np.random.normal(0, 0.02, len(t))

    dom_freq, energy = SeismicMathEngine.compute_fft(z_signal, sampling_rate_hz=sampling_rate)

    # Must accurately identify ~5 Hz
    assert np.isclose(dom_freq, 5.0, atol=0.2)
    assert energy > 0.05


def test_analyze_waveform_end_to_end():
    """Verify dictionary output structure."""
    samples = [
        {"t_offset_ms": 0, "x": 0.01, "y": 0.01, "z": 0.15},
        {"t_offset_ms": 1, "x": 0.01, "y": 0.01, "z": -0.22},
        {"t_offset_ms": 2, "x": 0.01, "y": 0.01, "z": 0.08},
        {"t_offset_ms": 3, "x": 0.01, "y": 0.01, "z": 0.02},
    ]
    analysis = SeismicMathEngine.analyze_waveform(samples, sampling_rate_hz=1000)

    assert "peak_acceleration_g" in analysis
    assert "rms_acceleration_g" in analysis
    assert "dominant_frequency_hz" in analysis
    assert "spectral_energy" in analysis
    assert analysis["peak_acceleration_g"] == 0.22
