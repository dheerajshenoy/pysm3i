"""Dust, synchrotron and free-free with adjustable spectral parameters. No Qt here.

The template maps come from PySM3 (the d0, s0 and f1 presets). The scaling laws below are
the same ones PySM3 applies, written in NumPy so that a slider move recomputes instantly.
"""

from dataclasses import dataclass

import numpy as np
import pysm3

PLANCK = 6.62607015e-34  # J s
BOLTZMANN = 1.380649e-23  # J / K
CURVATURE_PIVOT_GHZ = 23.0  # pivot of the synchrotron curvature term, as in PySM3's s3 and s7

COMPONENTS = {"dust": "Thermal dust", "synchrotron": "Synchrotron", "free_free": "Free-free"}
TEMPLATE_PRESET = {"dust": "d0", "synchrotron": "s0", "free_free": "f1"}


@dataclass(frozen=True)
class Parameter:
    key: str
    label: str
    component: str
    low: float
    high: float
    step: float
    default: float
    suffix: str = ""
    tooltip: str = ""


PARAMETERS = [
    Parameter("beta_d", "β_d", "dust", 0.5, 3.0, 0.01, 1.54, "",
              "Dust emissivity index: how steeply the dust emission rises with frequency"),
    Parameter("temp_d", "T_d", "dust", 5.0, 50.0, 0.1, 20.0, " K",
              "Dust temperature: sets where the dust emission peaks"),
    Parameter("beta_s", "β_s", "synchrotron", -4.5, -1.5, 0.01, -3.0, "",
              "Synchrotron spectral index: how steeply the emission falls with frequency"),
    Parameter("curv_s", "C", "synchrotron", -0.5, 0.5, 0.005, 0.0, "",
              "Spectral curvature: lets the index change with frequency (0 is a pure power law)"),
    Parameter("beta_ff", "β_ff", "free_free", -3.0, -1.0, 0.01, -2.14, "",
              "Free-free spectral index"),
]
DEFAULTS = {p.key: p.default for p in PARAMETERS}


def model_preset(component: str, params: dict[str, float]) -> str:
    """The PySM3 preset whose model type the current parameters correspond to.

    The template maps always come from TEMPLATE_PRESET. Giving synchrotron a non-zero
    curvature turns it into PySM3's curved power law, which the s3 preset uses.
    """
    if component == "synchrotron" and params["curv_s"] != 0:
        return "s3"
    return TEMPLATE_PRESET[component]


@dataclass(frozen=True)
class Template:
    iqu: np.ndarray  # (3, npix) in uK_RJ at the reference frequencies
    freq_ref_i: float  # GHz
    freq_ref_p: float | None  # GHz, or None if the component is unpolarized


def load_templates(nside: int) -> dict[str, Template]:
    """Read the template maps from PySM3 (may download them on first use)."""
    templates = {}
    for component, preset in TEMPLATE_PRESET.items():
        model = pysm3.Sky(nside=nside, preset_strings=[preset]).components[0]
        polarized = model.has_polarization
        iqu = np.stack([
            model.I_ref.value,
            model.Q_ref.value if polarized else np.zeros_like(model.I_ref.value),
            model.U_ref.value if polarized else np.zeros_like(model.I_ref.value),
        ])
        templates[component] = Template(
            iqu,
            float(model.freq_ref_I.value),
            float(model.freq_ref_P.value) if polarized else None,
        )
    return templates


def blackbody_ratio(freq, freq_ref, temp):
    """B_nu(T) / B_nu_ref(T), frequencies in GHz."""
    x = PLANCK * freq * 1e9 / (BOLTZMANN * temp)
    x_ref = PLANCK * freq_ref * 1e9 / (BOLTZMANN * temp)
    return (freq / freq_ref) ** 3 * np.expm1(x_ref) / np.expm1(x)


def scaling(component: str, params: dict[str, float]):
    """Function (freq, freq_ref) -> factor applied to the template, in K_RJ."""
    if component == "dust":
        beta, temp = params["beta_d"], params["temp_d"]
        # the -2 converts the flux-density law to a Rayleigh-Jeans temperature
        return lambda f, f0: (f / f0) ** (beta - 2.0) * blackbody_ratio(f, f0, temp)
    if component == "synchrotron":
        beta, curvature = params["beta_s"], params["curv_s"]
        return lambda f, f0: (f / f0) ** (beta + curvature * np.log(f / CURVATURE_PIVOT_GHZ))
    beta = params["beta_ff"]
    return lambda f, f0: (f / f0) ** beta


def component_maps(templates, params, enabled, freq_ghz: float) -> dict[str, np.ndarray]:
    """I, Q, U of each enabled component at one frequency, (3, npix) in uK_RJ."""
    maps = {}
    for component in COMPONENTS:
        if not enabled.get(component):
            continue
        template, factor = templates[component], scaling(component, params)
        out = np.zeros_like(template.iqu)
        out[0] = template.iqu[0] * factor(freq_ghz, template.freq_ref_i)
        if template.freq_ref_p is not None:
            out[1:] = template.iqu[1:] * factor(freq_ghz, template.freq_ref_p)
        maps[component] = out
    return maps


def pixel_spectra(templates, params, enabled, pixel: int, freqs_ghz) -> dict[str, np.ndarray]:
    """I, Q, U of each enabled component at one pixel over many frequencies, (3, nfreq) in uK_RJ."""
    freqs = np.asarray(freqs_ghz, dtype=float)
    spectra = {}
    for component in COMPONENTS:
        if not enabled.get(component):
            continue
        template, factor = templates[component], scaling(component, params)
        out = np.zeros((3, freqs.size))
        out[0] = template.iqu[0, pixel] * factor(freqs, template.freq_ref_i)
        if template.freq_ref_p is not None:
            out[1:] = template.iqu[1:, pixel, None] * factor(freqs, template.freq_ref_p)
        spectra[component] = out
    return spectra
