"""Where a part lives: its environment or service temperature against the plastic's heat limit.

A model declares `ENVIRONMENT = "car-dash"` (a preset in printer.toml [environments.*]) or
`SERVICE_TEMP_C = 65`. The plastic passes when its `hdt_c` (HDT at 0.45 MPa, from the maker's data
sheet) minus `[service] margin_c` is at least that temperature. Presets marked `sun` add a UV
warning for plastics not marked `uv_resistant`.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .checks import Report
from .config import PRINTER_TOML


@dataclass(frozen=True)
class Service:
    label: str      # the preset's name, or "65 °C" for a bare temperature
    temp_c: float
    sun: bool


def _data(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def service_of(module, path: Path = PRINTER_TOML) -> Service | None:
    """The model's declared environment, or None. ValueError for a bad declaration."""
    env = getattr(module, "ENVIRONMENT", None)
    temp = getattr(module, "SERVICE_TEMP_C", None)
    if env is not None and temp is not None:
        raise ValueError("ENVIRONMENT and SERVICE_TEMP_C: give one, not both")
    if env is not None:
        presets = _data(path).get("environments", {})
        if env not in presets:
            raise ValueError(f"ENVIRONMENT = {env!r}: no such preset, there are: {', '.join(presets)}")
        preset = presets[env]
        return Service(env, float(preset["temp_c"]), bool(preset.get("sun", False)))
    if temp is not None:
        if isinstance(temp, bool) or not isinstance(temp, (int, float)):
            raise ValueError(f"SERVICE_TEMP_C = {temp!r}: expected a number of °C")
        return Service(f"{temp:g} °C", float(temp), False)
    return None


def _limit(mat: dict, margin: float) -> float | None:
    return None if "hdt_c" not in mat else float(mat["hdt_c"]) - margin


def passing(temp_c: float, path: Path = PRINTER_TOML) -> list[str]:
    """Plastics whose HDT minus the margin is at least temp_c."""
    data = _data(path)
    margin = float(data.get("service", {}).get("margin_c", 10))
    return [name for name, mat in data.get("materials", {}).items()
            if (lim := _limit(mat, margin)) is not None and lim >= temp_c - 1e-9]


def check_service(report: Report, service: Service, material: str, build_material: str,
                  path: Path = PRINTER_TOML) -> None:
    """Adds "Environment" (ok, fail or warn), "UV" for sun presets on a non-UV plastic, and
    "Plastic" when the plastic checked is not the one the build's fits were computed for."""
    data = _data(path)
    margin = float(data.get("service", {}).get("margin_c", 10))
    material, build_material = material.upper(), build_material.upper()
    mat = data.get("materials", {}).get(material, {})
    where = f"{service.label} ({service.temp_c:g} °C)" if service.label[0].isalpha() else service.label
    lim = _limit(mat, margin)
    if lim is None:
        report.add("Environment", "warn", f"{where}: {material} has no HDT data, the heat limit is not checked")
    elif lim >= service.temp_c - 1e-9:
        report.add("Environment", "ok", f"{where}: {material} HDT {mat['hdt_c']:g} − {margin:g} = {lim:g} °C")
    else:
        others = passing(service.temp_c, path)
        tail = f"plastics that pass: {', '.join(others)}" if others else "no plastic in printer.toml takes that"
        report.add("Environment", "fail",
                   f"{where}: {material} HDT {mat['hdt_c']:g} − {margin:g} = {lim:g} °C is below it; {tail}")
    if service.sun and not mat.get("uv_resistant", False):
        report.add("UV", "warn", f"{service.label} is in the sun: {material} fades and gets brittle in UV, "
                                 "ASA is UV-resistant")
    if material != build_material:
        report.add("Plastic", "warn", f"checked for {material} (PRINT_HINTS), but the fits were computed for "
                                      f"{build_material}: build with --material {material.lower()}")
