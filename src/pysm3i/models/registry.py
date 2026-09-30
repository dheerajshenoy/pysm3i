"""Model catalog: PySM3 preset configs merged with our own descriptions."""

import tomllib
from dataclasses import dataclass, field
from functools import cache
from importlib.resources import files

import pysm3
from pysm3.sky import PRESET_MODELS


@dataclass(frozen=True)
class Preset:
    name: str
    component: str
    summary: str
    reference: str
    spatial_variation: str
    kind: str
    sed_class: str
    config: dict = field(repr=False)

    @property
    def is_large(self) -> bool:
        """Needs high-resolution templates, which trigger big downloads."""
        return "available_nside" in self.config or self.config.get("max_nside", 0) >= 2048

    @property
    def n_components(self) -> int:
        """Multi-component presets (d4, a1, a2) nest one config per component."""
        return 1 if "class" in self.config else len(self.config)


@dataclass(frozen=True)
class Equation:
    title: str
    latex: tuple[str, ...]  # mathtext lines, possibly empty
    where: str  # plain-text explanation of the symbols


@dataclass(frozen=True)
class Component:
    key: str
    name: str
    summary: str
    sed: str
    presets: tuple[Preset, ...]


# Display order: the main Galactic foregrounds first, then the rest.
COMPONENT_ORDER = ["dust", "synchrotron", "free_free", "ame", "cmb", "co",
                   "cib", "radio_galaxies", "sz", "dipole"]


def _sed_class(config: dict) -> str:
    if "class" in config:
        return config["class"]
    # multi-component presets (d4, a1, a2) nest one config per component
    return " + ".join(sub["class"] for sub in config.values())


def _class_names(config: dict) -> list[str]:
    if "class" in config:
        return [config["class"]]
    return [sub["class"] for sub in config.values()]


class Registry:
    def __init__(self, components: list[Component], equations: dict[str, Equation]):
        self.components = components
        self._equations = equations
        self._presets = {p.name: p for c in components for p in c.presets}

    def equations_for(self, preset: Preset) -> list[Equation]:
        """Equations for a preset, found through its classes' ancestry. No duplicates."""
        found: dict[str, Equation] = {}
        for class_name in _class_names(preset.config):
            candidates = [class_name]
            if class_name == "SimpleSZ":
                candidates.insert(0, f"SimpleSZ.{preset.kind}")
            candidates += [c.__name__ for c in getattr(pysm3, class_name).__mro__[1:]]
            key = next((c for c in candidates if c in self._equations), None)
            if key is not None:
                found.setdefault(key, self._equations[key])
        return list(found.values())

    def __getitem__(self, name: str) -> Preset:
        return self._presets[name]

    def __iter__(self):
        return iter(self._presets.values())

    def __len__(self) -> int:
        return len(self._presets)


@cache
def load_registry() -> Registry:
    data_dir = files("pysm3i.models") / "data"
    components = []
    for path in sorted(data_dir.iterdir(), key=lambda p: p.name):
        if not path.name.endswith(".toml"):
            continue
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        key = path.name.removesuffix(".toml")
        presets = tuple(
            Preset(
                name=name,
                component=key,
                summary=meta["summary"],
                reference=meta.get("reference", ""),
                spatial_variation=meta.get("spatial_variation", ""),
                kind=meta.get("kind", ""),
                sed_class=_sed_class(PRESET_MODELS[name]),
                config=PRESET_MODELS[name],
            )
            for name, meta in raw["presets"].items()
        )
        info = raw["component"]
        components.append(
            Component(key, info["name"], info["summary"], info["sed"], presets)
        )
    components.sort(key=lambda c: COMPONENT_ORDER.index(c.key) if c.key in COMPONENT_ORDER else len(COMPONENT_ORDER))
    raw = tomllib.loads((files("pysm3i.models") / "equations.toml").read_text(encoding="utf-8"))
    equations = {
        key: Equation(entry["title"], tuple(entry["latex"]), entry["where"])
        for key, entry in raw["classes"].items()
    }
    return Registry(components, equations)
