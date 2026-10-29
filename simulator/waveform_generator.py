"""
Synthetic Seismic Waveform Generator (Task L4)

Generates realistic 3-axis accelerometer data:
- Quiescent state: Low-amplitude Gaussian ambient micro-seismic noise (traffic, wind, baseline noise).
- Event state: Physically inspired seismic wave arrivals (P-wave precursor, strong S-wave burst, 
  and exponentially decaying multi-frequency oscillations).
Uses vectorized NumPy computations for high-performance generation across 500+ virtual nodes.
"""

import math
import numpy as np
from typing import List, Tuple, Optional
from datetime import datetime, timezone, timedelta

from simulator.config import (
    SAMPLING_RATE_HZ,
    SEISMIC_TRIGGER_THRESHOLD_G,
)
from simulator.models import WaveformSample


class SeismicEvent:
    """Represents a simulated seismic shockwave propagating through the metropolitan area."""

    def __init__(
        self,
        magnitude: float,
        epicenter_km: Tuple[float, float],
        start_time_s: float,
        duration_s: float = 30.0,
        depth_km: float = 10.0,
    ):
        self.magnitude = magnitude
        self.epicenter_km = epicenter_km
        self.start_time_s = start_time_s
        self.duration_s = duration_s
        self.depth_km = depth_km

        # Peak ground acceleration near epicenter scales realistically with magnitude
        # Standard GMPE relationship: log10(PGA in g) ~ 0.5 * M - 3.45
        # M3.8 ~ 0.03g (sub-threshold), M4.2 ~ 0.05g (local threshold), M5.5 ~ 0.20g (moderate), M7.2 ~ 1.25g (severe)
        self.base_pga_g = min(1.8, max(0.015, 10 ** (0.50 * magnitude - 3.45)))

        # Seismic wave velocities (approximate crustal velocities)
        self.p_velocity_km_s = 6.0  # Compressional P-wave
        self.s_velocity_km_s = 3.5  # Shear S-wave (causes major structural damage)
        self.attenuation_lambda = max(0.08, 0.35 - (magnitude * 0.02))  # Decay coefficient


class SeismicWaveformGenerator:
    """
    Simulates high-precision 1,000 Hz accelerometer sensor output for a single station.
    """

    def __init__(
        self,
        node_id: str,
        coordinates_km: Tuple[float, float],
        soil_amplification: float = 1.0,
        ambient_noise_sigma: float = 0.003,
        sampling_rate_hz: int = SAMPLING_RATE_HZ,
    ):
        self.node_id = node_id
        self.coordinates_km = coordinates_km
        self.soil_amplification = soil_amplification
        self.ambient_noise_sigma = ambient_noise_sigma
        self.sampling_rate_hz = sampling_rate_hz

        # Station hardware characteristics
        self.temp_base = 25.0 + (hash(node_id) % 50) / 10.0
        self.dt = 1.0 / sampling_rate_hz

    def calculate_distance_km(self, target_coords: Tuple[float, float]) -> float:
        """Euclidean distance in km from station to target coordinates."""
        dx = self.coordinates_km[0] - target_coords[0]
        dy = self.coordinates_km[1] - target_coords[1]
        return math.sqrt(dx * dx + dy * dy)

    def generate_window(
        self,
        start_sim_time_s: float,
        sample_count: int,
        active_event: Optional[SeismicEvent] = None,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
        """
        Generates tri-axial acceleration arrays (x, y, z) for a given time window.
        Returns:
            (x_arr, y_arr, z_arr, peak_acceleration_g, rms_acceleration_g)
        """
        # Time vector relative to start_sim_time_s
        t_offsets = np.arange(sample_count, dtype=np.float64) * self.dt
        t_absolute = start_sim_time_s + t_offsets

        # 1. Baseline Ambient Micro-Seismic Noise
        z_noise = np.random.normal(0.0, self.ambient_noise_sigma, sample_count)
        x_noise = np.random.normal(0.0, self.ambient_noise_sigma * 0.6, sample_count)
        y_noise = np.random.normal(0.0, self.ambient_noise_sigma * 0.6, sample_count)

        z = z_noise
        x = x_noise
        y = y_noise

        # 2. Seismic Event Shaking (if an event is ongoing)
        if active_event is not None:
            epi_dist = self.calculate_distance_km(active_event.epicenter_km)
            hypo_dist = math.sqrt(epi_dist ** 2 + active_event.depth_km ** 2)

            # Wave arrival times
            t_arrival_p = active_event.start_time_s + (hypo_dist / active_event.p_velocity_km_s)
            t_arrival_s = active_event.start_time_s + (hypo_dist / active_event.s_velocity_km_s)

            # Geometric spreading & crustal anelastic attenuation
            # Amplitude decays with distance: R^-1.1 * exp(-gamma * dR)
            geom_attenuation = ((10.0 / hypo_dist) ** 1.15) * math.exp(-0.035 * max(0.0, hypo_dist - 10.0))
            local_amplitude = active_event.base_pga_g * geom_attenuation * self.soil_amplification

            # Mask for S-wave arrival (main shaking)
            s_mask = (t_absolute >= t_arrival_s) & (t_absolute < (t_arrival_s + active_event.duration_s))
            if np.any(s_mask):
                tau_s = t_absolute[s_mask] - t_arrival_s
                decay = np.exp(-active_event.attenuation_lambda * tau_s)

                # Multi-frequency constructive/destructive seismic waves (2.5 Hz fundamental, 5.2 Hz harmonic)
                oscillation_z = (
                    0.75 * np.sin(2.0 * np.pi * 2.8 * tau_s) +
                    0.25 * np.sin(2.0 * np.pi * 5.6 * tau_s + 0.4)
                )
                z[s_mask] += local_amplitude * decay * oscillation_z

                oscillation_x = np.sin(2.0 * np.pi * 2.4 * tau_s + 0.8)
                oscillation_y = np.cos(2.0 * np.pi * 2.6 * tau_s + 0.2)
                x[s_mask] += local_amplitude * 0.7 * decay * oscillation_x
                y[s_mask] += local_amplitude * 0.7 * decay * oscillation_y

            # Mask for P-wave arrival (precursor micro-vibration)
            p_mask = (t_absolute >= t_arrival_p) & (t_absolute < t_arrival_s)
            if np.any(p_mask):
                tau_p = t_absolute[p_mask] - t_arrival_p
                # P-wave has higher frequency (10-14 Hz) and lower amplitude (~15% of S-wave)
                p_amp = local_amplitude * 0.18
                z[p_mask] += p_amp * np.sin(2.0 * np.pi * 12.0 * tau_p)

        # Compute peak and RMS metrics
        abs_z = np.abs(z)
        peak_g = float(np.max(abs_z))
        rms_g = float(np.sqrt(np.mean(z ** 2)))

        return x, y, z, peak_g, rms_g

    def format_waveform_samples(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
    ) -> List[WaveformSample]:
        """Converts generated numpy arrays into serialized WaveformSample list."""
        samples = []
        n = len(z)
        for i in range(n):
            t_ms = int(round(i * (1000.0 / self.sampling_rate_hz)))
            samples.append(
                WaveformSample(
                    t_offset_ms=t_ms,
                    x=round(float(x[i]), 5),
                    y=round(float(y[i]), 5),
                    z=round(float(z[i]), 5),
                )
            )
        return samples
