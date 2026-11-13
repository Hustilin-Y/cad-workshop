"""Checks of a finished mesh before printing (section 6 of the spec).

Checks 1–3 (manifold, volume, bed) fail the build; the others only warn.
Bed, support and overhangs (3, 5, 6) are judged in the print orientation: if the model lies in
the file differently from how it's printed, print_down says which of its sides faces the bed.
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
# A narrow base under a tall part: less than this share of the footprint while the part is taller
# than TALL_FACTOR × the width of the contact patch (square root of its area) — it tears off or
# tips over (a "mushroom on a stem").
MIN_BASE_SHARE = 0.10
TALL_FACTOR = 2.0
OVERHANG_DEG = 45.0
OVERHANG_WARN_SHARE = 0.25  # over a quarter of the area steeper than 45°: it won't print without supports
ISLAND_PROBE_MM = 0.05      # slices just above and below an island candidate
ISLAND_MERGE_MM = 1.0       # an island that joins the part within 1 mm (5 layers of 0.2) prints like an overhang
MAX_ISLAND_CANDIDATES = 50  # organic shapes give hundreds of tiny minima; the largest are checked

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
    """print_down: the side of the model that lies on the bed when printed ('-y' or a vector); None — as in the file (−Z)."""
    report = Report()
    _check_manifold(mesh, report)
    _check_volume_and_bodies(mesh, report, expected_bodies)
    printed = orient_for_print(mesh, print_down)
    if print_down is not None:
        report.add("Orientation", "info", f"checks 3, 5, 6 as printed: {_axis_label(print_down)} on the bed")
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
            raise ValueError(f"side {print_down!r}: expected one of {', '.join(AXIS_NAMES)} or a vector (x, y, z)")
        return np.array(AXIS_NAMES[key], float)
    v = np.asarray(print_down, float)
    if v.shape != (3,) or not np.linalg.norm(v):
        raise ValueError(f"print_down {print_down!r}: expected a non-zero vector (x, y, z)")
    return v / np.linalg.norm(v)


def _axis_label(print_down) -> str:
    v = down_vector(print_down)
    for name, axis in AXIS_NAMES.items():
        if np.allclose(v, axis):
            return name.upper()
    return "(" + ", ".join(f"{c:.2f}" for c in v) + ")"


def orient_for_print(mesh: trimesh.Trimesh, print_down: str | Sequence[float] | None) -> trimesh.Trimesh:
    """A copy turned so print_down faces −Z (the bed); without print_down, the mesh itself."""
    if print_down is None:
        return mesh
    turned = mesh.copy()
    turned.apply_transform(trimesh.geometry.align_vectors(down_vector(print_down), [0, 0, -1]))
    return turned


def _check_manifold(mesh: trimesh.Trimesh, report: Report) -> None:
    degenerate = int(np.count_nonzero(mesh.area_faces < DEGENERATE_AREA_MM2))
    problems = []
    if not mesh.is_watertight:
        problems.append("the mesh is not closed (holes or stray edges)")
    if not mesh.is_winding_consistent:
        problems.append("triangle normals point inconsistently")
    if degenerate:
        problems.append(f"degenerate triangles: {degenerate}")
    if problems:
        report.add("1. Mesh", "fail", "; ".join(problems))
    else:
        report.add("1. Mesh", "ok", f"closed, manifold, {len(mesh.faces)} triangles")


def _check_volume_and_bodies(mesh: trimesh.Trimesh, report: Report, expected_bodies: int) -> None:
    volume = float(mesh.volume)
    if volume <= 0:
        report.add("2. Volume", "fail", f"volume {volume:.2f} mm³ (≤ 0, is the mesh inside out?)")
    else:
        report.add("2. Volume", "ok", f"{volume:.1f} mm³ ({volume / 1000:.2f} cm³)")
    bodies = len(mesh.split(only_watertight=False))
    if bodies != expected_bodies:
        report.add("2. Bodies", "warn", f"separate bodies: {bodies}, expected {expected_bodies}")
    else:
        report.add("2. Bodies", "ok", f"separate bodies: {bodies}")


def _check_fits_bed(mesh: trimesh.Trimesh, profile: Profile, report: Report) -> None:
    size = mesh.extents
    limit = profile.usable_volume_mm
    dims = f"{size[0]:.1f} × {size[1]:.1f} × {size[2]:.1f} mm"
    # The part may be turned 90° on the bed, so XY is compared sorted.
    fits_xy = all(a <= b for a, b in zip(sorted(size[:2]), sorted(limit[:2])))
    if fits_xy and size[2] <= limit[2]:
        report.add("3. Bed", "ok", f"{dims}, fits {limit[0]:g} × {limit[1]:g} × {limit[2]:g}")
    else:
        report.add(
            "3. Bed",
            "fail",
            f"{dims} does not fit {limit[0]:g} × {limit[1]:g} × {limit[2]:g} mm "
            f"(the {profile.printer} bed with a {profile.bed_margin_mm:g} mm margin)",
        )


def _check_units(mesh: trimesh.Trimesh, report: Report) -> None:
    largest = float(max(mesh.extents))
    if largest < MIN_SANE_SIZE_MM:
        report.add("4. Units", "warn", f"largest size {largest:.3f} mm: is the model in metres or inches?")
    elif largest > MAX_SANE_SIZE_MM:
        report.add("4. Units", "warn", f"largest size {largest:.0f} mm: is the model in microns, or ×25.4?")
    else:
        report.add("4. Units", "ok", f"plausible scale (largest {largest:.1f} mm)")


def base_area(mesh: trimesh.Trimesh) -> float:
    """Area of the faces lying at the lowest Z and facing down."""
    z_min = mesh.bounds[0][2]
    tri_z = mesh.triangles[:, :, 2]
    on_base = np.all(np.abs(tri_z - z_min) < BASE_Z_TOL_MM, axis=1) & (mesh.face_normals[:, 2] < -0.999)
    return float(mesh.area_faces[on_base].sum())


def footprint_area(mesh: trimesh.Trimesh) -> float:
    """Area of the convex hull of the projection on the bed, mm²: how much room the part takes from above."""
    from scipy.spatial import ConvexHull, QhullError

    try:
        return float(ConvexHull(mesh.vertices[:, :2]).volume)  # a 2D hull's volume is its area
    except QhullError:
        return 0.0


def _check_base(mesh: trimesh.Trimesh, report: Report) -> None:
    area = base_area(mesh)
    if area < MIN_BASE_AREA_MM2:
        report.add(
            "5. Base",
            "warn",
            f"almost no flat base ({area:.2f} mm²): turn the part in the slicer (Lay on Face) or it needs supports",
        )
        return
    footprint = footprint_area(mesh)
    share = area / footprint if footprint else 1.0
    height = float(mesh.extents[2])
    if share < MIN_BASE_SHARE and height > TALL_FACTOR * np.sqrt(area):
        report.add(
            "5. Base",
            "warn",
            f"{area:.1f} mm² on the bed, {share * 100:.0f}% of the part's footprint ({footprint:.0f} mm²) "
            f"at {height:.0f} mm tall: it may tear off or tip over. Turn it (Lay on Face), add a brim or supports",
        )
    else:
        report.add("5. Base", "ok", f"{area:.1f} mm² on the bed ({share * 100:.0f}% of the footprint)")


def _check_support(mesh: trimesh.Trimesh, report: Report) -> None:
    """Bodies that don't touch the bed, and islands: places where printing starts in the air."""
    floating = floating_bodies(mesh)
    if floating:
        where = ", ".join(f"{h:.1f}" for h in floating[:5])
        report.add(
            "5. Bodies above the bed",
            "warn",
            f"{len(floating)} of the bodies don't touch the bed (bottom at {where} mm): they print only on supports",
        )
    islands, healed, checked, total = find_islands(mesh)
    notes = []
    if healed:
        notes.append(f"small islands that join the part within {ISLAND_MERGE_MM:g} mm: {healed}")
    if checked < total:
        notes.append(f"checked the {checked} largest of {total} candidates")
    note = f" ({'; '.join(notes)})" if notes else ""
    if islands:
        where = "; ".join(f"Z {h:.1f} mm at ({x:.0f}, {y:.0f})" for x, y, h in islands[:3])
        more = f" and {len(islands) - 3} more" if len(islands) > 3 else ""
        report.add(
            "5. Islands",
            "warn",
            f"places where printing starts in the air: {len(islands)}: {where}{more}. "
            f"Needs supports or another orientation{note}",
        )
    elif not floating:
        report.add("5. Support", "ok", f"every layer rests on the one below{note}")


