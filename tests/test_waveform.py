"""
Unit tests for Task L4: Waveform Generator
Verifies ambient noise baseline and decaying oscillation earthquake waveforms.
"""

import pytest
import numpy as np
from simulator.waveform_generator import SeismicWaveformGenerator, SeismicEvent
from simulator.config import SEISMIC_TRIGGER_THRESHOLD_G


def test_quiescent_ambient_noise():
    """Verify that during quiet conditions, acceleration is low-level noise well below threshold."""
    gen = SeismicWaveformGenerator(
        node_id="node-001",
        coordinates_km=(0.0, 0.0),
        ambient_noise_sigma=0.003,
    )
    x, y, z, peak_g, rms_g = gen.generate_window(
        start_sim_time_s=0.0,
        sample_count=1000,
        active_event=None,
    )

    assert len(z) == 1000
    # Ambient noise should be far below 0.05g trigger threshold
    assert peak_g < SEISMIC_TRIGGER_THRESHOLD_G
    assert rms_g < 0.015
    assert np.isclose(np.mean(z), 0.0, atol=0.005)


def test_earthquake_event_trigger_and_decay():
    """Verify that a simulated earthquake triggers high acceleration with decaying oscillation."""
    gen = SeismicWaveformGenerator(
        node_id="node-002",
        coordinates_km=(1.0, 1.0),
        soil_amplification=1.2,
    )
    # Create M6.5 earthquake starting at time t=0.0 nearby
    event = SeismicEvent(
        magnitude=6.5,
        epicenter_km=(0.0, 0.0),
        start_time_s=0.0,
        duration_s=20.0,
    )

    # Window around S-wave arrival (main shock)
    _, _, z_peak, peak_g, rms_g = gen.generate_window(
        start_sim_time_s=3.0,
        sample_count=1000,
        active_event=event,
    )

    # Shaking must exceed the 0.05g trigger threshold
    assert peak_g > SEISMIC_TRIGGER_THRESHOLD_G
    assert rms_g > 0.04

    # Window much later (decay phase)
    _, _, z_decay, peak_decay_g, rms_decay_g = gen.generate_window(
        start_sim_time_s=18.0,
        sample_count=1000,
        active_event=event,
    )

    # Shaking should have substantially attenuated
    assert peak_decay_g < peak_g
    assert rms_decay_g < rms_g


def test_waveform_samples_formatting():
    """Verify conversion to Pydantic WaveformSample structures."""
    gen = SeismicWaveformGenerator(
        node_id="node-003",
        coordinates_km=(2.0, -1.0),
    )
    x = np.array([0.001, 0.002, 0.003])
    y = np.array([0.000, 0.001, 0.002])
    z = np.array([0.010, 0.015, 0.020])

    samples = gen.format_waveform_samples(x, y, z)
    assert len(samples) == 3
    assert samples[0].t_offset_ms == 0
    assert samples[0].z == 0.01
    assert samples[1].t_offset_ms == 1
    assert samples[2].t_offset_ms == 2
