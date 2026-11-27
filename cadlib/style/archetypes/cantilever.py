"""Cantilever bracket: a wall plate, an arm and bracing, drawn as an elevation and extruded to depth.

Frame: the plate occupies -plate_t <= x <= 0 (its back, x = -plate_t, lies against the wall), the arm
runs along +X at the top, z from 0 to `height`, the depth runs along Y centred on y = 0. The
elevation lives in Plane.XZ (u = X, v = Z), so every void and lattice cell is a through-cut along Y.

Mounting: keyhole slots in the plate. The screws are set in the wall first, their heads pass the
round entries on the plate's back and the bracket slides down onto them. The heads ride in a channel
inside the plate, so the bracing in front of the plate stays whole and needs no driver access.

Print orientations: "-y" (default) lies the elevation on the bed, every cut is vertical and the load
acts in the layer plane. "-x" stands the bracket on its wall plate: a void between members is then
filled under its roof down to a 45 degree tent, holes get a 45 degree cap and pockets keep flat-top roofs.

Rules of thumb (part 1 has no load calculation): the arm tapers by the dialect's ratio, the bracing
meets the arm at 0.75-0.9 of the reach, relief ribs are 2 x min_wall wide.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np
from build123d import Box, Compound, Cylinder, Edge, Face, Kind, Plane, Pos, Rot, Solid, Vector, Wire, extrude, fillet, offset

from cadlib import fasteners
from cadlib.config import Profile
from cadlib.style.archetypes.types import Archetype, Load, Support, Tunable
from cadlib.style.dialects import Dialect, edge_size, finish_extrusion, get_dialect
from cadlib.style.lattice import LatticeCut, _segments, lattice
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
GOTHIC_STRUT_TO = 0.75     # the pointed-arch strut meets the arm's underside at this share of the reach
GOTHIC_STRUT_W = 0.8       # strut width / root_t
HITECH_NODES_AT = (0.5, 0.9)
HITECH_BAR = 0.3           # truss bar / root_t (floored at 2 x min_wall)
HITECH_NODE = 2.5          # node disc diameter / bar
HITECH_TRI_CELL = 6.0      # arm pocket triangle side / min_wall
HITECH_POCKET = 1 / 3      # pocket depth / bracket depth
WEB_TO = 0.9               # the parametric web meets the arm at this share of the reach
PARAM_SAG = 0.08           # parametric web underside sag / chord length
PARAM_HEX_CELL = 6.5       # hex pitch / min_wall
PARAM_BAR_MAX = 4.0        # thickest hex bar (at the plate-arm corner) / min_wall
PARAM_BORDER = 2.0         # solid border round the hex field / min_wall
BIO_STRANDS_TO = (0.3, 0.5, 0.7, 0.88)  # where the tendons meet the arm, share of the reach
BIO_ROOT_GAP = 2.5         # gap between tendon roots on the plate / min_wall
BIO_SAG = 0.14             # tendon bow / chord length
BIO_ROOT_W = 0.45          # tendon width at the plate / root_t
BIO_VERTEBRA = 0.08        # first vertebra pitch / reach
BIO_SHRINK = 0.92          # each vertebra pitch is this share of the one before
RIB_WIDTH_WALLS = 2        # relief rib width / min_wall
RIB_HEIGHT_LAYERS = 15     # relief rib height / layer
THIN_EDGE = 0.45           # an edge finish is at most this share of the thinnest member

_SQRT3 = math.sqrt(3.0)
_ROOF_DEG = 46.0  # roofs are clipped a degree steeper than the 45 degree limit, clear of rounding noise
_RIB_MAX_SLOPE = 0.69  # standing up, a relief rib stops where its path runs flatter than ~46 degrees
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
    keep_r: float          # keep-out radius round a screw: (hole + 4 x min_wall) / 2
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

    @property
    def rib_w(self) -> float:
        return RIB_WIDTH_WALLS * self.p.min_wall_mm

    def arm_t(self, x: float) -> float:
        return self.t0 + (self.tip_t - self.t0) * min(max(x / self.arm_end, 0.0), 1.0)


@dataclass
class _Elevation:
    solid: Face                      # the elevation with its inherent voids (members fused)
    thin: float                      # the thinnest member: edge finishes stay below half of it
    web: Face | None = None          # the region a web lattice fills (parametric)
    ribs: list[list[Point]] = field(default_factory=list)  # relief rib paths on the +Y face, in (x, z)
    vertebrae: list[tuple[float, float]] = field(default_factory=list)  # (x, width) of spine segments


@dataclass(frozen=True)
class _Keyhole:
    """A keyhole slot in the plate: the screw's shank ends at z, the head enters `slide` lower."""

    z: float
    slot_w: float          # shank slot through the plate's back layer
    head_r: float          # entry and channel half width
    back: float            # plate layer behind the head (against the wall)
    front: float           # x of the channel's front face
    slide: float           # travel from the entry up to the shank's stop

    @property
    def z_lo(self) -> float:
        return self.z - self.slide - self.head_r

    @property
    def z_hi(self) -> float:
        return self.z + self.head_r


