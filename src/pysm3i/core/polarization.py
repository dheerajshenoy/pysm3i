"""E and B polarization maps from Q and U. No Qt here."""

import healpy as hp
import numpy as np


def eb_maps(iqu: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Scalar E and B maps of an (I, Q, U) map set, in the same units as Q and U.

    Q and U are decomposed into spherical harmonics, and each of the E and B harmonic
    coefficients is synthesized back into its own map. Polarization has no ell = 0 or 1
    modes, so those are removed. On a full sky E and B hold exactly the power of Q and U
    between them. The cost grows quickly with nside (seconds at 512, tens of seconds at 1024).
    """
    nside = hp.npix2nside(iqu.shape[1])
    lmax = 3 * nside - 1
    alm = hp.map2alm(iqu, lmax=lmax, pol=True)  # rows: T, E, B
    ell = hp.Alm.getlm(lmax)[0]
    maps = []
    for coefficients in (alm[1], alm[2]):
        coefficients = coefficients.copy()
        coefficients[ell < 2] = 0
        maps.append(hp.alm2map(coefficients, nside, lmax=lmax))
    return maps[0], maps[1]
