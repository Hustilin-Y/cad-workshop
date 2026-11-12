"""Проверки готовой сетки перед печатью (раздел 6 ТЗ).

Проверки 1–3 (manifold, объём, стол) при провале валят сборку, остальные только предупреждают.
Стол, опора, нависания (3, 5, 6) считаются в ориентации печати: если модель лежит в файле
не так, как печатается, print_down говорит, какая её сторона смотрит в стол.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence

import numpy as np
import trimesh

from .config import Profile

Level = Literal["ok", "warn", "fail", "info"]

DEGENERATE_AREA_MM2 = 1e-10
MIN_SANE_SIZE_MM = 5.0
MAX_SANE_SIZE_MM = 1000.0
BASE_Z_TOL_MM = 0.01
MIN_BASE_AREA_MM2 = 1.0
# Узкое основание у высокой детали: меньше этой доли от проекции на стол при высоте больше
# TALL_FACTOR × ширины пятна (корень из площади) — оторвётся или опрокинется («гриб на ножке»).
MIN_BASE_SHARE = 0.10
TALL_FACTOR = 2.0
OVERHANG_DEG = 45.0
OVERHANG_WARN_SHARE = 0.25  # больше четверти площади нависает круче 45° — без поддержек не обойтись
ISLAND_PROBE_MM = 0.05      # срезы чуть выше и ниже кандидата в «острова»
ISLAND_MERGE_MM = 1.0       # остров, сросшийся с деталью за 1 мм (5 слоёв по 0.2), принтер проходит как нависание
MAX_ISLAND_CANDIDATES = 50  # органика даёт сотни мелких минимумов; проверяем самые крупные

AXIS_NAMES = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+y": (0, 1, 0), "-y": (0, -1, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}


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


def check_mesh(
    mesh: trimesh.Trimesh,
    profile: Profile,
    expected_bodies: int = 1,
    print_down: str | Sequence[float] | None = None,
) -> Report:
    """print_down: сторона модели, которая при печати лежит на столе ('-y' или вектор); None — как в файле (−Z)."""
    report = Report()
    _check_manifold(mesh, report)
    _check_volume_and_bodies(mesh, report, expected_bodies)
    printed = orient_for_print(mesh, print_down)
    if print_down is not None:
        report.add("Ориентация", "info", f"проверки 3, 5, 6 — как при печати: на стол ложится сторона {_axis_label(print_down)}")
    _check_fits_bed(printed, profile, report)
    _check_units(mesh, report)
    _check_base(printed, report)
    _check_support(printed, report)
    _check_overhangs(printed, report)
    return report


def down_vector(print_down: str | Sequence[float]) -> np.ndarray:
    if isinstance(print_down, str):
        key = print_down.strip().lower()
        key = key if key[0] in "+-" else "+" + key
        if key not in AXIS_NAMES:
            raise ValueError(f"сторона «{print_down}»: нужно одно из {', '.join(AXIS_NAMES)} или вектор (x, y, z)")
        return np.array(AXIS_NAMES[key], float)
    v = np.asarray(print_down, float)
    if v.shape != (3,) or not np.linalg.norm(v):
        raise ValueError(f"print_down {print_down!r}: нужен ненулевой вектор (x, y, z)")
    return v / np.linalg.norm(v)


def _axis_label(print_down) -> str:
    v = down_vector(print_down)
    for name, axis in AXIS_NAMES.items():
        if np.allclose(v, axis):
            return name.upper()
    return "(" + ", ".join(f"{c:.2f}" for c in v) + ")"


def orient_for_print(mesh: trimesh.Trimesh, print_down: str | Sequence[float] | None) -> trimesh.Trimesh:
    """Копия, повёрнутая так, чтобы print_down смотрела в −Z (на стол); без print_down — сама сетка."""
    if print_down is None:
        return mesh
    turned = mesh.copy()
    turned.apply_transform(trimesh.geometry.align_vectors(down_vector(print_down), [0, 0, -1]))
    return turned


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


def footprint_area(mesh: trimesh.Trimesh) -> float:
    """Площадь выпуклой оболочки проекции на стол, мм²: «сколько места деталь занимает сверху»."""
    from scipy.spatial import ConvexHull, QhullError

    try:
        return float(ConvexHull(mesh.vertices[:, :2]).volume)  # у 2D-оболочки volume — площадь
    except QhullError:
        return 0.0


def _check_base(mesh: trimesh.Trimesh, report: Report) -> None:
    area = base_area(mesh)
    if area < MIN_BASE_AREA_MM2:
        report.add(
            "5. Основание",
            "warn",
            f"плоского основания почти нет ({area:.2f} мм²) — повернуть деталь в Bambu Studio "
            "(Lay on Face) или нужны поддержки",
        )
        return
    footprint = footprint_area(mesh)
    share = area / footprint if footprint else 1.0
    height = float(mesh.extents[2])
    if share < MIN_BASE_SHARE and height > TALL_FACTOR * np.sqrt(area):
        report.add(
            "5. Основание",
            "warn",
            f"на столе {area:.1f} мм² — {share * 100:.0f}% от проекции детали ({footprint:.0f} мм²) "
            f"при высоте {height:.0f} мм: может оторваться или опрокинуться. Повернуть (Lay on Face), "
            "добавить brim или поддержки",
        )
    else:
        report.add("5. Основание", "ok", f"площадь на столе {area:.1f} мм² ({share * 100:.0f}% проекции)")


def _check_support(mesh: trimesh.Trimesh, report: Report) -> None:
    """Тела, не касающиеся стола, и «острова» — места, где печать начнётся в воздухе."""
    floating = floating_bodies(mesh)
    if floating:
        where = ", ".join(f"{h:.1f}" for h in floating[:5])
        report.add(
            "5. Тела над столом",
            "warn",
            f"{len(floating)} из тел не касается стола (низ на высоте {where} мм): напечатается только на поддержках",
        )
    islands, healed, checked, total = find_islands(mesh)
    notes = []
    if healed:
        notes.append(f"мелких островов, которые в пределах {ISLAND_MERGE_MM:g} мм срастаются с деталью: {healed}")
    if checked < total:
        notes.append(f"проверено {checked} самых крупных из {total} кандидатов")
    note = f" ({'; '.join(notes)})" if notes else ""
    if islands:
        where = "; ".join(f"Z {h:.1f} мм у ({x:.0f}, {y:.0f})" for x, y, h in islands[:3])
        more = f" и ещё {len(islands) - 3}" if len(islands) > 3 else ""
        report.add(
            "5. Острова",
            "warn",
            f"мест, где печать начнётся в воздухе: {len(islands)} — {where}{more}. "
            f"Нужны поддержки или другая ориентация{note}",
        )
    elif not floating:
        report.add("5. Опора", "ok", f"каждый слой опирается на предыдущий{note}")


def floating_bodies(mesh: trimesh.Trimesh) -> list[float]:
    """Высоты низа тел, которые не касаются стола (по возрастанию)."""
    z_min = mesh.bounds[0][2]
    lows = sorted(float(b.bounds[0][2] - z_min) for b in mesh.split(only_watertight=False))
    return [h for h in lows if h > BASE_Z_TOL_MM]


def find_islands(mesh: trimesh.Trimesh) -> tuple[list[tuple[float, float, float]], int, int]:
    """Острова как в слайсере: контур слоя, который не опирается на слой под ним.

    Кандидаты — «нижние площадки» сетки: связные участки одной высоты без соседей ниже, к которым
    сходятся грани, смотрящие вниз (дно кармана смотрит вверх и кандидатом не считается). Кандидат —
    остров, только если контур среза чуть выше него не пересекается со срезом чуть ниже: потолок
    над нишей или подбородок фигурки держатся на остальном сечении слоя, это мост или нависание.
    Тела над столом не считаются (о них отдельное предупреждение). Остров, который в пределах
    ISLAND_MERGE_MM срастается с опёртой частью слоя (губа у подбородка, деталь лого в нише),
    принтер проходит как нависание: такие только считаются.
    Возвращает ([(x, y, высота над столом)], сросшихся, проверено кандидатов, всего кандидатов).
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    from .mesh import to_manifold

    z = mesh.vertices[:, 2]
    z_min = float(z.min())
    n = len(z)
    edges = mesh.edges_unique
    dz = z[edges[:, 0]] - z[edges[:, 1]]
    has_lower = np.zeros(n, bool)
    has_lower[edges[dz > BASE_Z_TOL_MM, 0]] = True
    has_lower[edges[dz < -BASE_Z_TOL_MM, 1]] = True
    flat = np.abs(dz) <= BASE_Z_TOL_MM
    graph = coo_matrix((np.ones(int(flat.sum())), (edges[flat, 0], edges[flat, 1])), shape=(n, n))
    count, label = connected_components(graph, directed=False)

    any_lower = np.zeros(count, bool)
    np.logical_or.at(any_lower, label, has_lower)
    height = np.full(count, np.inf)
    np.minimum.at(height, label, z)
    facing = np.zeros(count)  # сумма площадь × nz граней, касающихся площадки: < 0 — смотрит вниз
    weight = mesh.area_faces * mesh.face_normals[:, 2]
    for col in range(3):
        np.add.at(facing, label[mesh.faces[:, col]], weight)
    on_floating = _floating_vertex_mask(mesh)
    floating_comp = np.zeros(count, bool)
    np.logical_or.at(floating_comp, label, on_floating)

    candidates = np.flatnonzero(~any_lower & (height > z_min + BASE_Z_TOL_MM) & (facing < 0) & ~floating_comp)
    total = len(candidates)
    if not total:
        return [], 0, 0, 0
    candidates = candidates[np.argsort(facing[candidates])][:MAX_ISLAND_CANDIDATES]  # самые крупные первыми
    try:
        solid = to_manifold(mesh)
    except ValueError:
        return [], 0, 0, total  # незамкнутая сетка: проверка 1 уже провалена

    import manifold3d

    slices: dict[float, object] = {}

    def cut(at: float):
        key = round(at, 4)
        if key not in slices:
            slices[key] = solid.slice(key)
        return slices[key]

    islands, seen, healed = [], set(), 0
    for c in candidates:
        h = float(height[c])
        xy = mesh.vertices[label == c][:, :2].mean(axis=0)
        probe = manifold3d.CrossSection.circle(0.3, 16).translate((float(xy[0]), float(xy[1])))
        part = next((p for p in cut(h + ISLAND_PROBE_MM).decompose() if not (p ^ probe).is_empty()), None)
        if part is None:
            continue
        key = (round(h, 2), tuple(np.round(part.bounds(), 2)))
        if key in seen:
            continue
        seen.add(key)
        below = cut(h - ISLAND_PROBE_MM)
        if (part ^ below).area() > 1e-6:
            continue  # опирается на слой ниже: мост или нависание
        grown = next((p for p in cut(h + ISLAND_MERGE_MM).decompose() if not (p ^ probe).is_empty()), None)
        if grown is not None and (grown ^ below).area() > 1e-6:
            healed += 1  # через доли миллиметра срастается с деталью: принтер пройдёт как нависание
            continue
        islands.append((float(xy[0]), float(xy[1]), h - z_min))
    islands.sort(key=lambda item: item[2])
    return islands, healed, len(candidates), total


def _floating_vertex_mask(mesh: trimesh.Trimesh) -> np.ndarray:
    """Вершины тел, которые не касаются стола."""
    z = mesh.vertices[:, 2]
    labels = trimesh.graph.connected_component_labels(mesh.face_adjacency, node_count=len(mesh.faces))
    body_low = np.full(labels.max() + 1 if len(labels) else 0, np.inf)
    np.minimum.at(body_low, labels, z[mesh.faces].min(axis=1))
    face_floating = body_low[labels] > z.min() + BASE_Z_TOL_MM
    mask = np.zeros(len(z), bool)
    mask[mesh.faces[face_floating].ravel()] = True
    return mask


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
    text = f"{frac * 100:.1f}% площади нависает круче {OVERHANG_DEG:g}°"
    if frac > OVERHANG_WARN_SHARE:
        report.add("6. Нависания", "warn", f"{text}: без поддержек не напечатать, или повернуть деталь")
    else:
        report.add("6. Нависания", "info", text)
