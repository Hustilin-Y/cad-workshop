"""Strict printability helpers for tests: prove that style geometry prints without supports."""

from __future__ import annotations

import numpy as np
import trimesh

from cadlib.checks import OVERHANG_DEG, orient_for_print

HORIZONTAL_TOL_DEG = 2.0  # a down-facing patch this close to -z counts as horizontal (a bridge candidate)
RAY_START_OFFSET_MM = 1e-3
THIN_PERCENTILE = 1.0  # sharp corners must not count as thin walls
MAX_STEEP_AREA_MM2 = 1.0
MIN_WALL_SLACK = 0.95


def steep_overhang_area(mesh: trimesh.Trimesh, print_down, max_bridge_mm: float, bed_band_mm: float = 1.0) -> float:
    """Area (mm²) of faces steeper than OVERHANG_DEG that would need supports, in the print orientation.

    Exempt: faces within bed_band_mm of the bed (chamfers) and horizontal down-facing patches
    whose shorter side is at most max_bridge_mm (short bridges).
    """
    m = orient_for_print(mesh, print_down)
    z_min = float(m.bounds[0][2])
    steep = m.face_normals[:, 2] < -np.sin(np.radians(OVERHANG_DEG))
    near_bed = np.all(m.triangles[:, :, 2] < z_min + bed_band_mm, axis=1)
    counted = steep & ~near_bed

    horizontal = m.face_normals[:, 2] < -np.cos(np.radians(HORIZONTAL_TOL_DEG))
    in_facet = np.zeros(len(m.faces), bool)
    patches = []
    for facet in m.facets:
        in_facet[facet] = True
        patches.append(np.asarray(facet))
    patches.extend(np.array([i]) for i in np.flatnonzero(~in_facet))
    for patch in patches:
        if not (horizontal[patch].all() and counted[patch].any()):
            continue
        pts = m.vertices[np.unique(m.faces[patch])][:, :2]
        if _short_side(pts) <= max_bridge_mm:
            counted[patch] = False
    return float(m.area_faces[counted].sum())


def _short_side(points_xy: np.ndarray) -> float:
    try:
        _, extents = trimesh.bounds.oriented_bounds_2D(points_xy)
    except Exception:  # a degenerate (collinear) patch has no area to bridge
        return 0.0
    return float(min(extents))


def thinnest_wall(mesh: trimesh.Trimesh, samples: int = 4000, seed: int = 0) -> float:
    """Wall thickness (mm) at the 1st percentile of surface samples, measured by rays cast inward."""
    points, face_idx = trimesh.sample.sample_surface(mesh, samples, seed=seed)
    normals = mesh.face_normals[face_idx]
    origins = points - normals * RAY_START_OFFSET_MM
    locations, ray_idx, _ = mesh.ray.intersects_location(origins, -normals, multiple_hits=False)
    if not len(ray_idx):
        return float("inf")
    thickness = np.linalg.norm(locations - origins[ray_idx], axis=1)
    return float(np.percentile(thickness, THIN_PERCENTILE))


def assert_printable(mesh: trimesh.Trimesh, print_down, p) -> None:
    area = steep_overhang_area(mesh, print_down, p.max_bridge_mm)
    assert area <= MAX_STEEP_AREA_MM2, f"unsupported overhang area {area:.1f} mm²"
    wall = thinnest_wall(mesh)
    assert wall >= MIN_WALL_SLACK * p.min_wall_mm, f"thinnest wall {wall:.2f} mm < {MIN_WALL_SLACK} × {p.min_wall_mm} mm"
