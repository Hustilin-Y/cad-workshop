"""Print orientation finder: which side of a part should go on the bed.

Candidates are the six axis directions and the largest flat facets of the convex hull (a part
lies stably only on a hull facet). Each candidate is turned onto the bed and scored with the same
support checks the build report uses: islands, bodies above the bed, a narrow base, overhangs.
The score is a ranking aid, not a verdict: the user still chooses in the slicer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh

from .checks import (
    AXIS_NAMES,
    MIN_BASE_AREA_MM2,
    MIN_BASE_SHARE,
    OVERHANG_WARN_SHARE,
    TALL_FACTOR,
    base_area,
    find_islands,
    floating_bodies,
    footprint_area,
    orient_for_print,
    overhang_fraction,
)
from .config import Profile

HULL_FACETS = 12          # largest hull facets tried besides the six axes
SAME_DIRECTION_DEG = 2.0  # candidates closer than this are one candidate

# Score weights: lower total is better. An island or a floating body almost always means supports,
# so they outweigh everything else; a narrow base risks the print tearing off; overhang share and
# height break ties (less support material, fewer layers).
PENALTY_ISLAND = 40.0
PENALTY_FLOATING = 40.0
PENALTY_NARROW_BASE = 30.0
PENALTY_PER_OVERHANG_PERCENT = 1.0
PENALTY_HEIGHT = 5.0      # × height / largest extent
PENALTY_BASE_SHARE = 10.0  # × (1 − base share)


@dataclass
class Orientation:
    down: tuple[float, float, float]
    label: str
    fits_bed: bool
    height_mm: float
    base_mm2: float
    base_share: float
    overhang_share: float
    islands: int
    floating: int
    score: float
    notes: list[str] = field(default_factory=list)

    @property
    def print_down(self) -> str:
        """The value to put into a model as PRINT_DOWN."""
        for name, axis in AXIS_NAMES.items():
            if np.allclose(self.down, axis, atol=1e-6):
                return f'"{name}"'
        return "(" + ", ".join(f"{c:.3f}" for c in self.down) + ")"


def label_for(down) -> str:
    v = np.asarray(down, float)
    for name, axis in AXIS_NAMES.items():
        if np.allclose(v, axis, atol=1e-6):
            return name.upper()
    return "(" + ", ".join(f"{c:+.2f}" for c in v) + ")"


def candidate_downs(mesh: trimesh.Trimesh, facets: int = HULL_FACETS) -> list[np.ndarray]:
    """Directions to try as "down": the six axes, then hull facets by area, without near-duplicates."""
    found = [np.array(axis, float) for axis in AXIS_NAMES.values()]
    try:
        hull = mesh.convex_hull
        areas = hull.facets_area
        normals = hull.facets_normal
        for i in np.argsort(-areas)[:facets]:
            found.append(np.asarray(normals[i], float))
    except (ValueError, IndexError):
        pass  # flat or degenerate hull: the axes are enough
    unique: list[np.ndarray] = []
    limit = np.cos(np.radians(SAME_DIRECTION_DEG))
    for v in found:
        v = v / np.linalg.norm(v)
        if all(float(v @ u) < limit for u in unique):
            unique.append(v)
    return unique


def evaluate(mesh: trimesh.Trimesh, down, profile: Profile) -> Orientation:
    printed = orient_for_print(mesh, tuple(down))
    size = printed.extents
    limit = profile.usable_volume_mm
    fits = all(a <= b for a, b in zip(sorted(size[:2]), sorted(limit[:2]))) and size[2] <= limit[2]
    area = base_area(printed)
    footprint = footprint_area(printed)
    share = area / footprint if footprint else 1.0
    height = float(size[2])
    narrow = area < MIN_BASE_AREA_MM2 or (share < MIN_BASE_SHARE and height > TALL_FACTOR * np.sqrt(max(area, 1e-9)))
    overhang = overhang_fraction(printed)
    floating = len(floating_bodies(printed))
    islands, _, _, _ = find_islands(printed)

    notes = []
    if not fits:
        notes.append("does not fit the bed")
    if floating:
        notes.append(f"{floating} body(ies) above the bed")
    if islands:
        notes.append(f"{len(islands)} island(s)")
    if narrow:
        notes.append("narrow base")
    if overhang > OVERHANG_WARN_SHARE:
        notes.append("heavy overhangs")

    score = (
        PENALTY_ISLAND * len(islands)
        + PENALTY_FLOATING * floating
        + (PENALTY_NARROW_BASE if narrow else 0.0)
        + PENALTY_PER_OVERHANG_PERCENT * overhang * 100
        + PENALTY_HEIGHT * height / max(float(max(mesh.extents)), 1e-9)
        + PENALTY_BASE_SHARE * (1 - min(share, 1.0))
    )
    v = np.asarray(down, float)
    return Orientation(
        down=tuple(float(c) for c in v / np.linalg.norm(v)),
        label=label_for(v),
        fits_bed=fits,
        height_mm=height,
        base_mm2=area,
        base_share=share,
        overhang_share=overhang,
        islands=len(islands),
        floating=floating,
        score=score,
        notes=notes,
    )


def rank_orientations(mesh: trimesh.Trimesh, profile: Profile) -> list[Orientation]:
    """All candidates, best first; ones that don't fit the bed go last."""
    results = [evaluate(mesh, d, profile) for d in candidate_downs(mesh)]
    return sorted(results, key=lambda o: (not o.fits_bed, o.score))


def print_ready(mesh: trimesh.Trimesh, print_down) -> trimesh.Trimesh:
    """A copy turned so print_down faces the bed and standing on Z = 0: export it to slice as is."""
    turned = orient_for_print(mesh, print_down)
    if turned is mesh:
        turned = mesh.copy()
    turned.apply_translation((0, 0, -turned.bounds[0][2]))
    return turned
