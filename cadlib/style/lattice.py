"""Graded hex/tri/organic lattice cutters in 2D: the holes a panel is perforated with.

hex and tri: the pitch is fixed and the bars vary, so every hole is a scaled copy of its cell.
organic: irregular Voronoi cells round seeds spread by a deterministic Poisson-disk-like sampling
whose spacing follows the field; each cell is shrunk by half its bar and its corners are rounded,
so the holes are convex pebbles and the bars read as tendons that thicken where they meet.
Containment is decided on polylines with numpy, so a 200 x 140 mm panel needs no per-cell boolean.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Literal

import numpy as np
from build123d import Compound, Face, Plane, Vector, Wire
from scipy.spatial import ConvexHull, Voronoi

from cadlib.style.log import note

LatticeKind = Literal["hex", "tri", "organic"]
Field = Callable[[float, float], float]

_SQRT3 = math.sqrt(3.0)
_EDGE_STEP_MM = 0.25  # sampling step on curved edges: chord sag stays below 0.001 mm for r >= 8
_EPS = 1e-9
_CHUNK = 128
ORGANIC_SPREAD = 2.5  # organic: seed spacing runs from `cell` (field 1) to this many cells (field 0)
ORGANIC_ROUND = 0.7  # organic: corner radius / the shrunk cell's inner radius
ORGANIC_TRIES = 20  # organic: random seed candidates per cell² of the region
ORGANIC_EDGE = 0.4  # organic: seeds keep this share of their spacing from the region's edge
ORGANIC_ROOF_DEG = 46.0  # organic upright roofs: a degree steeper than 45, clear of rounding noise


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
    seed: int = 0,
) -> LatticeCut:
    """Hex, triangle or organic cutters filling `region`, in the region's own plane (u, v = its x_dir, y_dir).

    `cell` is the across-flats pitch (hex) or the side (tri), default 4 x p.min_wall_mm. The bar
    between neighbours is bar_min + (bar_max - bar_min) * field(centre), field in 0..1 (0 = thinnest).
    A cell is kept only when its hole lies inside the region shrunk by bar_min and clear of every
    keep-out grown by bar_min. `up` is print "up" in (u, v): hexes then stand flat-top and the
    top edges of their holes (down-pointing triangles for tri) must not exceed p.max_bridge_mm.

    organic: seeds are spread `cell` apart where field is 1 and ORGANIC_SPREAD x `cell` where it is 0,
    from a random generator started at `seed` (the same seed gives the same lattice). With `up` every
    hole gets a 45 degree peak instead of a roof, so it needs no bridge at all.
    """
    if kind not in ("hex", "tri", "organic"):
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
    if kind == "organic":
        if cell - bar_max <= 0:
            raise ValueError(f"bar_max {bar_max} mm leaves no hole in a {cell} mm cell")
        return _organic(region, p, cell, bar_min, bar_max, field, keepout, up, seed)
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

    return _finish(holes, centres, region, plane, keepout, bar_min, 0)


def _finish(holes, centres, region, plane, keepout, bar_min, dropped_before: int, outlines=None) -> LatticeCut:
    """Keep the holes clear of the region's edge and the keep-outs, note what was dropped, make the faces.

    `holes` (N, k, 2) is what the checks see; `outlines` (when given) are the same holes with their own
    point counts, used for the faces so padding never adds edges to the solid.
    """
    ra, rb = _segments(region, plane)
    org = np.array(tuple(plane.origin))
    xd, yd = np.array(tuple(plane.x_dir)), np.array(tuple(plane.y_dir))
    ok = _clear(holes, ra, rb, bar_min)
    for ko in keepout:
        ka, kb = _segments(ko, plane)
        ok &= _clear(holes, ka, kb, bar_min) & ~_inside(centres, ka, kb)
    kept, dropped = int(ok.sum()), int((~ok).sum()) + dropped_before
    if kept == 0:
        note("lattice", "panel too small for one cell: left solid")
        return LatticeCut(None, 0, dropped)
    if dropped:
        note("lattice", f"{dropped} cells dropped at edges and keep-outs", level="info")

    out = []
    polys = holes[ok] if outlines is None else [o for o, keep in zip(outlines, ok) if keep]
    for poly in polys:
        pts = [Vector(*(org + u * xd + v * yd)) for u, v in poly]
        out.append(Face(Wire.make_polygon(pts, close=True)))
    return LatticeCut(Compound(out), kept, dropped)


# --- organic ---------------------------------------------------------------------------------------


def _clip_halfplane(poly: np.ndarray, a: np.ndarray, n: np.ndarray, d: float) -> np.ndarray:
    """The part of a convex polygon where n . (x - a) >= d (one Sutherland-Hodgman pass)."""
    if len(poly) == 0:
        return poly
    s = (poly - a) @ n - d
    out = []
    for i in range(len(poly)):
        j = (i + 1) % len(poly)
        if s[i] >= 0:
            out.append(poly[i])
        if (s[i] >= 0) != (s[j] >= 0):
            t = s[i] / (s[i] - s[j])
            out.append(poly[i] + t * (poly[j] - poly[i]))
    return np.array(out) if len(out) >= 3 else np.zeros((0, 2))


def _ccw(poly: np.ndarray) -> np.ndarray:
    area = np.sum(poly[:, 0] * np.roll(poly[:, 1], -1) - np.roll(poly[:, 0], -1) * poly[:, 1])
    return poly if area > 0 else poly[::-1]


def _shrink(poly: np.ndarray, d: float) -> np.ndarray:
    """A convex ccw polygon moved in by d on every edge (edges that vanish simply drop out)."""
    out = poly
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        e = b - a
        length = float(np.hypot(*e))
        if length < _EPS:
            continue
        out = _clip_halfplane(out, a, np.array([-e[1], e[0]]) / length, d)
        if len(out) == 0:
            break
    return out


def _clip_convex(poly: np.ndarray, clip: np.ndarray) -> np.ndarray:
    """The part of a convex polygon inside a convex ccw clip polygon."""
    out = poly
    for i in range(len(clip)):
        a, b = clip[i], clip[(i + 1) % len(clip)]
        e = b - a
        out = _clip_halfplane(out, a, np.array([-e[1], e[0]]) / max(float(np.hypot(*e)), _EPS), 0.0)
        if len(out) == 0:
            break
    return out


def _inner_radius(poly: np.ndarray) -> float:
    """Distance from the polygon's area centroid to its nearest edge (a vertex mean would lean
    towards a densely sampled curved side)."""
    x, y = poly[:, 0], poly[:, 1]
    xn, yn = np.roll(x, -1), np.roll(y, -1)
    cross = x * yn - xn * y
    area = cross.sum() / 2
    if abs(area) < _EPS:
        return 0.0
    c = np.array([((x + xn) * cross).sum(), ((y + yn) * cross).sum()]) / (6 * area)
    return float(_point_seg_dist(c[None], poly, np.roll(poly, -1, axis=0)).min())


def _pebble(poly: np.ndarray, r: float) -> np.ndarray:
    """A convex ccw polygon grown by r with round corners (its Minkowski sum with a disc)."""
    pts = []
    n = len(poly)
    for i in range(n):
        prev, cur, nxt = poly[i - 1], poly[i], poly[(i + 1) % n]
        a0 = math.atan2(-(cur - prev)[0], (cur - prev)[1])  # outward normal of the incoming edge
        a1 = math.atan2(-(nxt - cur)[0], (nxt - cur)[1])
        if a1 < a0:
            a1 += 2 * math.pi
        steps = max(1, math.ceil((a1 - a0) / math.radians(15)))
        for k in range(steps + 1):
            a = a0 + (a1 - a0) * k / steps
            pts.append(cur + r * np.array([math.cos(a), math.sin(a)]))
    return np.array(pts)


def _tent(hole: np.ndarray, up: np.ndarray) -> np.ndarray:
    """The hole cut down under a 46 degree tent through its highest point, so its roof needs no support.

    Unlike outline.clip_roof this never grows the hole, so the bars to its neighbours keep their width.
    """
    up = up / np.linalg.norm(up)
    side = np.array([up[1], -up[0]])
    apex = hole[np.argmax(hole @ up)]
    t = math.tan(math.radians(ORGANIC_ROOF_DEG))
    out = hole
    for sign in (1.0, -1.0):
        n = -(up + sign * t * side)  # keeps v <= -t |s|: walls 46 degrees above horizontal
        out = _clip_halfplane(out, apex, n / np.linalg.norm(n), 0.0)
    return _ccw(out) if len(out) >= 3 else out


def _pad(poly: np.ndarray, k: int) -> np.ndarray:
    """The outline with k points: its longest edges split in half until there are k. Every corner stays."""
    pts = [q for q in poly]
    while len(pts) < k:
        seg = [np.hypot(*(pts[(i + 1) % len(pts)] - pts[i])) for i in range(len(pts))]
        i = int(np.argmax(seg))
        pts.insert(i + 1, (pts[i] + pts[(i + 1) % len(pts)]) / 2)
    return np.array(pts)


def _seeds(lo, hi, ra, rb, spacing, cell: float, rng) -> np.ndarray:
    """Dart throwing: candidates in random order, kept when no kept seed lies closer than their mean spacing."""
    area = float(np.prod(hi - lo))
    cand = lo + rng.random((max(64, int(ORGANIC_TRIES * area / cell**2)), 2)) * (hi - lo)
    cand = cand[_inside(cand, ra, rb)]
    space = np.array([spacing(u, v) for u, v in cand])
    # A seed hugging the edge would leave a sliver cell too thin to hold a hole: keep seeds a
    # share of their spacing inside, so the edge cells reach the rim instead.
    if len(cand):
        inner = _point_seg_dist(cand, ra, rb).min(axis=1) >= ORGANIC_EDGE * space
        cand, space = cand[inner], space[inner]
    kept: list[int] = []
    for i in range(len(cand)):
        if kept:
            k = np.array(kept)
            if (np.hypot(*(cand[k] - cand[i]).T) < (space[k] + space[i]) / 2).any():
                continue
        kept.append(i)
    return cand[kept]


def _organic(region, p, cell, bar_min, bar_max, field, keepout, up, seed) -> LatticeCut:
    plane = Plane(region.faces()[0])
    ra, rb = _segments(region, plane)
    pts = np.concatenate([ra, rb])
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    fld = field if field is not None else (lambda u, v: 0.0)

    def f(u: float, v: float) -> float:
        return min(1.0, max(0.0, float(fld(u, v))))

    def spacing(u: float, v: float) -> float:
        return cell * (1.0 + (ORGANIC_SPREAD - 1.0) * (1.0 - f(u, v)))

    seeds = _seeds(lo, hi, ra, rb, spacing, cell, np.random.default_rng(seed))
    if len(seeds) == 0:
        note("lattice", "panel too small for one cell: left solid")
        return LatticeCut(None, 0, 0)
    # Far ghost seeds close every Voronoi region round the real ones.
    span = float(np.linalg.norm(hi - lo)) * 3 + cell
    angles = np.linspace(0, 2 * np.pi, 16, endpoint=False)
    ring = (lo + hi) / 2 + span * np.column_stack([np.cos(angles), np.sin(angles)])
    vor = Voronoi(np.vstack([seeds, ring]))
    hull_in = _shrink(_ccw(pts[ConvexHull(pts).vertices]), bar_min / 2)

    holes, centres, dropped = [], [], 0
    for i, s in enumerate(seeds):
        ids = vor.regions[vor.point_region[i]]
        if not ids or -1 in ids:
            dropped += 1
            continue
        clipped = _clip_convex(_ccw(vor.vertices[ids]), hull_in)
        bar = bar_min + (bar_max - bar_min) * f(*s)
        core = _shrink(clipped, bar / 2) if len(clipped) else clipped
        if len(core) < 3 or _inner_radius(core) < p.min_wall_mm:
            dropped += 1
            continue
        r = ORGANIC_ROUND * _inner_radius(core)
        inner = _shrink(core, r)
        if len(inner) < 3:
            dropped += 1
            continue
        hole = _pebble(_ccw(inner), r)
        if up is not None:
            hole = _tent(hole, np.array(up, dtype=float))
            if len(hole) < 3:
                dropped += 1
                continue
        holes.append(_ccw(hole))
        centres.append(s)
    if not holes:
        note("lattice", "panel too small for one cell: left solid")
        return LatticeCut(None, 0, dropped)
    k = max(len(h) for h in holes)
    padded = np.array([_pad(h, k) for h in holes])
    return _finish(padded, np.array(centres), region, plane, keepout, bar_min, dropped, outlines=holes)
