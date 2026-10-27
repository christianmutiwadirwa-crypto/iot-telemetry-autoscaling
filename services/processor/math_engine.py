"""
Seismic Signal Processing Engine (Task L13)
Computes Peak Ground Acceleration (PGA), RMS, and Fast Fourier Transform (FFT)
spectral properties from raw accelerometer waveforms.
"""

from typing import List, Tuple, Dict, Any
import numpy as np


class SeismicMathEngine:
    """Vectorized mathematical engine for real-time seismic vibration analysis."""

    @staticmethod
    def extract_z_array(samples: List[Dict[str, Any]]) -> np.ndarray:
        """Extracts vertical Z acceleration component from sample list."""
        if not samples:
            return np.array([], dtype=np.float64)
        return np.array([s.get("z", 0.0) for s in samples], dtype=np.float64)

    @staticmethod
    def compute_peak(z_arr: np.ndarray) -> float:
        """Computes peak absolute acceleration in g."""
        if len(z_arr) == 0:
            return 0.0
        return float(np.max(np.abs(z_arr)))

    @staticmethod
    def compute_rms(z_arr: np.ndarray) -> float:
        """Computes Root-Mean-Square acceleration in g."""
        if len(z_arr) == 0:
            return 0.0
        return float(np.sqrt(np.mean(z_arr ** 2)))

    @staticmethod
    def compute_fft(
        z_arr: np.ndarray,
        sampling_rate_hz: int = 1000,
    ) -> Tuple[float, float]:
        """
        Calculates Fast Fourier Transform (FFT) frequency spectrum.
        Returns:
            (dominant_frequency_hz, spectral_energy)
        """
        n = len(z_arr)
        if n < 4:
            return 0.0, 0.0

        # Remove DC component (detrend / mean subtraction)
        z_detrended = z_arr - np.mean(z_arr)

        # Real Fast Fourier Transform
        fft_vals = np.fft.rfft(z_detrended)
        freqs = np.fft.rfftfreq(n, d=1.0 / sampling_rate_hz)

        # Power spectrum
        power = np.abs(fft_vals) ** 2

        # Ignore DC index (0 Hz) to avoid static bias
        if len(freqs) > 1:
            peak_idx = 1 + int(np.argmax(power[1:]))
            dominant_freq_hz = float(freqs[peak_idx])
        else:
            dominant_freq_hz = 0.0

        # Integrated spectral energy
        spectral_energy = float(np.sum(power) / n)

        return round(dominant_freq_hz, 2), round(spectral_energy, 4)

    @classmethod
    def analyze_waveform(
        cls,
        samples: List[Dict[str, Any]],
        sampling_rate_hz: int = 1000,
    ) -> Dict[str, float]:
        """
        End-to-end extraction: returns PGA, RMS, dominant frequency, and spectral energy.
        """
        z_arr = cls.extract_z_array(samples)
        peak_g = cls.compute_peak(z_arr)
        rms_g = cls.compute_rms(z_arr)
        dom_freq, energy = cls.compute_fft(z_arr, sampling_rate_hz)

        return {
            "peak_acceleration_g": round(peak_g, 5),
            "rms_acceleration_g": round(rms_g, 5),
            "dominant_frequency_hz": dom_freq,
            "spectral_energy": energy,
        }
