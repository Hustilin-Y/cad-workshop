"""Graded hex/tri lattice cutters in 2D: the holes a panel is perforated with.

The pitch is fixed and the bars vary, so every hole is a scaled copy of its cell. Containment
is decided on polylines with numpy, so a 200 x 140 mm panel needs no per-cell boolean.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Literal

import numpy as np
from build123d import Compound, Face, Plane, Vector, Wire

from cadlib.style.log import note

LatticeKind = Literal["hex", "tri"]
Field = Callable[[float, float], float]

_SQRT3 = math.sqrt(3.0)
_EDGE_STEP_MM = 0.25  # sampling step on curved edges: chord sag stays below 0.001 mm for r >= 8
_EPS = 1e-9
_CHUNK = 128


@dataclass(frozen=True)
class LatticeCut:
    """The cutter (None when no cell fits) and how many cells were kept and dropped."""

    tool: Compound | None
    kept: int
    dropped: int


def _segments(shape, plane: Plane) -> tuple[np.ndarray, np.ndarray]:
    """Boundary of every face of `shape` as a soup of segments (A, B) in the plane's (u, v)."""
    org = np.array(tuple(plane.origin))
    xd, yd = np.array(tuple(plane.x_dir)), np.array(tuple(plane.y_dir))
    a_all, b_all = [], []
    for face in shape.faces():
        for wire in [face.outer_wire(), *face.inner_wires()]:
            for edge in wire.edges():
                n = 1 if edge.geom_type.name == "LINE" else max(8, math.ceil(edge.length / _EDGE_STEP_MM))
                pts = np.array([tuple(edge.position_at(i / n)) for i in range(n + 1)]) - org
                uv = np.stack([pts @ xd, pts @ yd], axis=1)
                a_all.append(uv[:-1])
                b_all.append(uv[1:])
    return np.concatenate(a_all), np.concatenate(b_all)


