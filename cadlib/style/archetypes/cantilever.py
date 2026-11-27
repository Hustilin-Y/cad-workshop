"""Cantilever bracket: a wall plate, an arm and bracing, drawn as an elevation and extruded to depth.

Frame: the plate occupies -plate_t <= x <= 0 (its back, x = -plate_t, lies against the wall), the arm
runs along +X at the top, z from 0 to `height`, the depth runs along Y centred on y = 0. The
elevation lives in Plane.XZ (u = X, v = Z), so every opening and lattice cell is a through-cut along Y.

The screws go through the plate along X. Their heads sit on the plate's front face inside a "bay",
an opening that leaves the plate's face bare around them, so each head can be reached from the front.

Print orientations: "-y" (default) lies the elevation on the bed, every cut is vertical and the load
acts in the layer plane. "-x" stands the bracket on its wall plate: openings then turn their point to
+X with a 45 degree cap, and a void between members is filled under its roof down to a 45 degree tent.

Rules of thumb (part 1 has no load calculation): the arm tapers by the dialect's ratio, the bracing
meets the arm at 0.8-0.9 of the reach, bars around openings are max(3 x min_wall, root_t / 2).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
from build123d import Compound, Edge, Face, Plane, Pos, Rot, Solid, Vector, Wire, extrude, fillet

from cadlib import fasteners
from cadlib.config import Profile
from cadlib.style.archetypes.types import Archetype, Load, Support, Tunable
from cadlib.style.dialects import Dialect, edge_size, finish_extrusion, get_dialect
from cadlib.style.lattice import _inside, _point_seg_dist, _segments, lattice
from cadlib.style.log import note
from cadlib.style.members import catenary, curved_beam, rib, truss
from cadlib.style.outline import Point, arch, clip_roof, to_face
from cadlib.style.plane import in_plane_up

ALLOWED_PRINT_DOWN = ("-y", "-x")

# Archetype ratios (dimensionless, see the module docstring).
GAUDI_BRACE_AT = 0.8       # the catenary brace meets the arm at this share of the reach
GAUDI_BRACE_ROOT = 1.6     # brace width at the plate / root_t
GAUDI_SAG = 0.1            # brace sag / chord length
GAUDI_DROOP = 0.08         # the arm's tip droops by this share of the reach
HITECH_NODES_AT = (0.5, 0.9)
HITECH_BAR = 0.3           # truss bar / root_t (floored at 2 x min_wall)
HITECH_NODE = 2.5          # node disc diameter / bar
HITECH_TRI_CELL = 6.0      # plate lattice triangle side / min_wall
WEB_TO = 0.9               # gothic and parametric webs meet the arm at this share of the reach
PARAM_SAG = 0.08           # parametric lower chord sag / chord length
PARAM_HEX_CELL = 6.0       # hex pitch / min_wall
PARAM_BAR_MAX = 3.0        # thickest hex bar / min_wall
RIB_HEIGHT_LAYERS = 6
THIN_EDGE = 0.45           # an edge finish is at most this share of the thinnest member
BAY_SPAN = 0.18            # bay width (across the plate face's normal) / reach, upright layout
TRACERY_MAX = 3            # gothic: arches beside the bay
TRACERY_STEP = 0.8         # each arch at most this share of the one before
TRACERY_MIN = 5.0          # smallest arch span / min_wall
GOTHIC_COVE = 0.06         # the web's underside bulges this share of its chord towards the corner

_SQRT3 = math.sqrt(3.0)
_ROOF_DEG = 46.0  # roofs are clipped a degree steeper than the 45 degree limit, clear of rounding noise
_SMOOTH_DEG = 12.0  # a sampled curve turns less than this per point; a corner turns more
_XZ = Plane.XZ


@dataclass(frozen=True)
class CantileverSpec:
    reach: float           # arm length from the plate's front face to the tip, mm
    height: float          # plate height, the arm's top is at z = height, mm
    depth: float           # extrusion depth along Y, mm
    root_t: float          # arm thickness at the plate, mm
    plate_t: float         # wall plate thickness, mm
    screw: str = "M4"
    screw_count: int = 2
    tip_hole: str | None = "M4"
    load_n: float = 20.0   # load hung at the tip hole, N (straight down)


@dataclass(frozen=True)
class _Frame:
    """Sizes derived from the spec, the profile and the dialect."""

    spec: CantileverSpec
    p: Profile
    d: Dialect
    up: Point | None       # print "up" in (x, z), None when the elevation lies flat
    tip_t: float
    eye_r: float           # radius of the round eye at the tip, 0 when the arm is thick enough itself
    arm_end: float         # x where the arm's straight part ends (the eye's centre when there is one)
    tip_at: Point          # tip hole centre (or the tip's middle)
    keep_r: float          # keep-out radius around a screw
    margin: float          # bar left around openings
    edge: float            # dialect edge size used by finish_extrusion

    @property
    def H(self) -> float:
        return self.spec.height

    @property
    def R(self) -> float:
        return self.spec.reach

    @property
    def pt(self) -> float:
        return self.spec.plate_t

    @property
    def t0(self) -> float:
        return self.spec.root_t

    def arm_t(self, x: float) -> float:
        return self.t0 + (self.tip_t - self.t0) * min(max(x / self.arm_end, 0.0), 1.0)


@dataclass
class _Elevation:
    solid: Face                      # the elevation with its inherent voids (members fused)
    openings: list[list[Point]]      # cut-outs in (x, z), already printable for `up`
    thin: float                      # the thinnest member: edge finishes stay below half of it
    web: Face | None = None          # the region bays and lattices fit into
    bay: list[Point] | None = None


def cantilever(style: str, spec: CantileverSpec, p: Profile, print_down: str = "-y") -> Archetype:
    """A cantilever bracket in the given dialect, see the module docstring for the frame."""
    dialect = get_dialect(style)
    if print_down not in ALLOWED_PRINT_DOWN:
        raise ValueError(f"print_down {print_down!r}: the cantilever prints with {' or '.join(ALLOWED_PRINT_DOWN)} down")
    _validate(spec, p)
    g = _frame(spec, p, dialect, print_down)

    elev = {"gothic": _gothic, "gaudi": _gaudi, "hitech": _hitech, "parametric": _parametric}[style](g)
    if g.up is None:
        voids: list[Face] = []
    else:
        voids = [f for w in elev.solid.inner_wires() for f in _printable_void(Face(w), g.up)]
    open_faces = [_poly(pts) for pts in elev.openings]
    screws_z = _place_screws(g, elev, voids)
    keepouts = [_keepout(g, z) for z in screws_z]
    for pts in elev.openings:
        _check_keepouts(pts, screws_z, g.keep_r)

    # Body: in the flat layout the voids and openings are finished with the outline; standing up,
    # their roofs keep a sharp 45 degree apex, so they are cut after the finish.
    edge = min(g.edge, THIN_EDGE * elev.thin)
    if edge < g.edge:
        note("cantilever", f"{style}: edge {g.edge:.1f} mm shrunk to {edge:.1f} mm, thinnest member {elev.thin:.1f} mm", "info")
    if g.up is None:
        face = elev.solid
        for f in open_faces:
            face = face - f
        body = finish_extrusion(_extrude(_round_corners(face, g, edge), spec.depth), dialect, spec.depth, print_down, p, edge)
    else:
        envelope = _round_corners(Face(elev.solid.outer_wire()), g, edge)
        body = finish_extrusion(_extrude(envelope, spec.depth), dialect, spec.depth, print_down, p, edge)
        cuts = voids + open_faces
        if cuts:
            body = _one(body - _extrude(Compound(cuts), spec.depth + 2))

    if style == "parametric":
        body = _parametric_lattice(g, elev, body, keepouts, print_down)
    if style == "hitech":
        body = _plate_lattice(g, body, screws_z, keepouts, print_down)
    for z in screws_z:
        body = _one(body - _screw_tool(g, z, print_down))
    if spec.tip_hole is not None:
        body = _one(body - _tip_tool(g))
    if dialect.relief_ribs and elev.bay is not None:
        body = _one(body + _relief_rib(g, elev.bay))

    return Archetype(
        solid=body,
        print_down=print_down,
        allowed_print_down=ALLOWED_PRINT_DOWN,
        supports=[Support((-spec.plate_t, 0.0, spec.height / 2), (-1.0, 0.0, 0.0))],
        loads=[Load((g.tip_at[0], 0.0, g.tip_at[1]), (0, 0, -spec.load_n))],
        tunables={
            "root_t": Tunable("root_t", spec.root_t, 2 * p.min_wall_mm, spec.height / 3),
            "plate_t": Tunable("plate_t", spec.plate_t, 2 * p.min_wall_mm, 12.0),
            "depth": Tunable("depth", spec.depth, 10.0, 60.0),
        },
    )


# --- sizes --------------------------------------------------------------------------------------


def _validate(spec: CantileverSpec, p: Profile) -> None:
    if spec.plate_t < 2 * p.min_wall_mm:
        raise ValueError(f"plate_t {spec.plate_t:g} mm is below 2 x min_wall = {2 * p.min_wall_mm:g} mm")
    if spec.root_t < 2 * p.min_wall_mm:
        raise ValueError(f"root_t {spec.root_t:g} mm is below 2 x min_wall = {2 * p.min_wall_mm:g} mm")
    if spec.root_t > spec.height / 3:
        raise ValueError(f"root_t {spec.root_t:g} mm is over a third of the height {spec.height:g} mm")
    if spec.depth < 10:
        raise ValueError(f"depth {spec.depth:g} mm is below 10 mm")
    if spec.reach < 2 * spec.root_t or spec.height < 3 * spec.root_t:
        raise ValueError(f"reach {spec.reach:g} x height {spec.height:g} mm is too small for root_t {spec.root_t:g} mm")
    if spec.screw_count < 1:
        raise ValueError("the cantilever needs at least one screw")
    hole = _hole_d(spec.screw, p)
    if spec.depth < hole + 4 * p.min_wall_mm:
        raise ValueError(f"depth {spec.depth:g} mm leaves no wall around a {hole:g} mm screw hole")


def _hole_d(size: str, p: Profile) -> float:
    return fasteners.metric(size).clear_fine + p.hole_clearance_mm


def _frame(spec: CantileverSpec, p: Profile, d: Dialect, print_down: str) -> _Frame:
    up = in_plane_up(_XZ, print_down)
    tip_t = max(spec.root_t * d.taper, 2 * p.min_wall_mm)
    eye_r, arm_end, x_tip = 0.0, spec.reach, spec.reach
    if spec.tip_hole is not None:
        hole = _hole_d(spec.tip_hole, p)
        room = hole / 2 + 2 * p.min_wall_mm  # the hole plus two walls on each side
        if tip_t < 2 * room:
            # A slender arm ends in a round eye that holds the hole; the arm runs into its centre.
            eye_r = room
            arm_end = x_tip = spec.reach - room
        else:
            # Room for the hole's 45 degree cap when the arm stands up.
            x_tip = spec.reach - max(room, hole / 2 * math.sqrt(2) + 2 * p.min_wall_mm)
    g = _Frame(
        spec=spec, p=p, d=d, up=up, tip_t=tip_t, eye_r=eye_r, arm_end=arm_end, tip_at=(0.0, 0.0),
        keep_r=(_hole_d(spec.screw, p) + 4 * p.min_wall_mm) / 2,
        margin=max(3 * p.min_wall_mm, spec.root_t / 2),
        edge=edge_size(d, spec.depth, p),
    )
    if d.name == "gaudi":
        z_tip = _gaudi_arm_centre(g, x_tip)
    elif eye_r:
        z_tip = spec.height - eye_r  # the eye's top runs on tangentially into the arm's flat top
    else:
        z_tip = spec.height - g.arm_t(x_tip) / 2
    return replace(g, tip_at=(x_tip, z_tip))


# --- 2D helpers -----------------------------------------------------------------------------------


def _poly(pts: list[Point]) -> Face:
    """Planar face of an (x, z) outline, wound so its normal is +Y like the members' faces (they fuse).

    Runs of points that turn by less than _SMOOTH_DEG per vertex become one spline, so a sampled
    arch is a few smooth edges an edge finish can follow, not dozens of facets.
    """
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))
    pts = pts if area < 0 else pts[::-1]
    n = len(pts)
    seg = [math.dist(pts[i], pts[(i + 1) % n]) for i in range(n)]
    long = 2.5 * float(np.median(seg))  # a straight run (a jamb) between sampled curves stays a line
    corners = [
        i for i in range(n)
        if _corner(pts[i - 1], pts[i], pts[(i + 1) % n]) > _SMOOTH_DEG or max(seg[i - 1], seg[i]) > long
    ]
    if len(corners) < 2:
        return to_face(pts)
    edges = []
    for a, b in zip(corners, corners[1:] + corners[:1]):
        run = [pts[k % n] for k in range(a, b + (n if b <= a else 0) + 1)]
        vecs = [Vector(u, 0, v) for u, v in run]
        edges.append(Edge.make_line(*vecs) if len(run) == 2 else Edge.make_spline(vecs))
    return Face(Wire(edges))


def _disc(centre: Point, r: float) -> Face:
    # Polygon faces from to_face wind clockwise seen along the plane normal; the disc follows suit.
    return Face(Wire.make_circle(r, Plane(origin=(centre[0], 0, centre[1]), z_dir=(0, 1, 0))))


def _fuse(faces: list[Face]) -> Face:
    fused = faces[0]
    for f in faces[1:]:
        fused = fused + f
    return fused


def _trim(face, g: _Frame) -> Face:
    """Keep the part of `face` inside the bracket's box: nothing behind the wall or below z = 0."""
    box = _poly([(-g.pt, 0), (g.R + 1, 0), (g.R + 1, g.H), (-g.pt, g.H)])
    faces = (face & box).clean().faces()
    if len(faces) != 1:
        raise ValueError(f"the {g.d.name} elevation is not one piece ({len(faces)} pieces)")
    return faces[0]


