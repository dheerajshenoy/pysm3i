"""Export the map shown on the Sky page: a FITS file, or a pysm3 snippet that recreates it."""

from dataclasses import dataclass

import healpy as hp
import numpy as np

from .skymodel import UNITS


@dataclass(frozen=True)
class SkySnapshot:
    """The maps on screen together with the settings that produced them."""

    presets: tuple[str, ...]
    nside: int
    freq_ghz: float
    unit_label: str  # a key of UNITS
    maps: np.ndarray  # (3, npix): I, Q, U in unit_label

    @property
    def pysm_unit(self) -> str:
        return UNITS[self.unit_label]


def sky_snippet(snapshot: SkySnapshot) -> str:
    """Python code that recreates the snapshot's maps with PySM3."""
    presets = ", ".join(f'"{p}"' for p in snapshot.presets)
    return (
        "import pysm3\n"
        "import pysm3.units as u\n"
        "\n"
        f'sky = pysm3.Sky(nside={snapshot.nside}, preset_strings=[{presets}],\n'
        f'               output_unit="{snapshot.pysm_unit}")\n'
        f"emission = sky.get_emission({snapshot.freq_ghz:.6g} * u.GHz)\n"
        "# emission has shape (3, npix): I, Q, U in HEALPix RING order, Galactic coordinates\n"
        "\n"
        "# To save it as a FITS file:\n"
        "# import healpy as hp\n"
        '# hp.write_map("sky.fits", emission.value, overwrite=True, coord="G")\n'
    )


def write_fits(path: str, snapshot: SkySnapshot) -> None:
    """Write I, Q, U as a three-column HEALPix FITS file with the settings in the header."""
    hp.write_map(
        path,
        snapshot.maps,
        overwrite=True,
        coord="G",
        column_names=["I_STOKES", "Q_STOKES", "U_STOKES"],
        column_units=[snapshot.pysm_unit] * 3,
        extra_header=[
            ("FREQ_GHZ", float(snapshot.freq_ghz), "Frequency in GHz"),
            ("PRESETS", ",".join(snapshot.presets), "PySM3 presets summed"),
            ("CREATOR", "pysm3i", "Written by pysm3i"),
        ],
    )


def default_filename(snapshot: SkySnapshot) -> str:
    return f"pysm3i_{snapshot.freq_ghz:.0f}GHz_nside{snapshot.nside}.fits"
