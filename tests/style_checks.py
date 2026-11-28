"""Strict printability helpers for tests: prove that style geometry prints without supports."""

from __future__ import annotations

import numpy as np
import trimesh

from cadlib.checks import OVERHANG_DEG, orient_for_print

HORIZONTAL_TOL_DEG = 2.0  # a down-facing patch this close to -z counts as horizontal (a bridge candidate)
RAY_START_OFFSET_MM = 1e-3
OPPOSITE_DOT = -0.8  # a wall is measured only between faces this close to antiparallel (not at corners)
AREA_PER_SAMPLE_MM2 = 0.25  # wall-thickness sampling density: 1 mm² is about four samples
MIN_SAMPLES, MAX_SAMPLES = 4000, 200_000
RAY_CHUNK = 20_000
MAX_THIN_AREA_MM2 = 1.0  # walls thinner than MIN_WALL_SLACK x min_wall may cover at most this much surface
MAX_STEEP_AREA_MM2 = 1.0
MIN_WALL_SLACK = 0.95
ANCHOR_PROBE_MM = 0.3  # how far beyond a bridge's ends (and below it) material is looked for
ANCHOR_SHARE = 0.6  # share of the probes along an end that must hit material for that end to count as anchored


def steep_overhang_area(mesh: trimesh.Trimesh, print_down, max_bridge_mm: float, bed_band_mm: float = 1.0) -> float:
    """Area (mm²) of faces steeper than OVERHANG_DEG that would need supports, in the print orientation.

    Exempt: faces within bed_band_mm of the bed (chamfers) and horizontal down-facing patches
    anchored at both ends along one of their principal directions, with that span at most
    max_bridge_mm (real bridges). A patch held on one side only is a cantilever ledge and counts.
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
        verts = m.vertices[np.unique(m.faces[patch])]
        if _bridged(m, verts, max_bridge_mm):
            counted[patch] = False
    return float(m.area_faces[counted].sum())


def _bridged(m: trimesh.Trimesh, verts: np.ndarray, max_bridge_mm: float) -> bool:
    """True when the patch is a real bridge: anchored at both ends along one of its principal
    directions, with that span at most max_bridge_mm. A degenerate patch is not a bridge."""
    try:
        to_box, extents = trimesh.bounds.oriented_bounds_2D(verts[:, :2])
    except Exception:  # degenerate (collinear) patch: counted, not excused
        return False
    from_box = np.linalg.inv(to_box)
    z = float(verts[:, 2].mean()) - ANCHOR_PROBE_MM
    for k in (0, 1):
        if extents[k] > max_bridge_mm:
            continue
        along = np.linspace(-0.4, 0.4, 5) * extents[1 - k]
        held = True
        for side in (-1.0, 1.0):
            box = np.zeros((len(along), 2))
            box[:, k] = side * (extents[k] / 2 + ANCHOR_PROBE_MM)
            box[:, 1 - k] = along
            xy = (np.column_stack([box, np.ones(len(box))]) @ from_box.T)[:, :2]
            probes = np.column_stack([xy, np.full(len(xy), z)])
            if m.contains(probes).mean() < ANCHOR_SHARE:
                held = False
                break
        if held:
            return True
    return False


def _wall_samples(mesh: trimesh.Trimesh, reach_mm: float, samples: int | None, seed: int) -> tuple[np.ndarray, int]:
    """Wall thickness (mm) at random surface samples, measured by rays cast inward, and the sample count.

    A sample counts only where its ray leaves through a face nearly antiparallel to the sample's own
    face (dot of the normals < OPPOSITE_DOT): two opposite walls. A ray that runs out at a corner
    or across a fillet meets a side face and is not a wall thickness, so it is left out (inf), as is
    a wall thicker than reach_mm. Rays only look reach_mm deep, which keeps 100 000 of them cheap.
    """
    if samples is None:
        samples = int(np.clip(mesh.area / AREA_PER_SAMPLE_MM2, MIN_SAMPLES, MAX_SAMPLES))
    points, face_idx = trimesh.sample.sample_surface(mesh, samples, seed=seed)
    normals = mesh.face_normals[face_idx]
    origins = points - normals * RAY_START_OFFSET_MM
    near_t, near_face = np.full(samples, np.inf), np.full(samples, -1)
    for s in range(0, samples, RAY_CHUNK):
        sl = slice(s, s + RAY_CHUNK)
        t, face, ray = _first_hits(mesh, origins[sl], -normals[sl], reach_mm)
        # The nearest hit of each ray: written in order of falling distance, so the nearest is written last.
        order = np.argsort(-t)
        near_t[s + ray[order]], near_face[s + ray[order]] = t[order], face[order]
    has = near_face >= 0
    opposite = np.zeros(samples, dtype=bool)
    opposite[has] = (mesh.face_normals[near_face[has]] * normals[has]).sum(axis=1) < OPPOSITE_DOT
    return np.where(opposite, near_t + RAY_START_OFFSET_MM, np.inf), samples


def _first_hits(mesh: trimesh.Trimesh, origins: np.ndarray, dirs: np.ndarray, reach_mm: float):
    """Every hit (distance, triangle, ray index) of the rays within reach_mm (Moller-Trumbore on the
    triangles whose boxes meet each ray's short segment)."""
    ends = origins + dirs * reach_mm
    ids, counts = mesh.triangles_tree.intersection_v(np.minimum(origins, ends) - 1e-6, np.maximum(origins, ends) + 1e-6)
    ray = np.repeat(np.arange(len(origins)), counts.astype(np.int64))
    ids = ids.astype(np.int64)
    tri = mesh.triangles[ids]
    d, o = dirs[ray], origins[ray]
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    pvec = np.cross(d, e2)
    det = (e1 * pvec).sum(axis=1)
    inv = 1.0 / np.where(np.abs(det) < 1e-12, np.inf, det)
    tvec = o - tri[:, 0]
    u = (tvec * pvec).sum(axis=1) * inv
    qvec = np.cross(tvec, e1)
    v = (d * qvec).sum(axis=1) * inv
    t = (e2 * qvec).sum(axis=1) * inv
    hit = (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-9) & (t <= reach_mm)
    return t[hit], ids[hit], ray[hit]


def thin_wall_area(mesh: trimesh.Trimesh, limit_mm: float, samples: int | None = None, seed: int = 0) -> float:
    """Estimated surface area (mm²) whose wall, between two opposite faces, is thinner than limit_mm.

    Each surface sample stands for mesh.area / samples of the surface (about AREA_PER_SAMPLE_MM2
    by default), so the result is the share of thin samples times the mesh's area.
    """
    thickness, n = _wall_samples(mesh, limit_mm, samples, seed)
    return float((thickness < limit_mm).sum() / n * mesh.area)


def thinnest_wall(mesh: trimesh.Trimesh, reach_mm: float = 5.0, samples: int | None = None, seed: int = 0) -> float:
    """The thinnest wall (mm) between two opposite faces among the surface samples, inf when none is
    thinner than reach_mm (for reports)."""
    thickness, _ = _wall_samples(mesh, reach_mm, samples, seed)
    return float(thickness.min())


def assert_printable(mesh: trimesh.Trimesh, print_down, p) -> None:
    area = steep_overhang_area(mesh, print_down, p.max_bridge_mm)
    assert area <= MAX_STEEP_AREA_MM2, f"unsupported overhang area {area:.1f} mm²"
    limit = MIN_WALL_SLACK * p.min_wall_mm
    thin = thin_wall_area(mesh, limit)
    assert thin <= MAX_THIN_AREA_MM2, (
        f"{thin:.1f} mm² of walls thinner than {limit:.2f} mm (thinnest {thinnest_wall(mesh):.2f} mm)"
    )