def _arm(g: _Frame) -> Face:
    x0 = -g.pt / 2
    return _poly([(x0, g.H), (g.arm_end, g.H), (g.arm_end, g.H - g.tip_t), (x0, g.H - g.arm_t(x0))])


def _plate(g: _Frame) -> Face:
    return _poly([(-g.pt, 0), (0, 0), (0, g.H), (-g.pt, g.H)])


def _eye(g: _Frame) -> list[Face]:
    """The round eye at the tip; standing up, its underside comes to a 45 degree point so it prints."""
    if g.eye_r <= 0:
        return []
    if g.up is None:
        return [_disc(g.tip_at, g.eye_r)]
    n = 64
    circle = [(g.eye_r * math.cos(2 * math.pi * k / n), g.eye_r * math.sin(2 * math.pi * k / n)) for k in range(n)]
    down = (-g.up[0], -g.up[1])
    return [_poly(_shift(clip_roof(circle, down, _ROOF_DEG), g.tip_at))]


Segs = tuple[np.ndarray, np.ndarray]


def _pts_of(shape, plane: Plane = _XZ) -> Segs:
    return _segments(shape, plane)


def _fits(pts: np.ndarray, region: Segs, margin: float, skip_plate: bool = True) -> bool:
    """All points inside `region` (its boundary segments) and at least `margin` from that boundary.

    With skip_plate the plate face (x = 0) does not count: a bay may rest on it.
    """
    a, b = region
    probe = pts.copy()
    probe[:, 0] = np.maximum(probe[:, 0], 1e-3)
    if not _inside(probe, a, b).all():
        return False
    if skip_plate:
        keep = (np.abs(a[:, 0]) > 1e-3) | (np.abs(b[:, 0]) > 1e-3)
        a, b = a[keep], b[keep]
    return bool(_point_seg_dist(pts, a, b).min() >= margin)


