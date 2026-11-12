"""Проверки готовой сетки перед печатью (раздел 6 ТЗ).

Проверки 1–3 (manifold, объём, стол) при провале валят сборку, остальные только предупреждают.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import trimesh

from .config import Profile

Level = Literal["ok", "warn", "fail", "info"]

DEGENERATE_AREA_MM2 = 1e-10
MIN_SANE_SIZE_MM = 5.0
MAX_SANE_SIZE_MM = 1000.0
BASE_Z_TOL_MM = 0.01
MIN_BASE_AREA_MM2 = 1.0
OVERHANG_DEG = 45.0


@dataclass
class Check:
    name: str
    level: Level
    message: str


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, level: Level, message: str) -> None:
        self.checks.append(Check(name, level, message))

    @property
    def failed(self) -> bool:
        return any(c.level == "fail" for c in self.checks)

    def format(self) -> str:
        marks = {"ok": "OK  ", "warn": "WARN", "fail": "FAIL", "info": "INFO"}
        return "\n".join(f"[{marks[c.level]}] {c.name}: {c.message}" for c in self.checks)


def check_mesh(mesh: trimesh.Trimesh, profile: Profile, expected_bodies: int = 1) -> Report:
    report = Report()
    _check_manifold(mesh, report)
    _check_volume_and_bodies(mesh, report, expected_bodies)
    _check_fits_bed(mesh, profile, report)
    _check_units(mesh, report)
    _check_base(mesh, report)
    _check_overhangs(mesh, report)
    return report


def _check_manifold(mesh: trimesh.Trimesh, report: Report) -> None:
    degenerate = int(np.count_nonzero(mesh.area_faces < DEGENERATE_AREA_MM2))
    problems = []
    if not mesh.is_watertight:
        problems.append("сетка не замкнута (есть дыры или лишние рёбра)")
    if not mesh.is_winding_consistent:
        problems.append("нормали треугольников направлены несогласованно")
    if degenerate:
        problems.append(f"вырожденных треугольников: {degenerate}")
    if problems:
        report.add("1. Сетка", "fail", "; ".join(problems))
    else:
        report.add("1. Сетка", "ok", f"замкнута, manifold, {len(mesh.faces)} треугольников")


def _check_volume_and_bodies(mesh: trimesh.Trimesh, report: Report, expected_bodies: int) -> None:
    volume = float(mesh.volume)
    if volume <= 0:
        report.add("2. Объём", "fail", f"объём {volume:.2f} мм³ (≤ 0, сетка вывернута?)")
    else:
        report.add("2. Объём", "ok", f"{volume:.1f} мм³ ({volume / 1000:.2f} см³)")
    bodies = len(mesh.split(only_watertight=False))
    if bodies != expected_bodies:
        report.add("2. Тела", "warn", f"отдельных тел: {bodies}, ожидалось {expected_bodies}")
    else:
        report.add("2. Тела", "ok", f"отдельных тел: {bodies}")


def _check_fits_bed(mesh: trimesh.Trimesh, profile: Profile, report: Report) -> None:
    size = mesh.extents
    limit = profile.usable_volume_mm
    dims = f"{size[0]:.1f} × {size[1]:.1f} × {size[2]:.1f} мм"
    # Деталь можно повернуть на столе на 90°, поэтому XY сравниваем отсортированными.
    fits_xy = all(a <= b for a, b in zip(sorted(size[:2]), sorted(limit[:2])))
    if fits_xy and size[2] <= limit[2]:
        report.add("3. Стол", "ok", f"{dims}, влезает в {limit[0]:g} × {limit[1]:g} × {limit[2]:g}")
    else:
        report.add(
            "3. Стол",
            "fail",
            f"{dims} не влезает в {limit[0]:g} × {limit[1]:g} × {limit[2]:g} мм "
            f"(стол {profile.printer} с запасом {profile.bed_margin_mm:g} мм)",
        )


def _check_units(mesh: trimesh.Trimesh, report: Report) -> None:
    largest = float(max(mesh.extents))
    if largest < MIN_SANE_SIZE_MM:
        report.add("4. Единицы", "warn", f"самый большой размер {largest:.3f} мм — модель в метрах или дюймах?")
    elif largest > MAX_SANE_SIZE_MM:
        report.add("4. Единицы", "warn", f"самый большой размер {largest:.0f} мм — модель в микронах или ×25.4?")
    else:
        report.add("4. Единицы", "ok", f"масштаб правдоподобный (макс. {largest:.1f} мм)")


def base_area(mesh: trimesh.Trimesh) -> float:
    """Площадь граней, лежащих на минимальном Z и смотрящих вниз."""
    z_min = mesh.bounds[0][2]
    tri_z = mesh.triangles[:, :, 2]
    on_base = np.all(np.abs(tri_z - z_min) < BASE_Z_TOL_MM, axis=1) & (mesh.face_normals[:, 2] < -0.999)
    return float(mesh.area_faces[on_base].sum())


def _check_base(mesh: trimesh.Trimesh, report: Report) -> None:
    area = base_area(mesh)
    if area < MIN_BASE_AREA_MM2:
        report.add(
            "5. Основание",
            "warn",
            f"плоского основания почти нет ({area:.2f} мм²) — повернуть деталь в Bambu Studio "
            "(Lay on Face) или нужны поддержки",
        )
    else:
        report.add("5. Основание", "ok", f"площадь на столе {area:.1f} мм²")


def overhang_fraction(mesh: trimesh.Trimesh, angle_deg: float = OVERHANG_DEG) -> float:
    """Доля площади, нависающей круче angle_deg от вертикали (без граней, лежащих на столе)."""
    z_min = mesh.bounds[0][2]
    limit = -np.sin(np.radians(angle_deg))
    down = mesh.face_normals[:, 2] < limit
    on_bed = np.all(np.abs(mesh.triangles[:, :, 2] - z_min) < BASE_Z_TOL_MM, axis=1)
    return float(mesh.area_faces[down & ~on_bed].sum() / mesh.area)


EXPECTED_DELTA_REL_TOL = 0.01  # ±1% от ожидаемого изменения объёма (критерий ТЗ)
EXPECTED_DELTA_FLOOR_REL = 0.001  # но не меньше 0.1% объёма оригинала


def compare_to_original(
    original: trimesh.Trimesh,
    result: trimesh.Trimesh,
    report: Report,
    expected_delta_mm3: float | None = None,
) -> None:
    """Проверка 7: что правка ремикса изменила и не задела ли лишнего."""
    v0, v1 = float(original.volume), float(result.volume)
    delta = v1 - v0
    pct = delta / v0 * 100 if v0 else float("nan")
    report.add("7. Объём vs оригинал", "info", f"{v0:.1f} → {v1:.1f} мм³ ({delta:+.1f} мм³, {pct:+.2f}%)")

    e0, e1 = original.extents, result.extents
    dims = " × ".join(f"{a:.2f}" for a in e0) + " → " + " × ".join(f"{b:.2f}" for b in e1)
    changed = [ax for ax, a, b in zip("XYZ", e0, e1) if abs(a - b) > 0.01]
    shift = result.bounds[0] - original.bounds[0]
    moved = np.abs(shift).max() > 0.01
    note = f"габариты изменились по {', '.join(changed)}" if changed else "габариты те же"
    if moved:
        note += f"; модель сдвинута на ({shift[0]:+.2f}, {shift[1]:+.2f}, {shift[2]:+.2f}) мм"
    report.add("7. Габариты vs оригинал", "info", f"{dims} мм — {note}")

    if abs(delta) < 1e-3 and not changed and not moved:
        report.add("7. Правка", "warn", "результат совпадает с оригиналом — правка ничего не изменила?")
    if expected_delta_mm3 is not None:
        err = abs(delta - expected_delta_mm3)
        # При ожидаемом нуле (перенос, поворот) 1% от нуля = 0: берём ещё пол от объёма оригинала на шум тесселяции.
        limit = max(abs(expected_delta_mm3) * EXPECTED_DELTA_REL_TOL, abs(v0) * EXPECTED_DELTA_FLOOR_REL)
        level = "ok" if err <= limit else "warn"
        report.add("7. Ожидаемое изменение", level, f"ожидалось {expected_delta_mm3:+.1f} мм³, получено {delta:+.1f} (расхождение {err:.1f}, допуск ±{limit:.1f})")


def _check_overhangs(mesh: trimesh.Trimesh, report: Report) -> None:
    frac = overhang_fraction(mesh)
    report.add("6. Нависания", "info", f"{frac * 100:.1f}% площади нависает круче {OVERHANG_DEG:g}° в текущей ориентации")