def floating_bodies(mesh: trimesh.Trimesh) -> list[float]:
    """Heights of the bottoms of bodies that don't touch the bed, lowest first."""
    z_min = mesh.bounds[0][2]
    lows = sorted(float(b.bounds[0][2] - z_min) for b in mesh.split(only_watertight=False))
    return [h for h in lows if h > BASE_Z_TOL_MM]


def find_islands(mesh: trimesh.Trimesh) -> tuple[list[tuple[float, float, float]], int, int, int]:
    """Islands as a slicer sees them: a contour of a layer that doesn't rest on the layer below.

    Candidates are the mesh's "low plateaus": connected areas of one height with no lower neighbour
    and facing down (a pocket floor faces up and is no candidate). A candidate is an island only if
    the slice contour just above it doesn't overlap the slice just below: a ceiling over a niche or
    a figurine's chin rests on the rest of the layer's section, which is a bridge or an overhang.
    Bodies above the bed don't count (they get their own warning). An island that joins the
    supported part of the layer within ISLAND_MERGE_MM (a lip under a chin, a logo detail in a
    niche) prints like an overhang: those are only counted.
    Returns ([(x, y, height above the bed)], joined, candidates checked, candidates in all).
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
    facing = np.zeros(count)  # sum of area × nz of the faces touching the plateau: < 0 faces down
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
    candidates = candidates[np.argsort(facing[candidates])][:MAX_ISLAND_CANDIDATES]  # largest first
    try:
        solid = to_manifold(mesh)
    except ValueError:
        return [], 0, 0, total  # an open mesh: check 1 has failed already

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
            continue  # rests on the layer below: a bridge or an overhang
        grown = next((p for p in cut(h + ISLAND_MERGE_MM).decompose() if not (p ^ probe).is_empty()), None)
        if grown is not None and (grown ^ below).area() > 1e-6:
            healed += 1  # joins the part a fraction of a millimetre higher: prints like an overhang
            continue
        islands.append((float(xy[0]), float(xy[1]), h - z_min))
    islands.sort(key=lambda item: item[2])
    return islands, healed, len(candidates), total


def _floating_vertex_mask(mesh: trimesh.Trimesh) -> np.ndarray:
    """Vertices of the bodies that don't touch the bed."""
    z = mesh.vertices[:, 2]
    labels = trimesh.graph.connected_component_labels(mesh.face_adjacency, node_count=len(mesh.faces))
    body_low = np.full(labels.max() + 1 if len(labels) else 0, np.inf)
    np.minimum.at(body_low, labels, z[mesh.faces].min(axis=1))
    face_floating = body_low[labels] > z.min() + BASE_Z_TOL_MM
    mask = np.zeros(len(z), bool)
    mask[mesh.faces[face_floating].ravel()] = True
    return mask