def _turn(pts: list[Point], up: Point) -> list[Point]:
    """Turn points whose apex is +v so that it points along `up`."""
    ang = math.atan2(up[1], up[0]) - math.pi / 2
    c, s = math.cos(ang), math.sin(ang)
    return [(c * u - s * v, s * u + c * v) for u, v in pts]


def _shift(pts: list[Point], at: Point) -> list[Point]:
    return [(u + at[0], v + at[1]) for u, v in pts]


def _head(kind: str, span: float) -> float:
    return span * _SQRT3 / 2 if kind == "pointed" else 0.6 * span


def _lancet(kind: str, span: float, jamb: float) -> list[Point]:
    """Window outline: base on v = 0 centred on u = 0, vertical jambs, an arched head, apex +v (ccw)."""
    h = span / 2
    return [(h, 0.0)] + [(u, v + jamb) for u, v in arch(kind, span, _head(kind, span), n=32)] + [(-h, 0.0)]


def _place(local: list[Point], up: Point | None, at: Point) -> list[Point]:
    """Local outline (apex +v) placed at `at`: upright when the elevation lies flat, else turned to `up` and clipped."""
    if up is None:
        return _shift(local, at)
    return _shift(clip_roof(_turn(local, up), up, _ROOF_DEG), at)


def _bay(g: _Frame, web: Face, kind: str) -> list[Point]:
    """The screw bay: a window whose base or jamb lies on the plate face, fitted into the web."""
    segs = _pts_of(web)
    spans = [g.R * BAY_SPAN * f for f in (1.0, 0.85, 0.7)] if g.up is None else []
    if g.up is None:
        for span in spans:
            rise = _head(kind, span)
            for sill in np.arange(g.margin, g.H, 1.0):
                top = g.H - g.t0 - g.margin
                jamb = top - sill - rise
                if jamb < 2 * g.keep_r:
                    break
                pts = _place(_lancet(kind, span, jamb), None, (span / 2, sill))
                if _fits(np.array(pts), segs, g.margin):
                    return pts
    else:
        # Standing up: the window rests its base on the plate face and points to +X.
        jamb = 2 * g.keep_r
        for span in np.arange(0.7 * (g.H - g.t0), 4 * g.keep_r, -2.0):
            for z0 in np.arange(g.margin, g.H - span, 1.0):
                pts = _place(_lancet(kind, span, jamb), g.up, (0.0, z0 + span / 2))
                if _fits(np.array(pts), segs, g.margin):
                    return pts
    raise ValueError(f"no room for the screw bay in the {g.d.name} web: make the bracket taller or longer")


