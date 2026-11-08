"""Резьба для печати: витки одним телом (профиль, протянутый по спирали).

Профиль — метрический ISO 68-1 (60°): высота витка 5H/8 = 0.5413·P, ширина у основания
7P/8, у вершины P/4.

Особенность OCCT: swept-витки сливаются с втулкой, только если целиком лежат внутри неё
по высоте. Если витки обрезаны заранее или торчат за торец, fuse молча теряет их или
возвращает два тела. Поэтому трубка строится на 2 шага длиннее с каждой стороны,
витки сливаются, а потом готовое тело обрезается до нужной высоты.

Печатная резьба всегда нуждается в зазоре: передавайте диаметр уже с зазором
(THREAD_D + p.slide_fit_mm для внутренней). Зазор брать из профиля принтера.
"""

from __future__ import annotations

from build123d import Box, Cylinder, Helix, Plane, Polygon, Pos, Solid, sweep

ISO_THREAD_H = 0.541266   # высота витка в долях шага (5H/8, H = 0.866P)
ROOT_W = 0.875            # ширина витка у основания в долях шага
CREST_W = 0.25            # ширина витка у вершины в долях шага
EMBED = 0.2               # основание витка заходит в стенку: слияние объёмное, а не по касанию


def minor_diameter(major_d: float, pitch: float) -> float:
    """Внутренний диаметр резьбы (по вершинам витков гайки)."""
    return major_d - 2 * ISO_THREAD_H * pitch


def _ridge(base_r: float, crest_r: float, pitch: float, z0: float, z1: float) -> Solid:
    """Витки правой резьбы от base_r (основание) к crest_r (вершина), примерно от z0 до z1."""
    wb, wt = ROOT_W * pitch, CREST_W * pitch
    profile = Plane.XZ * Polygon((base_r, -wb / 2), (crest_r, -wt / 2), (crest_r, wt / 2), (base_r, wb / 2), align=None)
    ridge = Pos(0, 0, z0) * sweep(profile, path=Helix(pitch=pitch, height=z1 - z0, radius=base_r), is_frenet=True)
    return ridge.solids()[0]


def internal_thread_tube(outer_d: float, major_d: float, pitch: float, length: float) -> Solid:
    """Трубка Ø outer_d высотой length (от Z = 0) с внутренней резьбой Ø major_d по всей высоте."""
    if outer_d <= major_d:
        raise ValueError(f"наружный Ø{outer_d} должен быть больше резьбы Ø{major_d}")
    margin = 2 * pitch
    z0, z1 = -margin, length + margin
    tall = Pos(0, 0, (z0 + z1) / 2) * (Cylinder(outer_d / 2, z1 - z0) - Cylinder(major_d / 2, z1 - z0))
    ridge = _ridge(major_d / 2 + EMBED, major_d / 2 - ISO_THREAD_H * pitch, pitch, z0 + pitch, z1 - pitch)

    fused = tall.solids()[0].fuse(ridge)
    if len(fused.solids()) != 1 or fused.volume < tall.volume + 0.5 * ridge.volume:
        raise RuntimeError("витки не слились с трубкой")  # защита от молчаливой потери витков в OCCT
    trimmed = fused.solids()[0].intersect(Pos(0, 0, length / 2) * Box(outer_d + 2, outer_d + 2, length))
    solids = trimmed.solids()
    if len(solids) != 1:
        raise RuntimeError(f"после обрезки резьбовая трубка распалась на {len(solids)} тел")
    return solids[0]
