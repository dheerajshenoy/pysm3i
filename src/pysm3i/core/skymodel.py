"""Compute sky emission maps from PySM3 presets, with caching. No Qt here."""

import threading

import numpy as np
import pysm3
import pysm3.units as u

UNITS = {
    "µK_CMB": "uK_CMB",
    "µK_RJ": "uK_RJ",
    "MJy/sr": "MJy/sr",
}

_CACHE_BUDGET_BYTES = 1 << 30  # 1 GiB of cached per-preset maps


class Cancelled(Exception):
    """Raised when a computation is abandoned via its cancel event."""


class SkyModel:
    """Per-preset emission cache. Safe to call from a worker thread."""

    def __init__(self):
        self._skies: dict[tuple[str, int], pysm3.Sky] = {}
        self._emission: dict[tuple[str, int, float], np.ndarray] = {}
        self._lock = threading.Lock()

    def emission(
        self, presets: list[str], nside: int, freq_ghz: float, unit: str,
        cancel: threading.Event | None = None,
    ) -> np.ndarray:
        """Sum of the given presets at one frequency, shape (3, npix): I, Q, U.

        `cancel` is checked between presets. A preset already being computed
        cannot be interrupted, so it finishes (and is cached) before Cancelled
        is raised.
        """
        freq = freq_ghz * u.GHz
        npix = 12 * nside**2
        total = np.zeros((3, npix))
        with self._lock:
            for preset in presets:
                if cancel is not None and cancel.is_set():
                    raise Cancelled
                total += self._preset_emission(preset, nside, freq_ghz)
            if cancel is not None and cancel.is_set():
                raise Cancelled
        converted = (total * u.uK_RJ).to(u.Unit(unit), u.cmb_equivalencies(freq))
        return np.asarray(converted.value)

    def _preset_emission(self, preset: str, nside: int, freq_ghz: float) -> np.ndarray:
        key = (preset, nside, round(freq_ghz, 4))
        if key not in self._emission:
            sky = self._sky(preset, nside)
            emission = sky.get_emission(freq_ghz * u.GHz)
            self._emission[key] = np.asarray(emission.to(u.uK_RJ).value)
            self._evict_over_budget(keep=key)
        return self._emission[key]

    def _evict_over_budget(self, keep):
        while (
            sum(a.nbytes for a in self._emission.values()) > _CACHE_BUDGET_BYTES
            and len(self._emission) > 1
        ):
            oldest = next(k for k in self._emission if k != keep)
            del self._emission[oldest]

    def _sky(self, preset: str, nside: int) -> pysm3.Sky:
        key = (preset, nside)
        if key not in self._skies:
            self._skies[key] = pysm3.Sky(nside=nside, preset_strings=[preset])
        return self._skies[key]
