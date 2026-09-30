"""Unit conversion between CMB temperature, Rayleigh-Jeans temperature and flux density."""

import pysm3.units as u

# Label shown to the user -> astropy unit. Order is the order in the pickers.
UNIT_CHOICES = {
    "µK_CMB": u.uK_CMB,
    "mK_CMB": u.mK_CMB,
    "K_CMB": u.K_CMB,
    "µK_RJ": u.uK_RJ,
    "mK_RJ": u.mK_RJ,
    "K_RJ": u.K_RJ,
    "MJy/sr": u.MJy / u.sr,
    "kJy/sr": u.kJy / u.sr,
    "Jy/sr": u.Jy / u.sr,
}


def convert(value: float, from_label: str, to_label: str, freq_ghz: float) -> float:
    """Convert a small brightness fluctuation at one (monochromatic) frequency."""
    quantity = value * UNIT_CHOICES[from_label]
    equivalencies = u.cmb_equivalencies(freq_ghz * u.GHz)
    return float(quantity.to(UNIT_CHOICES[to_label], equivalencies).value)
