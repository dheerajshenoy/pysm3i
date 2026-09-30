"""Model catalog: PySM3 preset configs merged with our own descriptions."""

import tomllib
from dataclasses import dataclass, field
from functools import cache
from importlib.resources import files

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


@dataclass(frozen=True)
class Component:
    key: str
    name: str
    summary: str
    sed: str
    presets: tuple[Preset, ...]


def _sed_class(config: dict) -> str:
    if "class" in config:
        return config["class"]
    # multi-component presets (d4, a1, a2) nest one config per component
    return " + ".join(sub["class"] for sub in config.values())


class Registry:
    def __init__(self, components: list[Component]):
        self.components = components
        self._presets = {p.name: p for c in components for p in c.presets}

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
    return Registry(components)