def _base_last(pts: list[Point], standing: bool) -> list[Point]:
    """Roll a bay outline so that its base closes it: the sill (lying flat) or the plate face (standing)."""
    a = np.array(pts)
    n = len(a)
    col, at = (0, 0.0) if standing else (1, a[:, 1].min())
    for i in range(n):
        if abs(a[i, col] - at) < 1e-6 and abs(a[(i + 1) % n, col] - at) < 1e-6:
            return pts[i + 1 :] + pts[: i + 1]
    raise ValueError("bay outline has no base edge")


def _offset_open(pts: list[Point], dist: float) -> list[Point]:
    """Offset an open polyline of a ccw outline outward by `dist` (mitred corners)."""
    a = np.array(pts)
    d = np.diff(a, axis=0)
    d /= np.linalg.norm(d, axis=1)[:, None]
    nrm = np.stack([d[:, 1], -d[:, 0]], axis=1)  # right of the travel = outside of a ccw outline
    out = [a[0] + nrm[0] * dist]
    for i in range(1, len(a) - 1):
        m = nrm[i - 1] + nrm[i]
        m *= dist / max(1.0 + float(nrm[i - 1] @ nrm[i]), 1e-6)
        out.append(a[i] + m)
    out.append(a[-1] + nrm[-1] * dist)
    return [(float(u), float(v)) for u, v in out]