def cantilever(style: str, spec: CantileverSpec, p: Profile, print_down: str = "-y") -> Archetype:
    """A cantilever bracket in the given dialect, see the module docstring for the frame."""
    dialect = get_dialect(style)
    if print_down not in ALLOWED_PRINT_DOWN:
        raise ValueError(f"print_down {print_down!r}: the cantilever prints with {' or '.join(ALLOWED_PRINT_DOWN)} down")
    _validate(spec, p)
    g = _frame(spec, p, dialect, print_down)

    keys = _keyholes(g)
    keepouts = [_poly(_keyhole_footprint(g, k, p.min_wall_mm)) for k in keys]
    elev = _BUILDERS[style](g)
    # A screw boss in front of each channel that pokes out of the plate, so a head never rides in the open.
    bosses = [_poly(_keyhole_footprint(g, k, p.min_wall_mm, boss=True)) for k in keys if k.front > -p.min_wall_mm]
    if bosses:
        elev = replace(elev, solid=_trim(_fuse([elev.solid, *bosses]), g))
    voids = [] if g.up is None else [f for w in elev.solid.inner_wires() for f in _printable_void(Face(w), g.up)]

    edge = min(g.edge, THIN_EDGE * elev.thin)
    if edge < g.edge:
        note("cantilever", f"{style}: edge {g.edge:.1f} mm shrunk to {edge:.1f} mm, thinnest member {elev.thin:.1f} mm", "info")
    # Lying down the voids are finished with the outline. Standing up their tent roofs keep a sharp
    # apex, so they are cut after the finish.
    if g.up is None:
        face = _round_corners(elev.solid, g, edge)
        body = finish_extrusion(_extrude(face, spec.depth), dialect, spec.depth, print_down, p, edge)
    else:
        envelope = _round_corners(Face(elev.solid.outer_wire()), g, edge)
        body = finish_extrusion(_extrude(envelope, spec.depth), dialect, spec.depth, print_down, p, edge)
        if voids:
            body = _one(body - _extrude(Compound(voids), spec.depth + 2))

    cut = _lattice_cut(g, elev, keepouts, print_down, edge)
    if cut is not None and cut.tool is not None:
        body = _one(body - _lattice_tool(g, cut))
    for k in keys:
        body = _one(body - _keyhole_tool(g, k, print_down))
    if spec.tip_hole is not None:
        body = _one(body - _tip_tool(g))
    if dialect.relief_ribs:
        for path in elev.ribs:
            body = _one(body + _rib_solid(g, path, g.rib_w))
        if elev.vertebrae:
            body = _one(body + _spine_cord(g, elev.vertebrae))
        for x, w in elev.vertebrae:
            body = _one(body + _vertebra(g, x, w, edge))

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
    head = fasteners.metric(spec.screw).head_d + 2 * p.slide_fit_mm
    if spec.depth < head + 4 * p.min_wall_mm:
        raise ValueError(f"depth {spec.depth:g} mm leaves no wall round a {head:g} mm keyhole for the {spec.screw} head")


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