def _inside(points: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Even-odd point-in-polygon of (M, 2) points against a segment soup."""
    # The ray is nudged off exact vertex heights (and off the float seam of a closed curve).
    px, py = points[:, 0:1], points[:, 1:2] + 1.2345e-7
    ay, by = a[None, :, 1], b[None, :, 1]
    dy = np.where(by == ay, 1.0, by - ay)
    xcross = a[None, :, 0] + (py - ay) * (b[None, :, 0] - a[None, :, 0]) / dy
    hit = ((ay > py) != (by > py)) & (px < xcross)
    return hit.sum(axis=1) % 2 == 1


def _point_seg_dist(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Distances (M, S) from points p (M, 2) to segments a-b (S, 2)."""
    ab = b - a
    l2 = np.maximum((ab * ab).sum(axis=1), _EPS)
    t = np.clip(((p[:, None, :] - a[None]) * ab[None]).sum(axis=2) / l2[None], 0.0, 1.0)
    proj = a[None] + t[..., None] * ab[None]
    return np.linalg.norm(p[:, None, :] - proj, axis=2)


def _cross(o: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a[..., 0] - o[..., 0]) * (b[..., 1] - o[..., 1]) - (a[..., 1] - o[..., 1]) * (b[..., 0] - o[..., 0])


def _clear(holes: np.ndarray, a: np.ndarray, b: np.ndarray, gap: float) -> np.ndarray:
    """Per convex ccw hole (N, k, 2): at least `gap` from every segment, no crossing, nothing inside."""
    n, k, _ = holes.shape
    out = np.ones(n, dtype=bool)
    verts = np.concatenate([a, b])
    for s in range(0, n, _CHUNK):
        h = holes[s : s + _CHUNK]
        m = len(h)
        e0, e1 = h.reshape(-1, 2), np.roll(h, -1, axis=1).reshape(-1, 2)
        ok = _point_seg_dist(e0, a, b).reshape(m, -1).min(axis=1) >= gap - _EPS
        ok &= _point_seg_dist(verts, e0, e1).reshape(len(verts), m, k).min(axis=(0, 2)) >= gap - _EPS
        # Proper crossings between hole edges and the segment soup.
        d1 = _cross(e0[:, None], e1[:, None], a[None])
        d2 = _cross(e0[:, None], e1[:, None], b[None])
        d3 = _cross(a[None], b[None], e0[:, None])
        d4 = _cross(a[None], b[None], e1[:, None])
        crossing = ((d1 > 0) != (d2 > 0)) & ((d3 > 0) != (d4 > 0))
        ok &= ~crossing.reshape(m, -1).any(axis=1)
        # A segment vertex strictly inside the (convex, ccw) hole.
        inside = np.ones((len(verts), m), dtype=bool)
        for j in range(k):
            inside &= _cross(h[None, :, j], h[None, :, (j + 1) % k], verts[:, None]) > 0
        ok &= ~inside.any(axis=0)
        out[s : s + _CHUNK] = ok
    return out


def _cells(kind: LatticeKind, cell: float, centre: np.ndarray, radius: float, rot_deg: float, flat: bool):
    """Cell centres in (u, v) around `centre`, a per-cell type (0 hex or up-triangle, 1 down-triangle) and the rotation."""
    n = math.ceil(radius / (cell * _SQRT3 / 2)) + 2
    idx = np.arange(-n, n + 1)
    ii, jj = np.meshgrid(idx, idx)
    ii, jj = ii.ravel().astype(float), jj.ravel().astype(float)
    if kind == "hex":
        if flat:
            a1, a2 = cell * np.array([_SQRT3 / 2, 0.5]), cell * np.array([0.0, 1.0])
        else:
            a1, a2 = cell * np.array([1.0, 0.0]), cell * np.array([0.5, _SQRT3 / 2])
        local = ii[:, None] * a1 + jj[:, None] * a2
        kinds = np.zeros(len(local), dtype=int)
    else:
        h = cell * _SQRT3 / 2
        up = np.stack([(ii + jj / 2 + 0.5) * cell, jj * h + h / 3], axis=1)
        down = np.stack([(ii + jj / 2 + 1.0) * cell, jj * h + 2 * h / 3], axis=1)
        local = np.concatenate([up, down])
        kinds = np.concatenate([np.zeros(len(up), dtype=int), np.ones(len(down), dtype=int)])
    c, s = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
    rot = np.array([[c, -s], [s, c]])
    return local @ rot.T + centre, kinds, rot


def lattice(
    region: Face,
    p,
    *,
    kind: LatticeKind = "hex",
    cell: float | None = None,
    bar_min: float | None = None,
    bar_max: float | None = None,
    field: Field | None = None,
    keepout: list[Face] = (),
    up: tuple[float, float] | None = None,
) -> LatticeCut:
    """Hex or triangle cutters filling `region`, in the region's own plane (u, v = its x_dir, y_dir).

    `cell` is the across-flats pitch (hex) or the side (tri), default 4 x p.min_wall_mm. The bar
    between neighbours is bar_min + (bar_max - bar_min) * field(centre), field in 0..1 (0 = thinnest).
    A cell is kept only when its hole lies inside the region shrunk by bar_min and clear of every
    keep-out grown by bar_min. `up` is print "up" in (u, v): hexes then stand flat-top and the
    top edges of their holes (down-pointing triangles for tri) must not exceed p.max_bridge_mm.
    """
    if kind not in ("hex", "tri"):
        raise ValueError(f"unknown lattice kind {kind!r}")
    min_cell = 4 * p.min_wall_mm
    cell = min_cell if cell is None else cell
    bar_min = p.min_wall_mm if bar_min is None else bar_min
    bar_max = bar_min if bar_max is None else bar_max
    if cell < min_cell - _EPS:
        raise ValueError(f"cell {cell} mm is below the floor 4 x min_wall_mm = {min_cell:g} mm")
    if bar_min < p.min_wall_mm - _EPS:
        raise ValueError(f"bar_min {bar_min} mm is below min_wall_mm = {p.min_wall_mm:g} mm")
    if bar_max < bar_min - _EPS:
        raise ValueError(f"bar_max {bar_max} mm is below bar_min = {bar_min:g} mm")
    # Hole size (across flats for hex, side for tri) is cell minus the bar scaled to the shape.
    shrink = 1.0 if kind == "hex" else _SQRT3
    if cell - shrink * bar_max <= 0:
        raise ValueError(f"bar_max {bar_max} mm leaves no hole in a {cell} mm cell")
    flat = kind == "hex" and up is not None
    if up is not None:
        top = (cell - shrink * bar_min) / (_SQRT3 if kind == "hex" else 1.0)
        if top > p.max_bridge_mm + _EPS:
            raise ValueError(f"hole top edge {top:.2f} mm exceeds max_bridge_mm = {p.max_bridge_mm:g} mm")

    faces = region.faces()
    plane = Plane(faces[0])
    org = np.array(tuple(plane.origin))
    xd, yd = np.array(tuple(plane.x_dir)), np.array(tuple(plane.y_dir))
    ra, rb = _segments(region, plane)
    lo, hi = np.minimum(ra.min(axis=0), rb.min(axis=0)), np.maximum(ra.max(axis=0), rb.max(axis=0))
    centre = (lo + hi) / 2
    rot_deg = 0.0 if up is None else math.degrees(math.atan2(up[1], up[0])) - 90.0
    centres, kinds, _ = _cells(kind, cell, centre, float(np.linalg.norm(hi - lo)) / 2, rot_deg, flat)

    # Candidates: cell centre inside the region (the rest is the empty margin, not a dropped cell).
    cand = _inside(centres, ra, rb)
    centres, kinds = centres[cand], kinds[cand]
    if len(centres) == 0:
        note("lattice", "panel too small for one cell: left solid")
        return LatticeCut(None, 0, 0)

    fld = field if field is not None else (lambda u, v: 0.0)
    bar = bar_min + (bar_max - bar_min) * np.array([min(1.0, max(0.0, float(fld(u, v)))) for u, v in centres])
    size = cell - shrink * bar  # across flats (hex) or side (tri)
    # Vertex angles, counter-clockwise, in the frame where `up` is +v, then turned into (u, v).
    if kind == "hex":
        base = 0.0 if flat else 90.0
        angs = [np.radians(base + 60 * j) for j in range(6)]
        radius = size / _SQRT3
        ang_tab = np.tile(np.array(angs), (len(centres), 1))
    else:
        ang_tab = np.where(
            kinds[:, None] == 0,
            np.radians([90.0, 210.0, 330.0])[None],
            np.radians([270.0, 30.0, 150.0])[None],
        )
        radius = size / _SQRT3
    ang_tab = ang_tab + math.radians(rot_deg)
    holes = centres[:, None, :] + radius[:, None, None] * np.stack([np.cos(ang_tab), np.sin(ang_tab)], axis=-1)

    ok = _clear(holes, ra, rb, bar_min)
    for ko in keepout:
        ka, kb = _segments(ko, plane)
        ok &= _clear(holes, ka, kb, bar_min) & ~_inside(centres, ka, kb)
    kept, dropped = int(ok.sum()), int((~ok).sum())
    if kept == 0:
        note("lattice", "panel too small for one cell: left solid")
        return LatticeCut(None, 0, dropped)
    if dropped:
        note("lattice", f"{dropped} cells dropped at edges and keep-outs", level="info")

    out = []
    for poly in holes[ok]:
        pts = [Vector(*(org + u * xd + v * yd)) for u, v in poly]
        out.append(Face(Wire.make_polygon(pts, close=True)))
    return LatticeCut(Compound(out), kept, dropped)