def _printable_void(void: Face, up: Point) -> list[Face]:
    """The largest part of a void under a 45 degree tent (towards `up`), so its roof needs no support.

    Unlike an opening, a void is bounded by members: its roof is filled down to the tent instead of
    being cut up into a point. The tent's apex is tried at points around the void, the roomiest wins.
    """
    a, b = _pts_of(void)
    span = float(np.ptp(np.concatenate([a, b]), axis=0).max()) * 4
    t = math.tan(math.radians(_ROOF_DEG))
    ux, uz = up
    sx, sz = uz, -ux  # sideways, perpendicular to up
    best: list[Face] = []
    best_area = 0.0
    for apex in a[:: max(1, len(a) // 48)]:
        ax, az = float(apex[0]), float(apex[1])
        tent = _poly([
            (ax, az),
            (ax + (-ux * span + sx * span / t), az + (-uz * span + sz * span / t)),
            (ax + (-ux * span - sx * span / t), az + (-uz * span - sz * span / t)),
        ])
        common = void & tent
        faces = common.faces() if common is not None else []
        area = sum(f.area for f in faces)
        if area > best_area:
            best, best_area = faces, area
    return best


# --- dialects -------------------------------------------------------------------------------------


def _web_end(g: _Frame) -> float:
    """Where a web meets the arm: WEB_TO of the reach, but clear of the eye so the corners finish apart."""
    return min(WEB_TO * g.R, g.arm_end - g.eye_r - 4 * g.edge)


def _gothic(g: _Frame) -> _Elevation:
    xe = _web_end(g)
    # The web's underside is a shallow cove (bulging towards the plate-arm corner), like a corbel.
    z_end = g.H - g.arm_t(xe)
    chord = math.hypot(xe, z_end)
    nx, nz = -z_end / chord, xe / chord
    under = [
        (xe * t + nx * GOTHIC_COVE * chord * 4 * t * (1 - t), z_end * t + nz * GOTHIC_COVE * chord * 4 * t * (1 - t))
        for t in np.linspace(0, 1, 17)
    ]
    web = _poly(under + [(0.0, g.H - g.t0)])
    x0 = -g.pt / 2
    arm_web = _poly([(x0, g.H), (g.arm_end, g.H), (g.arm_end, g.H - g.tip_t)] + under[::-1] + [(x0, 0.0)])
    solid = _trim(_fuse([_plate(g), arm_web, *_eye(g)]), g)
    bay = _bay(g, web, "pointed")
    openings = [bay] + _tracery(g, web, bay)
    if len(openings) == 1:
        note("cantilever", "gothic: no room for a second arch in the web, left out")
    return _Elevation(solid, openings, min(g.pt, g.tip_t), web, bay)


def _tracery(g: _Frame, web: Face, bay: list[Point]) -> list[list[Point]]:
    """Pointed arches filling the web beside the bay, each the largest that fits the roomiest gap left.

    Each is at most TRACERY_STEP of the one before, so the openings diminish towards the tip.
    """
    segs = _pts_of(web)
    placed = [np.array(bay)]
    width = np.ptp(placed[0][:, 0]) if g.up is None else np.ptp(placed[0][:, 1])
    gx, gz = np.meshgrid(np.arange(0, g.R, 1.5), np.arange(0, g.H, 1.5))
    grid = np.stack([gx.ravel(), gz.ravel()], axis=1)
    out: list[list[Point]] = []
    span = width
    for _ in range(TRACERY_MAX):
        free = web
        for pts in placed:
            free = free - _poly(_grow([(float(u), float(v)) for u, v in pts], g.margin))
        faces = free.faces() if free is not None else []
        if not faces:
            break
        c = max(faces, key=lambda f: f.area).center()
        found = _largest_arch(g, segs, placed, grid, TRACERY_STEP * span, np.array([c.X, c.Z]))
        if found is None:
            break
        span, pts = found
        placed.append(pts)
        out.append([(float(u), float(v)) for u, v in pts])
    return out


def _largest_arch(g: _Frame, segs: Segs, placed: list[np.ndarray], grid: np.ndarray, span_max: float, target: np.ndarray):
    """(span, outline) of the largest pointed arch up to span_max that fits, nearest `target`; None if none fits."""
    a, b = segs
    # A cheap first cut per span: the arch's middle must lie deep enough inside the web.
    for span in np.arange(span_max, TRACERY_MIN * g.p.min_wall_mm, -1.5):
        local = np.array(_place(arch("pointed", span, span * _SQRT3 / 2, n=20), g.up, (0.0, 0.0)))
        mid = local.mean(axis=0)
        reach = np.linalg.norm(local - mid, axis=1).min()  # the arch's middle is this far inside its outline
        near = _inside(grid + mid, a, b)
        near[near] = _point_seg_dist(grid[near] + mid, a, b).min(axis=1) >= g.margin + reach
        if not near.any():
            continue
        cand = grid[near][:, None, :] + local[None]  # (N, k, 2)
        n, k, _ = cand.shape
        flat = cand.reshape(-1, 2)
        ok = _inside(flat, a, b).reshape(n, k).all(axis=1)
        if not ok.any():
            continue
        sub = flat.reshape(n, k, 2)[ok].reshape(-1, 2)
        clear = _point_seg_dist(sub, a, b).min(axis=1).reshape(-1, k).min(axis=1) >= g.margin
        for pts in placed:
            pa, pb = pts, np.roll(pts, -1, axis=0)
            clear &= _point_seg_dist(sub, pa, pb).min(axis=1).reshape(-1, k).min(axis=1) >= g.margin
            clear &= ~_inside(sub.reshape(-1, k, 2)[:, 0], pa, pb)
        if not clear.any():
            continue
        fits = cand[ok][clear]
        best = fits[np.argmin(np.linalg.norm(fits.mean(axis=1) - target, axis=1))]
        return span, best
    return None


def _gaudi_top_circle(g: _Frame) -> tuple[float, float, float]:
    """(cx, cz, r) of the arc the gaudi arm's top follows: level at the plate, drooping to the tip.

    A true arc, not a spline: the top rounding along it is a torus, which tessellates cleanly.
    """
    droop = GAUDI_DROOP * g.R
    x0, x1 = -g.pt, g.arm_end
    cx = x0
    # Centre straight below the plate end, so the arc leaves the plate level: r^2 = (x1-x0)^2 + (r-droop)^2.
    r = ((x1 - x0) ** 2 + droop**2) / (2 * droop)
    return cx, g.H - r, r


def _gaudi_top(g: _Frame, x: float) -> float:
    cx, cz, r = _gaudi_top_circle(g)
    return cz + math.sqrt(max(r * r - (x - cx) ** 2, 0.0))


def _gaudi_arm_centre(g: _Frame, x: float) -> float:
    return _gaudi_top(g, x) - g.arm_t(x) / 2


def _gaudi_arm(g: _Frame) -> Face:
    """The arm: an arc on top, a spline underside `arm_t` below it, square ends."""
    x0, x1 = -g.pt, g.arm_end
    xm = (x0 + x1) / 2
    top = Edge.make_three_point_arc(*(Vector(x, 0, _gaudi_top(g, x)) for x in (x0, xm, x1)))
    xs = np.linspace(x1, x0, 9)
    under = Edge.make_spline([Vector(float(x), 0, _gaudi_top(g, x) - g.arm_t(x)) for x in xs])
    ends = [Edge.make_line(top @ 1, under @ 0), Edge.make_line(under @ 1, top @ 0)]
    face = Face(Wire([top, ends[0], under, ends[1]]))
    return face if face.normal_at().Y > 0 else -face


def _gaudi(g: _Frame) -> _Elevation:
    arm = _gaudi_arm(g)
    xe = GAUDI_BRACE_AT * g.R
    s, e = (-g.pt / 2, 0.0), (xe, _gaudi_arm_centre(g, xe))
    chord = math.hypot(e[0] - s[0], e[1] - s[1])
    centre = catenary(s, e, GAUDI_SAG * chord, n=16)
    widths = list(np.linspace(GAUDI_BRACE_ROOT * g.t0, g.t0, len(centre)))
    brace = curved_beam(centre, widths, p=g.p)
    # The plate stops inside the arm, whose arc top then runs on from the plate's back without a step.
    plate = _poly([(-g.pt, 0), (0, 0), (0, g.H - g.t0 / 2), (-g.pt, g.H - g.t0 / 2)])
    solid = _trim(_fuse([plate, arm, brace, *_eye(g)]), g)
    return _Elevation(solid, [], min(g.pt, g.tip_t, widths[-1]))


def _hitech(g: _Frame) -> _Elevation:
    bar = max(2 * g.p.min_wall_mm, HITECH_BAR * g.t0)
    node_d = HITECH_NODE * bar
    # Nodes sit on the plate face and on the arm's underside, so each disc shows as a half round boss.
    nodes = [(0.0, bar), (0.0, g.H - g.t0)] + [(f * g.R, g.H - g.arm_t(f * g.R) - bar / 2) for f in HITECH_NODES_AT]
    frame = truss(nodes, [(0, 2), (0, 3)], bar, node_d, p=g.p)
    solid = _trim(_fuse([_plate(g), _arm(g), frame, _disc(nodes[1], node_d / 2), *_eye(g)]), g)
    return _Elevation(solid, [], min(g.pt, g.tip_t, bar))


def _parametric(g: _Frame) -> _Elevation:
    xe = _web_end(g)
    s, e = (-g.pt / 2, 0.0), (xe, g.H - g.arm_t(xe) / 2)
    chord = math.hypot(e[0] - s[0], e[1] - s[1])
    centre = catenary(s, e, PARAM_SAG * chord, n=12)
    widths = list(np.linspace(g.t0, max(0.7 * g.t0, 2 * g.p.min_wall_mm), len(centre)))
    beam = curved_beam(centre, widths, p=g.p)
    fill = _poly(centre + [(xe, g.H - 0.5), (s[0], g.H - 0.5)])
    solid = _trim(_fuse([_plate(g), _arm(g), beam, fill, *_eye(g)]), g)
    # The web the lattice and the bay fit into: above the chord, below the arm, in front of the plate.
    web = fill - beam - _arm(g) - _plate(g)
    web_faces = web.faces()
    web = max(web_faces, key=lambda f: f.area)
    bay = _bay(g, web, "oval")
    return _Elevation(solid, [bay], min(g.pt, g.tip_t, widths[-1]), web, bay)


# --- screws, holes, lattices, ribs ----------------------------------------------------------------


def _place_screws(g: _Frame, elev: _Elevation, voids: list[Face]) -> list[float]:
    """Screw heights on the plate face: spread over the room the bay (or the void at the plate) leaves."""
    if elev.bay is not None:
        room = [_poly(elev.bay)]
    elif voids:
        room = voids
    else:
        room = [Face(w) for w in elev.solid.inner_wires()]
    angles = np.radians(np.linspace(-80, 80, 17))
    best: tuple[float, float] | None = None
    for region in room:
        segs = _pts_of(region)
        ok = []
        for z in np.arange(0.0, g.H, 0.5):
            head = np.stack([g.keep_r * np.cos(angles), z + g.keep_r * np.sin(angles)], axis=1)
            head[:, 0] = np.maximum(head[:, 0], 0.05)
            if _inside(head, *segs).all():
                ok.append(z)
        if ok and (best is None or ok[-1] - ok[0] > best[1] - best[0]):
            best = (ok[0], ok[-1])
    n = g.spec.screw_count
    if best is None or (n > 1 and best[1] - best[0] < 2 * g.keep_r):
        raise ValueError(f"no room for {n} {g.spec.screw} screw(s) on the plate face of the {g.d.name} bracket")
    if n == 1:
        return [best[1]]
    return [float(z) for z in np.linspace(best[0], best[1], n)]


def _keepout(g: _Frame, z: float) -> Face:
    """Keep-out disc around a screw on the plate's front face (plane x = 0)."""
    return Face(Wire.make_circle(g.keep_r, Plane(origin=(0, 0, z), x_dir=(0, 1, 0), z_dir=(1, 0, 0))))


def _check_keepouts(pts: list[Point], screws_z: list[float], r: float) -> None:
    """An opening must not reach into the plate where a screw's keep-out disc lies."""
    a = np.array(pts)
    for z in screws_z:
        band = np.abs(a[:, 1] - z) <= r
        if (a[band, 0] < -1e-6).any():
            raise ValueError("an opening cuts into the plate around a screw")


def _round_corners(face: Face, g: _Frame, convex: float) -> Face:
    """Rounded dialects round the elevation's corners in 2D, which seldom fails the way a 3D fillet does.

    Concave corners (where members meet) take the full dialect edge, convex ones `convex`; a corner
    that cannot take its radius tries half of it, then stays sharp. The vertical edges then are
    tangent seams and the 3D finish only rounds the top and bed outlines.
    """
    if g.d.edge != "fillet":
        return face
    for pos in [Vector(v) for v in face.vertices()]:
        found = _corner_at(face, pos)
        if found is None:
            continue
        vertex, is_convex = found
        r = convex if is_convex else g.edge
        for size in (r, r / 2):
            try:
                faces = fillet(vertex, size).faces()
            except Exception:  # noqa: BLE001  OCCT refuses a radius that does not fit
                continue
            # Accept only a rounding that kept every hole and moved no more than a corner's worth of area.
            if (
                len(faces) == 1
                and faces[0].is_valid
                and len(faces[0].inner_wires()) == len(face.inner_wires())
                and abs(faces[0].area - face.area) < size * size
            ):
                face = faces[0]
                break
    return face


def _corner_at(face: Face, pos: Vector):
    """(vertex, convex?) of the face's vertex at `pos` when its two edges meet at an angle, else None."""
    vertex = next((v for v in face.vertices() if (Vector(v) - pos).length < 1e-6), None)
    if vertex is None:
        return None
    dirs = []
    for e in face.edges():
        if (e @ 0 - pos).length < 1e-6:
            dirs.append(e % 0)
        elif (e @ 1 - pos).length < 1e-6:
            dirs.append(-(e % 1))
    if len(dirs) != 2 or dirs[0].dot(dirs[1]) < -math.cos(math.radians(1.0)):
        return None  # tangent: the edges run on in a straight line
    bisector = (dirs[0] + dirs[1]).normalized()
    return vertex, face.is_inside(pos + bisector * 0.05)


def _extrude(shape, depth: float):
    """Through-extrusion of faces in the XZ plane over -depth/2 <= y <= depth/2 (one piece, no seam at y = 0)."""
    solids = [Solid.extrude(Pos(0, -depth / 2, 0) * f, Vector(0, depth, 0)) for f in shape.faces()]
    return solids[0] if len(solids) == 1 else Compound(solids)


def _one(shape) -> Solid:
    solids = shape.solids()
    if len(solids) != 1:
        raise ValueError(f"the bracket fell apart into {len(solids)} bodies")
    return solids[0]


def _cap_face(d: float, up: Point, plane: Plane) -> Face:
    """The 45 degree cap that turns a round hole of diameter d into a teardrop pointing to `up`."""
    return to_face(clip_roof(_turn(arch("round", d, d / 2, n=32), up), up, _ROOF_DEG), plane)


def _screw_tool(g: _Frame, z: float, print_down: str):
    hole = Pos(0, 0, z) * Rot(0, 90, 0) * fasteners.clearance_hole(g.spec.screw, g.pt + 1, g.p)
    plane = Plane(origin=(0.5, 0, z), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    up = in_plane_up(plane, print_down)
    if up is None:
        return hole
    cap = extrude(_cap_face(_hole_d(g.spec.screw, g.p), up, plane), amount=g.pt + 1.5, dir=(-1, 0, 0))
    return hole + cap


def _tip_tool(g: _Frame):
    x, z = g.tip_at
    d = g.spec.depth
    hole = Pos(x, -(d / 2 + 1), z) * Rot(90, 0, 0) * fasteners.clearance_hole(g.spec.tip_hole, d + 2, g.p)
    if g.up is None:
        return hole
    cap = _cap_face(_hole_d(g.spec.tip_hole, g.p), g.up, Plane(origin=(x, 0, z), x_dir=(1, 0, 0), z_dir=(0, -1, 0)))
    return hole + _extrude(cap, d + 2)


def _relief_rib(g: _Frame, bay: list[Point]) -> Solid:
    """Gothic hood mould: a rib following the bay's arch on the +Y face, clear of the edge finish."""
    w = g.p.min_wall_mm
    path = _offset_open(_base_last(_coarse(bay), g.up is not None), g.edge + w)
    if g.up is not None:
        # Standing up the rib's ends run down onto the bed instead of hanging in the air.
        path = [(-g.pt, path[0][1])] + path + [(-g.pt, path[-1][1])]
    plane = Plane(origin=(0, g.spec.depth / 2, 0), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
    return rib([(u, -v) for u, v in path], w, RIB_HEIGHT_LAYERS * g.p.layer_mm, plane, p=g.p)


def _coarse(pts: list[Point], step: float = 2.0) -> list[Point]:
    """Drop points closer than `step` to the last kept one (keeps corners: the rib is a chain of bars)."""
    out = [pts[0]]
    for i, q in enumerate(pts[1:], 1):
        nxt = pts[(i + 1) % len(pts)]
        turn = _corner(out[-1], q, nxt)
        if math.dist(q, out[-1]) >= step or turn > 20:
            out.append(q)
    return out


def _corner(a: Point, b: Point, c: Point) -> float:
    d1 = (b[0] - a[0], b[1] - a[1])
    d2 = (c[0] - b[0], c[1] - b[1])
    n1, n2 = math.hypot(*d1), math.hypot(*d2)
    if n1 < 1e-9 or n2 < 1e-9:
        return 0.0
    cos = (d1[0] * d2[0] + d1[1] * d2[1]) / (n1 * n2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def _parametric_lattice(g: _Frame, elev: _Elevation, body: Solid, keepouts: list[Face], print_down: str) -> Solid:
    """Graded hex lattice in the web: densest bars at the plate-arm corner, where the bending peaks."""
    region = elev.web - _poly(_grow(elev.bay, g.margin))
    region = max(region.faces(), key=lambda f: f.area)
    plane = Plane(region)
    corner = Vector(0, 0, g.H - g.t0) - plane.origin
    cu, cv = corner.dot(plane.x_dir), corner.dot(plane.y_dir)
    # The web's diagonal: from the corner to the farthest point of the web.
    wa, _ = _pts_of(elev.web, plane)
    diag = float(np.max(np.hypot(wa[:, 0] - cu, wa[:, 1] - cv)))

    def field(u: float, v: float) -> float:
        return 1.0 - math.hypot(u - cu, v - cv) / diag

    cut = lattice(
        region, g.p, kind="hex", cell=PARAM_HEX_CELL * g.p.min_wall_mm, bar_max=PARAM_BAR_MAX * g.p.min_wall_mm,
        field=field, keepout=keepouts, up=in_plane_up(plane, print_down),
    )
    if cut.tool is None:
        return body
    return _one(body - _extrude(cut.tool, g.spec.depth + 2))


def _grow(pts: list[Point], dist: float) -> list[Point]:
    """A convex ccw outline grown by `dist` (points pushed along the mitred normals)."""
    closed = pts + pts[:2]
    grown = _offset_open(closed, dist)[1:-1]
    return grown[-1:] + grown[:-1]


def _plate_lattice(g: _Frame, body: Solid, screws_z: list[float], keepouts: list[Face], print_down: str) -> Solid:
    """Uniform triangle lattice through the wall plate between the screws."""
    if len(screws_z) < 2:
        note("cantilever", "hitech: one screw, no plate lattice")
        return body
    half = g.spec.depth / 2 - g.edge
    lo, hi = min(screws_z), max(screws_z)
    region = Plane(origin=(0, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    face = to_face([(-half, lo), (half, lo), (half, hi), (-half, hi)], region)
    cut = lattice(
        face, g.p, kind="tri", cell=HITECH_TRI_CELL * g.p.min_wall_mm, keepout=keepouts,
        up=in_plane_up(Plane(face), print_down),
    )
    if cut.tool is None:
        return body
    tool = extrude(Pos(0.5, 0, 0) * cut.tool, amount=g.pt + 1.5, dir=(-1, 0, 0))
    return _one(body - tool)
