"""Сводка по модели для `cad.py inspect`: с чем имеем дело перед ремиксом."""

from __future__ import annotations

import numpy as np
import trimesh

from .checks import base_area, overhang_fraction

TOP_FACETS = 3


def describe(mesh: trimesh.Trimesh) -> list[tuple[str, str]]:
    lo, hi = mesh.bounds
    size = hi - lo
    bodies = mesh.split(only_watertight=False)
    rows = [
        ("Габариты", f"{size[0]:.2f} × {size[1]:.2f} × {size[2]:.2f} мм (X × Y × Z)"),
        ("Границы", f"X {lo[0]:.2f}…{hi[0]:.2f}, Y {lo[1]:.2f}…{hi[1]:.2f}, Z {lo[2]:.2f}…{hi[2]:.2f}"),
        ("Объём", f"{mesh.volume:.1f} мм³ ({mesh.volume / 1000:.2f} см³)"),
        ("Площадь поверхности", f"{mesh.area:.1f} мм²"),
        ("Тел", f"{len(bodies)}" + (f" (объёмы: {', '.join(f'{b.volume:.0f}' for b in bodies[:6])} мм³)" if len(bodies) > 1 else "")),
        ("Треугольников", f"{len(mesh.faces)}"),
        ("Замкнута (watertight)", "да" if mesh.is_watertight else "НЕТ"),
        ("Площадь на столе", f"{base_area(mesh):.1f} мм² (грани на минимальном Z)"),
        ("Нависания > 45°", f"{overhang_fraction(mesh) * 100:.1f}% площади в текущей ориентации"),
    ]
    rows += _largest_flats(mesh)
    if not (lo[2] == 0 or abs(lo[2]) < 1e-6):
        rows.append(("Внимание", f"модель не стоит на Z=0 (низ на {lo[2]:.2f} мм), Bambu Studio опустит её сама"))
    return rows


def _largest_flats(mesh: trimesh.Trimesh) -> list[tuple[str, str]]:
    """Крупнейшие плоские грани: кандидаты, какой стороной класть на стол."""
    if len(mesh.facets) == 0:
        return [("Плоские грани", "нет (органика или сильно тесселированная модель)")]
    order = np.argsort(mesh.facets_area)[::-1][:TOP_FACETS]
    z_min = mesh.bounds[0][2]
    rows = []
    for rank, idx in enumerate(order, start=1):
        n = mesh.facets_normal[idx]
        on_bed = bool(np.all(np.abs(mesh.triangles[mesh.facets[idx]][:, :, 2] - z_min) < 0.01))
        rows.append((f"Плоскость #{rank}", f"{mesh.facets_area[idx]:.1f} мм², нормаль ({n[0]:+.2f}, {n[1]:+.2f}, {n[2]:+.2f}){_dir(n, on_bed)}"))
    return rows


def _dir(n: np.ndarray, on_bed: bool) -> str:
    axis = int(np.argmax(np.abs(n)))
    if abs(n[axis]) < 0.99:
        return " — наклонная"
    if axis == 2 and n[2] < 0:
        return " — смотрит вниз, лежит на столе" if on_bed else " — смотрит вниз, над столом"
    names = {(2, 1): " — смотрит вверх", (0, 1): " — +X", (0, -1): " — −X", (1, 1): " — +Y", (1, -1): " — −Y"}
    return names[(axis, int(np.sign(n[axis])))]