def overhang_fraction(mesh: trimesh.Trimesh, angle_deg: float = OVERHANG_DEG) -> float:
    """Share of the area overhanging steeper than angle_deg from vertical (not counting faces on the bed)."""
    z_min = mesh.bounds[0][2]
    limit = -np.sin(np.radians(angle_deg))
    down = mesh.face_normals[:, 2] < limit
    on_bed = np.all(np.abs(mesh.triangles[:, :, 2] - z_min) < BASE_Z_TOL_MM, axis=1)
    return float(mesh.area_faces[down & ~on_bed].sum() / mesh.area)


EXPECTED_DELTA_REL_TOL = 0.01  # ±1% of the expected volume change (the spec's criterion)
EXPECTED_DELTA_FLOOR_REL = 0.001  # but no less than 0.1% of the original's volume


def compare_to_original(
    original: trimesh.Trimesh,
    result: trimesh.Trimesh,
    report: Report,
    expected_delta_mm3: float | None = None,
) -> None:
    """Check 7: what the remix edit changed, and whether it touched anything else."""
    v0, v1 = float(original.volume), float(result.volume)
    delta = v1 - v0
    pct = delta / v0 * 100 if v0 else float("nan")
    report.add("7. Volume vs original", "info", f"{v0:.1f} → {v1:.1f} mm³ ({delta:+.1f} mm³, {pct:+.2f}%)")

    e0, e1 = original.extents, result.extents
    dims = " × ".join(f"{a:.2f}" for a in e0) + " → " + " × ".join(f"{b:.2f}" for b in e1)
    changed = [ax for ax, a, b in zip("XYZ", e0, e1) if abs(a - b) > 0.01]
    shift = result.bounds[0] - original.bounds[0]
    moved = np.abs(shift).max() > 0.01
    note = f"size changed along {', '.join(changed)}" if changed else "same size"
    if moved:
        note += f"; moved by ({shift[0]:+.2f}, {shift[1]:+.2f}, {shift[2]:+.2f}) mm"
    report.add("7. Size vs original", "info", f"{dims} mm: {note}")

    if abs(delta) < 1e-3 and not changed and not moved:
        report.add("7. Edit", "warn", "the result equals the original: did the edit change anything?")
    if expected_delta_mm3 is not None:
        err = abs(delta - expected_delta_mm3)
        # With an expected zero (a move, a turn) 1% of zero is 0: allow a floor share of the original for tessellation noise.
        limit = max(abs(expected_delta_mm3) * EXPECTED_DELTA_REL_TOL, abs(v0) * EXPECTED_DELTA_FLOOR_REL)
        level = "ok" if err <= limit else "warn"
        report.add(
            "7. Expected change",
            level,
            f"expected {expected_delta_mm3:+.1f} mm³, got {delta:+.1f} (off by {err:.1f}, tolerance ±{limit:.1f})",
        )


def _check_overhangs(mesh: trimesh.Trimesh, report: Report) -> None:
    frac = overhang_fraction(mesh)
    text = f"{frac * 100:.1f}% of the area overhangs steeper than {OVERHANG_DEG:g}°"
    if frac > OVERHANG_WARN_SHARE:
        report.add("6. Overhangs", "warn", f"{text}: it won't print without supports, or turn the part")
    else:
        report.add("6. Overhangs", "info", text)
