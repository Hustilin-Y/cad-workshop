"""Загрузка printer.toml и расчёт действующих допусков под сопло и пластик."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRINTER_TOML = ROOT / "printer.toml"


@dataclass(frozen=True)
class Profile:
    printer: str
    build_volume_mm: tuple[float, float, float]
    bed_margin_mm: float
    nozzle_mm: float
    material: str
    min_wall_mm: float
    layer_mm: float
    hole_clearance_mm: float
    press_fit_mm: float
    slide_fit_mm: float
    material_note: str
    density_g_cm3: float = 1.24      # filament density, for the weight estimate
    price_per_kg: float | None = None  # spool price; None — the report shows no cost
    currency: str = "UAH"
    infill_share: float = 0.15       # infill the weight estimate assumes

    @property
    def usable_volume_mm(self) -> tuple[float, float, float]:
        """Объём стола с запасом bed_margin_mm по XY (с каждой стороны) и сверху."""
        x, y, z = self.build_volume_mm
        m = self.bed_margin_mm
        return (x - 2 * m, y - 2 * m, z - m)


def _nozzle_key(nozzle: float) -> str:
    return f"{nozzle:g}"


def load_profile(
    nozzle: float | None = None,
    material: str | None = None,
    path: Path = PRINTER_TOML,
) -> Profile:
    """Профиль из printer.toml; nozzle/material переопределяют значения по умолчанию."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    printer = data["printer"]
    tol = data["tolerances"]

    nozzle = nozzle if nozzle is not None else float(printer["nozzle_mm"])
    material = (material or printer["material"]).upper()

    nozzles = data.get("nozzles", {})
    if _nozzle_key(nozzle) not in nozzles:
        raise ValueError(f"Сопло {nozzle} мм не описано в printer.toml, есть: {', '.join(nozzles)}")
    nz = nozzles[_nozzle_key(nozzle)]

    materials = data.get("materials", {})
    if material not in materials:
        raise ValueError(f"Пластик {material} не описан в printer.toml, есть: {', '.join(materials)}")
    mat = materials[material]
    add = float(mat.get("clearance_add_mm", 0.0))

    return Profile(
        printer=printer["model"],
        build_volume_mm=tuple(float(v) for v in printer["build_volume_mm"]),
        bed_margin_mm=float(printer.get("bed_margin_mm", 5)),
        nozzle_mm=nozzle,
        material=material,
        min_wall_mm=float(nz["min_wall_mm"]),
        layer_mm=float(nz["layer_mm"]),
        hole_clearance_mm=float(tol["hole_clearance_mm"]) + add,
        press_fit_mm=float(tol["press_fit_mm"]) + add,
        slide_fit_mm=float(tol["slide_fit_mm"]) + add,
        material_note=mat.get("note", ""),
        density_g_cm3=float(mat.get("density_g_cm3", 1.24)),
        price_per_kg=float(mat["price_per_kg"]) if "price_per_kg" in mat else None,
        currency=str(data.get("estimate", {}).get("currency", "UAH")),
        infill_share=float(data.get("estimate", {}).get("infill_share", 0.15)),
    )
