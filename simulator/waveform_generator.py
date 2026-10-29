"""
Seismic Waveform Generator Engine (Task L2)

Synthesizes high-frequency 3-axis accelerometer readings (X, Y, Z) mimicking
the physical dynamics of tectonic earthquakes:
- Baseline ambient micro-seismicity (<0.005g Gaussian noise)
- P-wave (compressional) high-frequency precursor arriving first
- S-wave (shear) high-amplitude destructive ground motion arriving later
- Soil amplification (site-specific geological impedance factor)
- Geometric and inelastic wave attenuation based on epicentral distance
"""

import math
import random
from typing import Optional, Tuple, List
import numpy as np

from simulator.config import SAMPLING_RATE_HZ, SEISMIC_TRIGGER_THRESHOLD_G
from simulator.models import WaveformSample


class SeismicEvent:
    """Represents a simulated seismic shockwave propagating through the metropolitan area."""

    def __init__(
        self,
        magnitude: float,
        epicenter_km: Tuple[float, float],
        start_time_s: float,
        duration_s: float = 300.0,
        depth_km: float = 3.0,
        early_warning_delay_s: float = 15.0,
    ):
        self.magnitude = magnitude
        self.epicenter_km = epicenter_km
        self.start_time_s = start_time_s
        self.early_warning_delay_s = early_warning_delay_s
        self.impact_time_s = start_time_s + early_warning_delay_s
        self.duration_s = duration_s
        self.depth_km = depth_km

        # Peak ground acceleration near epicenter scales with magnitude:
        # M3.0 ~ 0.052g, M4.0 ~ 0.125g, M5.3 ~ 0.389g, M6.8 ~ 1.44g
        self.base_pga_g = min(1.8, max(0.025, 0.052 * (10 ** (0.38 * (magnitude - 3.0)))))

        # Characteristic attenuation radius R0 (km) scales with magnitude so:
        # - Minor tremor (M4.0): ~4.5 km trigger radius (~30-45 stations in 1 sector -> 3-4 pods on AKS)
        # - Sector quake (M5.3): ~15.5 km trigger radius (~160-200 stations in 2-3 sectors -> 6-7 pods on AKS)
        # - Major quake (M6.8): ~48+ km trigger radius (all 500 stations across all 5 sectors -> 10/10 pods on AKS)
        self.char_radius_km = 1.05 * (10 ** (0.30 * (magnitude - 3.0)))
        ratio = max(0.05, (self.base_pga_g * 1.1) / SEISMIC_TRIGGER_THRESHOLD_G - 1.0)
        self.trigger_radius_km = round(self.char_radius_km * (ratio ** (1.0 / 1.85)), 1)

        # Seismic wave velocities (calibrated for clear visual propagation & HPA demonstration)
        self.p_velocity_km_s = 2.8  # Compressional P-wave: traverses 25 km in ~9s
        self.s_velocity_km_s = 1.5  # Shear S-wave: trailing P-wave by 1.5s, traversing in ~16s
        self.attenuation_lambda = max(0.015, 0.06 - (magnitude * 0.006))

    def local_pga_at_distance(self, epi_dist_km: float, soil_amplification: float = 1.0) -> float:
        """Computes peak S-wave ground acceleration (in g) at a given epicentral distance."""
        geom_attenuation = 1.0 / (1.0 + ((epi_dist_km / self.char_radius_km) ** 1.85))
        return self.base_pga_g * geom_attenuation * soil_amplification


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
        force_s_wave: bool = False,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
        """
        Generates tri-axial acceleration arrays (x, y, z) for a given time window.
        Returns:
            (x_arr, y_arr, z_arr, peak_acceleration_g, rms_acceleration_g)
        """
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
            local_amplitude = active_event.local_pga_at_distance(epi_dist, self.soil_amplification)

            # P-wave arrives first
            t_arrival_p = active_event.start_time_s + (epi_dist / active_event.p_velocity_km_s)
            # Destructive S-wave arrives later
            t_arrival_s = active_event.impact_time_s + (epi_dist / active_event.s_velocity_km_s)

            if force_s_wave:
                tau_s = np.maximum(0.0, t_absolute - active_event.start_time_s)
                decay = np.exp(-active_event.attenuation_lambda * tau_s)
                oscillation_z = (
                    0.75 * np.sin(2.0 * np.pi * 2.8 * tau_s) +
                    0.25 * np.sin(2.0 * np.pi * 5.6 * tau_s + 0.4)
                )
                z += local_amplitude * decay * oscillation_z
                x += local_amplitude * 0.7 * decay * np.sin(2.0 * np.pi * 2.4 * tau_s + 0.8)
                y += local_amplitude * 0.7 * decay * np.cos(2.0 * np.pi * 2.6 * tau_s + 0.2)
            else:
                # Mask for S-wave arrival (main surface shaking)
                s_mask = (t_absolute >= t_arrival_s) & (t_absolute < (t_arrival_s + active_event.duration_s))
                if np.any(s_mask):
                    tau_s = t_absolute[s_mask] - t_arrival_s
                    decay = np.exp(-active_event.attenuation_lambda * tau_s)

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
                    p_amp = min(0.028, max(0.008, local_amplitude * 0.14))
                    z[p_mask] += p_amp * np.sin(2.0 * np.pi * 14.0 * tau_p)
                    x[p_mask] += (p_amp * 0.5) * np.cos(2.0 * np.pi * 11.0 * tau_p)
                    y[p_mask] += (p_amp * 0.5) * np.sin(2.0 * np.pi * 12.5 * tau_p)

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
