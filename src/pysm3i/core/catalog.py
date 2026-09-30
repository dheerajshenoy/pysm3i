from dataclasses import dataclass
from pysm3.sky import PRESET_MODELS

COMPONENTS = {
    "d": "Thermal dust", "s": "Synchrotron", "f": "Free-free",
    "a": "Anomalous microwave emission", "c": "CMB",
    "co": "CO lines", "cib": "Cosmic infrared background",
    "rg": "Radio galaxies", "ksz": "Kinetic SZ", "tsz": "Thermal SZ",
    "dip": "CMB dipole",
}

@dataclass(frozen=True)
class Preset:
    name: str
    component: str
    sed_class: str
    config: dict

def _component_of(name: str) -> str:
    prefix = name.rstrip("0123456789")   # "cib1" -> "cib", "d10" -> "d"
    return COMPONENTS[prefix]

def load_presets() -> list[Preset]:
    return [
        Preset(n, _component_of(n), cfg["class"], cfg)
        for n, cfg in PRESET_MODELS.items()
    ]
