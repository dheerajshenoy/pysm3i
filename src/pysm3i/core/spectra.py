"""Angular power spectra of sky maps, with a Galactic mask. No Qt here."""

import threading
from dataclasses import dataclass

import healpy as hp
import numpy as np

from .skymodel import Cancelled, SkyModel

SPECTRA = ("TT", "EE", "BB")
APODIZATION_DEG = 5.0  # smoothing of the mask edge, to limit E/B leakage


@dataclass(frozen=True)
class SpectraResult:
    ell: np.ndarray  # 0 .. lmax
    curves: dict[str, np.ndarray]  # preset -> (3, lmax+1) D_ell [uK_CMB^2]: TT, EE, BB
    total: np.ndarray | None  # spectrum of the summed map, when more than one preset
    reference: np.ndarray | None  # lensed CMB, when none of the presets is a CMB


def galactic_mask(nside: int, b_cut_deg: float) -> np.ndarray | None:
    """Keep |b| > b_cut, with a smooth edge. None means full sky."""
    if b_cut_deg <= 0:
        return None
    lat = hp.pix2ang(nside, np.arange(hp.nside2npix(nside)), lonlat=True)[1]
    hard = (np.abs(lat) > b_cut_deg).astype(float)
    return np.clip(hp.smoothing(hard, fwhm=np.radians(APODIZATION_DEG)), 0.0, 1.0)


def dl_spectra(iqu: np.ndarray, nside: int, mask: np.ndarray | None) -> np.ndarray:
    """D_ell = ell (ell + 1) C_ell / 2 pi for TT, EE, BB. Shape (3, 2 * nside + 1).

    A pseudo-C_ell estimate: the maps are multiplied by the mask and the result is
    divided by <mask^2>. This ignores mode coupling, so it is approximate at low ell.
    """
    lmax = 2 * nside
    weight = 1.0
    if mask is not None:
        iqu = iqu * mask
        weight = float(np.mean(mask**2))
    cl = hp.anafast(iqu, pol=True, lmax=lmax)[:3]  # TT, EE, BB
    ell = np.arange(lmax + 1)
    return ell * (ell + 1) / (2 * np.pi) * cl / weight


class SpectraModel:
    """Computes and caches spectra. Safe to call from a worker thread."""

    def __init__(self, sky: SkyModel):
        self._sky = sky
        self._masks: dict[tuple[int, float], np.ndarray | None] = {}
        self._cache: dict[tuple, np.ndarray] = {}
        self._lock = threading.Lock()

    def spectra(
        self, presets: list[str], nside: int, freq_ghz: float, b_cut_deg: float,
        reference: str | None = None, cancel: threading.Event | None = None,
    ) -> SpectraResult:
        curves = {p: self._one([p], nside, freq_ghz, b_cut_deg, cancel) for p in presets}
        total = self._one(presets, nside, freq_ghz, b_cut_deg, cancel) if len(presets) > 1 else None
        ref = self._one([reference], nside, freq_ghz, b_cut_deg, cancel) if reference else None
        return SpectraResult(np.arange(2 * nside + 1), curves, total, ref)

    def _one(self, presets, nside, freq_ghz, b_cut_deg, cancel) -> np.ndarray:
        key = (tuple(presets), nside, round(freq_ghz, 4), b_cut_deg)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        if cancel is not None and cancel.is_set():
            raise Cancelled
        maps = self._sky.emission(presets, nside, freq_ghz, "uK_CMB", cancel)
        with self._lock:
            mask_key = (nside, b_cut_deg)
            if mask_key not in self._masks:
                self._masks[mask_key] = galactic_mask(nside, b_cut_deg)
            self._cache[key] = dl_spectra(maps, nside, self._masks[mask_key])
            return self._cache[key]