def _poly(pts: list[Point], smooth_deg: float = 12.0) -> Face:
    """Planar face of an (x, z) outline, wound so its normal is +Y like the members' faces (they fuse).

    Runs of points that turn by less than smooth_deg per vertex become one spline, so a sampled
    arch is a few smooth edges an edge finish can follow, not dozens of facets.
    """
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))
    pts = pts if area < 0 else pts[::-1]
    n = len(pts)
    seg = [math.dist(pts[i], pts[(i + 1) % n]) for i in range(n)]
    long = 2.5 * float(np.median(seg))  # a straight run (a jamb) between sampled curves stays a line
    corners = [
        i for i in range(n)
        if _corner(pts[i - 1], pts[i], pts[(i + 1) % n]) > smooth_deg or max(seg[i - 1], seg[i]) > long
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



def _turn(pts: list[Point], up: Point) -> list[Point]:
    """Turn points whose apex is +v so that it points along `up`."""
    ang = math.atan2(up[1], up[0]) - math.pi / 2
    c, s = math.cos(ang), math.sin(ang)
    return [(c * u - s * v, s * u + c * v) for u, v in pts]


def _shift(pts: list[Point], at: Point) -> list[Point]:
    return [(u + at[0], v + at[1]) for u, v in pts]


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


def _gothic(g: _Frame) -> _Elevation:
    """A flying buttress: one pointed-arch strut springing level from the plate's foot to the arm.

    The strut's intrados is one leg of a pointed arch: a circle centred on the plate face, so it
    leaves the plate square to it and meets the arm's underside at an angle, the arch's point.
    Nervure ribs run along the intrados and along the arm's lower edge on the +Y face.
    """
    w = max(GOTHIC_STRUT_W * g.t0, 2 * g.p.min_wall_mm)
    z_f = w  # the strut's extrados reaches z = 0 at the plate
    xe = GOTHIC_STRUT_TO * g.R
    ze = g.H - g.arm_t(xe)
    rise = ze - z_f
    rho = (xe * xe + rise * rise) / (2 * rise)
    cz = z_f + rho

    def at(r: float, phi: float) -> Point:
        return (r * math.cos(phi), cz + r * math.sin(phi))

    # The extrados runs on until it is well inside the arm, so the strut lands on it full width.
    phi_end = -math.pi / 2
    while at(rho + w, phi_end)[1] < g.H - g.arm_t(at(rho + w, phi_end)[0]) + g.arm_t(xe) / 2:
        phi_end += math.radians(0.5)
    phis = np.linspace(-math.pi / 2, phi_end, 24)
    strut = _poly(
        [(-g.pt / 2, 0.0)] + [at(rho + w, f) for f in phis] + [at(rho, f) for f in phis[::-1]] + [(-g.pt / 2, z_f)]
    )
    solid = _trim(_fuse([_plate(g), _arm(g), strut, *_eye(g)]), g)

    off = g.edge + g.rib_w / 2 + 0.2  # a rib stays clear of the edge chamfer
    x_start = -g.pt + g.edge + g.rib_w / 2 + 0.2
    intrados = [(x_start, z_f - off)]
    for f in np.linspace(-math.pi / 2, phi_end, 48):
        x, z = at(rho + off, f)
        if z + g.rib_w / 2 > g.H - g.arm_t(x) - off:
            break  # reached the arm: its own rib takes over
        if g.up is not None and abs(math.cos(f)) > _RIB_MAX_SLOPE:
            break  # standing up, the rest of the arc would hang out flatter than 45 degrees
        intrados.append((x, z))
    x_end = g.arm_end - g.eye_r - g.rib_w
    arm_rib = [(x_start, g.H - g.t0 + off), (x_end, g.H - g.arm_t(x_end) + off)]
    ribs = [arm_rib] + ([intrados] if len(intrados) > 2 else [])
    return _Elevation(solid, min(g.pt, g.tip_t, w), ribs=ribs)


# The gaudi arm keeps its own builder instead of members.curved_beam: curved_beam makes both sides
# splines, and the 3D rounding along a spline top tessellated into a sliver triangle that the strict
# overhang check counted. An arc top rounds into a torus, which tessellates cleanly.
def _gaudi_top_circle(g: _Frame) -> tuple[float, float, float]:
    """(cx, cz, r) of the arc the gaudi arm's top follows: level at the plate, drooping to the tip."""
    droop = GAUDI_DROOP * g.R
    x0, x1 = -g.pt, g.arm_end
    # Centre straight below the plate end, so the arc leaves the plate level: r^2 = (x1-x0)^2 + (r-droop)^2.
    r = ((x1 - x0) ** 2 + droop**2) / (2 * droop)
    return x0, g.H - r, r


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
    return _Elevation(solid, min(g.pt, g.tip_t, widths[-1]))



def _hitech(g: _Frame) -> _Elevation:
    bar = max(2 * g.p.min_wall_mm, HITECH_BAR * g.t0)
    node_d = HITECH_NODE * bar
    # Nodes sit on the plate face and on the arm's underside, so each disc shows as a half round boss.
    nodes = [(0.0, bar), (0.0, g.H - g.t0)] + [(f * g.R, g.H - g.arm_t(f * g.R) - bar / 2) for f in HITECH_NODES_AT]
    frame = truss(nodes, [(0, 2), (0, 3)], bar, node_d, p=g.p)
    solid = _trim(_fuse([_plate(g), _arm(g), frame, _disc(nodes[1], node_d / 2), *_eye(g)]), g)
    return _Elevation(solid, min(g.pt, g.tip_t, bar))


def _parametric(g: _Frame) -> _Elevation:
    """A web under a sagging spline, its whole field perforated by a graded hex lattice."""
    xe = min(WEB_TO * g.R, g.arm_end - g.eye_r - 4 * g.edge)
    s, e = (-g.pt / 2, 0.0), (xe, g.H - g.arm_t(xe))
    chord = math.hypot(e[0] - s[0], e[1] - s[1])
    under = catenary(s, e, PARAM_SAG * chord, n=16)
    fill = _poly(under + [(xe, g.H - 0.5), (s[0], g.H - 0.5)])
    solid = _trim(_fuse([_plate(g), _arm(g), fill, *_eye(g)]), g)
    web = max((fill - _arm(g) - _plate(g)).faces(), key=lambda f: f.area)
    return _Elevation(solid, min(g.pt, g.tip_t), web=web)


def _biomech(g: _Frame) -> _Elevation:
    """Tendons fanning from a common root on the plate to the arm, and a segmented spine along the arm.

    The lowest root runs to the farthest point, so the strands never cross; each bows outwards, which
    opens gaps that widen from the plate. The 2D rounding (the full dialect edge in every concave
    corner) merges their ends smoothly into the plate and the arm.
    """
    w_root = max(2 * g.p.min_wall_mm, BIO_ROOT_W * g.t0)
    w_end = 2 * g.p.min_wall_mm * 1.05
    strands = []
    for i, f in enumerate(reversed(BIO_STRANDS_TO)):
        p0 = (-g.pt / 2, w_root / 2 + i * (w_root + BIO_ROOT_GAP * g.p.min_wall_mm))
        x2 = f * g.R
        p2 = (x2, g.H - g.arm_t(x2) / 2)
        dx, dz = p2[0] - p0[0], p2[1] - p0[1]
        p1 = ((p0[0] + p2[0]) / 2 + BIO_SAG * dz, (p0[1] + p2[1]) / 2 - BIO_SAG * dx)  # bowed down and out
        ts = np.linspace(0, 1, 14)
        centre = [
            (float((1 - t) ** 2 * p0[0] + 2 * t * (1 - t) * p1[0] + t * t * p2[0]),
             float((1 - t) ** 2 * p0[1] + 2 * t * (1 - t) * p1[1] + t * t * p2[1]))
            for t in ts
        ]
        strands.append(curved_beam(centre, list(np.linspace(w_root, w_end, len(ts))), p=g.p))
    solid = _trim(_fuse([_plate(g), _arm(g), *strands, *_eye(g)]), g)

    vertebrae = []
    x, pitch = 2 * g.edge + g.p.min_wall_mm, BIO_VERTEBRA * g.R
    while x < g.arm_end - g.eye_r - g.p.min_wall_mm and pitch >= 2 * g.p.min_wall_mm:
        vertebrae.append((x, max(g.p.min_wall_mm, 0.4 * pitch)))
        x += pitch
        pitch *= BIO_SHRINK
    return _Elevation(solid, min(g.pt, g.tip_t, w_end), vertebrae=vertebrae)


_BUILDERS = {"gothic": _gothic, "gaudi": _gaudi, "hitech": _hitech, "parametric": _parametric, "biomech": _biomech}


# --- mounting: keyhole slots ------------------------------------------------------------------------


def _keyholes(g: _Frame) -> list[_Keyhole]:
    """Keyholes spread over the plate's height, the top one as high as the plate allows (it takes the pull)."""
    m = fasteners.metric(g.spec.screw)
    head_r = (m.head_d + 2 * g.p.slide_fit_mm) / 2
    back = 2 * g.p.min_wall_mm
    proto = _Keyhole(
        z=0.0, slot_w=_hole_d(g.spec.screw, g.p), head_r=head_r, back=back,
        front=-g.pt + back + m.head_h + g.p.slide_fit_mm, slide=2 * head_r,
    )
    margin = 4 * g.p.min_wall_mm  # the same for every dialect, so the wall screws do not move with the style
    z_top = g.H - margin - proto.head_r
    z_bottom = margin + proto.slide + proto.head_r
    n = g.spec.screw_count
    # Neighbours keep their keep-out discs apart and leave a wall between their footprints.
    pitch = max(2 * g.keep_r, proto.z_hi - proto.z_lo + 2 * g.p.min_wall_mm)
    if (n - 1) * pitch > z_top - z_bottom:
        need = (n - 1) * pitch + z_bottom + g.H - z_top
        raise ValueError(f"no room for {n} {g.spec.screw} keyholes on a {g.H:g} mm plate: they need {need:.0f} mm")
    zs = [z_top] if n == 1 else list(np.linspace(z_top, z_bottom, n))
    return [replace(proto, z=float(z)) for z in zs]


def _keyhole_footprint(g: _Frame, k: _Keyhole, grow: float, boss: bool = False) -> list[Point]:
    """The keyhole's outline in the elevation (x, z), grown by `grow`; with boss, the pad round its channel."""
    x1 = max(k.front, 0.0) + grow if boss else k.front + grow
    x0 = -g.pt / 2 if boss else -g.pt
    return [(x0, k.z_lo - grow), (x1, k.z_lo - grow), (x1, k.z_hi + grow), (x0, k.z_hi + grow)]


def _keyhole_tool(g: _Frame, k: _Keyhole, print_down: str):
    """Slot for the shank through the back layer, a round entry for the head, a channel the head slides in.

    The ends are square: a round end lying horizontal in print would hang. Lying down (-y) the round
    entry is horizontal too and gets a 45 degree cap towards +Y.
    """
    x_wall = -g.pt - 1
    z_entry = k.z - k.slide
    slot_len = k.slide + k.slot_w / 2
    slot = Pos((x_wall + (-g.pt + k.back + 0.01)) / 2, 0, z_entry + slot_len / 2) * Box(
        -g.pt + k.back + 0.01 - x_wall, k.slot_w, slot_len
    )
    channel_len = k.slide + k.head_r
    channel = Pos((-g.pt + k.back + k.front) / 2, 0, z_entry + channel_len / 2) * Box(
        k.front - (-g.pt + k.back), 2 * k.head_r, channel_len
    )
    reach = k.front - x_wall
    entry = Pos(x_wall + reach / 2, 0, z_entry) * Rot(0, 90, 0) * Cylinder(k.head_r, reach)
    tool = slot + channel + entry
    plane = Plane(origin=(x_wall, 0, z_entry), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    up = in_plane_up(plane, print_down)
    if up is not None:
        tool = tool + extrude(_cap_face(2 * k.head_r, up, plane), amount=reach)
    return tool


# --- lattices and relief ----------------------------------------------------------------------------


def _lattice_cut(g: _Frame, elev: _Elevation, keepouts: list[Face], print_down: str, edge: float) -> LatticeCut | None:
    """The dialect's lattice: parametric's graded hex field in the web, hitech's triangle pockets on the arm."""
    if g.d.name == "parametric":
        # The field follows the web's outline: the web inset by a solid border.
        region = max(offset(elev.web, -PARAM_BORDER * g.p.min_wall_mm, kind=Kind.ARC).faces(), key=lambda f: f.area)
        plane = Plane(region)
        corner = Vector(0, 0, g.H - g.t0) - plane.origin
        cu, cv = corner.dot(plane.x_dir), corner.dot(plane.y_dir)
        ra, _ = _segments(region, plane)
        dist = np.hypot(ra[:, 0] - cu, ra[:, 1] - cv)
        cell = PARAM_HEX_CELL * g.p.min_wall_mm
        near, far = float(dist.min()) + cell / 2, float(dist.max()) - cell  # cell centres stay this far in

        def field(u: float, v: float) -> float:
            # 1 (thickest bars) nearest the plate-arm corner, where the bending peaks, 0 at the far end
            # of the field: the whole range of bars shows across the web.
            return (far - math.hypot(u - cu, v - cv)) / (far - near)

        return lattice(
            region, g.p, kind="hex", cell=cell, bar_max=PARAM_BAR_MAX * g.p.min_wall_mm,
            field=field, keepout=keepouts, up=in_plane_up(plane, print_down),
        )
    if g.d.name == "hitech":
        # Blind triangle pockets along the arm's +Y face (up in print lying down, so seen in use).
        x0 = g.edge + g.p.min_wall_mm
        x1 = g.tip_at[0] - _hole_d(g.spec.tip_hole, g.p) / 2 - 2 * g.p.min_wall_mm if g.spec.tip_hole else g.arm_end - edge
        z0, z1 = g.H - min(g.t0, g.tip_t) + edge, g.H - edge
        face = _side_rect(g, x0, x1, z0, z1)
        if g.up is None:
            # Lying down the grid's rows run along the arm and the grid is centred on the region's box,
            # which puts a row boundary on the band's middle. A 1 mm tail below the band (too narrow
            # for a cell) moves the box half a row down, so one row of alternating triangles fills the band.
            row = HITECH_TRI_CELL * g.p.min_wall_mm * _SQRT3 / 2
            face = (face + _side_rect(g, x0, x0 + 1.0, z0 - row, z0 + 0.1)).faces()[0]
        return lattice(
            face, g.p, kind="tri", cell=HITECH_TRI_CELL * g.p.min_wall_mm, keepout=keepouts,
            up=in_plane_up(Plane(face), print_down),
        )
    return None


def _side_rect(g: _Frame, x0: float, x1: float, z0: float, z1: float) -> Face:
    """A rectangle on the +Y face whose own plane runs u along X (make_rect keeps the given axes)."""
    centre = ((x0 + x1) / 2, g.spec.depth / 2, (z0 + z1) / 2)
    return Face.make_rect(x1 - x0, z1 - z0, Plane(origin=centre, x_dir=(1, 0, 0), z_dir=(0, 1, 0)))


def _side_plane(g: _Frame) -> Plane:
    """The +Y face as a sketch plane: u = X, v = -Z (its normal points out of the face)."""
    return Plane(origin=(0, g.spec.depth / 2, 0), x_dir=(1, 0, 0), z_dir=(0, 1, 0))


def _lattice_tool(g: _Frame, cut: LatticeCut):
    if g.d.name == "hitech":
        depth = HITECH_POCKET * g.spec.depth
        return extrude(Pos(0, 0.5, 0) * cut.tool, amount=depth + 0.5, dir=(0, -1, 0))
    return _extrude(cut.tool, g.spec.depth + 2)


def _rib_solid(g: _Frame, path: list[Point], width: float, height: float | None = None) -> Solid:
    """A relief rib on the +Y face along an (x, z) path."""
    h = RIB_HEIGHT_LAYERS * g.p.layer_mm if height is None else height
    return rib([(u, -v) for u, v in path], width, h, _side_plane(g), p=g.p)


def _vertebra(g: _Frame, x: float, width: float, edge: float) -> Solid:
    """One spine segment: a bar across the arm on the +Y face, clear of the edge finish."""
    inset = edge + 0.5
    return _rib_solid(g, [(x, g.H - g.arm_t(x) + inset), (x, g.H - inset)], width)


def _spine_cord(g: _Frame, vertebrae: list[tuple[float, float]]) -> Solid:
    """The low cord the vertebrae sit on, along the arm's middle."""
    x0, x1 = vertebrae[0][0], vertebrae[-1][0]
    path = [(x0, g.H - g.arm_t(x0) / 2), (x1, g.H - g.arm_t(x1) / 2)]
    return _rib_solid(g, path, g.p.min_wall_mm, RIB_HEIGHT_LAYERS * g.p.layer_mm / 2)


# --- shared tools -----------------------------------------------------------------------------------


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


def _tip_tool(g: _Frame):
    x, z = g.tip_at
    d = g.spec.depth
    hole = Pos(x, -(d / 2 + 1), z) * Rot(90, 0, 0) * fasteners.clearance_hole(g.spec.tip_hole, d + 2, g.p)
    if g.up is None:
        return hole
    cap = _cap_face(_hole_d(g.spec.tip_hole, g.p), g.up, Plane(origin=(x, 0, z), x_dir=(1, 0, 0), z_dir=(0, -1, 0)))
    return hole + _extrude(cap, d + 2)


def _corner(a: Point, b: Point, c: Point) -> float:
    d1 = (b[0] - a[0], b[1] - a[1])
    d2 = (c[0] - b[0], c[1] - b[1])
    n1, n2 = math.hypot(*d1), math.hypot(*d2)
    if n1 < 1e-9 or n2 < 1e-9:
        return 0.0
    cos = (d1[0] * d2[0] + d1[1] * d2[1]) / (n1 * n2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))

