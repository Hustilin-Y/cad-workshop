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
from build123d import Box, Compound, Cylinder, Edge, Face, Kind, Plane, Pos, Rot, Solid, Vector, Wire, extrude, offset

from cadlib import fasteners
from cadlib.config import Profile
from cadlib.style.archetypes.elevation import (
    RIB_HEIGHT_LAYERS, RIB_WIDTH_WALLS, ROOF_DEG, THIN_EDGE, band, cap_face, disc, extrude_y, fuse, offset_path, one,
    point_field, poly, round_corners, shift,
)
from cadlib.style.archetypes.types import Archetype, Load, Support, Tunable
from cadlib.style.dialects import Dialect, edge_size, finish_extrusion, get_dialect
from cadlib.style.lattice import LatticeCut, _segments, lattice
from cadlib.style.log import note
from cadlib.style.members import catenary, curved_beam, rib, truss
from cadlib.style.outline import Point, arch, clip_roof
from cadlib.style.plane import in_plane_up

ALLOWED_PRINT_DOWN = ("-y", "-x")

# Archetype ratios (dimensionless, see the module docstring).
GAUDI_BRACE_AT = 0.8       # the catenary brace meets the arm at this share of the reach
GAUDI_BRACE_ROOT = 1.6     # brace width at the plate / root_t
GAUDI_SAG = 0.1            # brace sag / chord length
GAUDI_DROOP = 0.08         # the arm's tip droops by this share of the reach
GOTHIC_STRUT_TO = 0.85     # the buttress strut meets the arm at this share of the reach
GOTHIC_STRUT_W = 0.8       # strut width / root_t
GOTHIC_ARCH_SPAN = 0.25    # pointed window span / reach
GOTHIC_APEX_GAP = 0.4      # solid left between the window's point and the arm's underside / root_t
GOTHIC_FINIAL = 1.2        # spear finial beyond the eye / eye radius
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
BIO_SAG = 0.12             # biomech web underside sag / chord length
BIO_CELL = 5.0             # smallest organic cell (at the plate-arm corner) / min_wall
BIO_BAR_MAX = 3.0          # thickest organic bar (at the corner) / min_wall
BIO_BORDER = 2.0           # solid rim round the organic field / min_wall
BIO_SEED = 0               # organic lattice seed: the same seed, the same bracket
BIO_BEND = 1.5             # rounding where the web meets the arm and the eye / root_t
BIO_OUTER = 0.8            # rounding of the other outer corners / root_t
RIB_RAMP = 1.1             # standing up, a rib's end slopes over this many rib heights (a little under 45 deg)

_SQRT3 = math.sqrt(3.0)
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
    extra: list[Face] = field(default_factory=list)  # pieces fused after the trim (the gothic finial)


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
    keepouts = [poly(_keyhole_footprint(g, k, p.min_wall_mm)) for k in keys]
    elev = _BUILDERS[style](g)
    edge = min(g.edge, THIN_EDGE * elev.thin)
    if edge < g.edge:
        note("cantilever", f"{style}: edge {g.edge:.1f} mm shrunk to {edge:.1f} mm, thinnest member {elev.thin:.1f} mm", "info")
    # A screw boss in front of each channel that pokes out of the plate, so a head never rides in the
    # open. It joins after the 2D rounding (which would round it away) and is kept out of every void.
    # Lying down its corners are vertical edges that get the dialect's finish: the boss runs on past
    # the channel's ends by that finish, so the rounding never thins the wall round the channel.
    finish = max(min(edge_size(dialect, spec.depth, p), edge), p.layer_mm) if g.up is None else 0.0
    bosses = [poly(_keyhole_footprint(g, k, p.min_wall_mm, boss=True, run_on=finish))
              for k in keys if k.front > -p.min_wall_mm]
    voids = [] if g.up is None else [f for w in elev.solid.inner_wires() for f in _printable_void(Face(w), g.up)]
    for b in bosses:
        voids = [f for v in voids for f in (v - b).faces()]
    # Lying down the voids are finished with the outline. Standing up their tent roofs keep a sharp
    # apex, so they are cut after the finish.
    if g.up is None:
        face = round_corners(elev.solid, g.d, g.edge, edge)
        if bosses:
            face = _trim(fuse([face, *bosses]), g)
        body = finish_extrusion(extrude_y(face, spec.depth), dialect, spec.depth, print_down, p, edge)
    else:
        envelope = round_corners(Face(elev.solid.outer_wire()), g.d, g.edge, edge)
        if bosses:
            envelope = _trim(fuse([envelope, *bosses]), g)  # a boss on the outer outline stays too
        body = finish_extrusion(extrude_y(envelope, spec.depth), dialect, spec.depth, print_down, p, edge)
        if voids:
            body = one(body - extrude_y(Compound(voids), spec.depth + 2))

    cut = _lattice_cut(g, elev, keepouts, print_down, edge)
    if cut is not None and cut.tool is not None:
        body = one(body - _lattice_tool(g, cut))
    for k in keys:
        body = one(body - _keyhole_tool(g, k, print_down))
    if spec.tip_hole is not None:
        body = one(body - _tip_tool(g))
    if dialect.relief_ribs:
        for path in elev.ribs:
            for run in _printable_runs(g, path):
                body = one(body + _rib_solid(g, run, g.rib_w))

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
            # The gothic eye sits back so its spear finial ends at the reach.
            eye_r = room
            arm_end = x_tip = spec.reach - room * (1 + (GOTHIC_FINIAL if d.name == "gothic" else 0.0))
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


def _trim(face, g: _Frame) -> Face:
    """Keep the part of `face` inside the bracket's box: nothing behind the wall or below z = 0."""
    box = poly([(-g.pt, 0), (g.R + 1, 0), (g.R + 1, g.H), (-g.pt, g.H)])
    faces = (face & box).clean().faces()
    if len(faces) != 1:
        raise ValueError(f"the {g.d.name} elevation is not one piece ({len(faces)} pieces)")
    return faces[0]


def _arm(g: _Frame) -> Face:
    x0 = -g.pt / 2
    return poly([(x0, g.H), (g.arm_end, g.H), (g.arm_end, g.H - g.tip_t), (x0, g.H - g.arm_t(x0))])


def _plate(g: _Frame) -> Face:
    return poly([(-g.pt, 0), (0, 0), (0, g.H), (-g.pt, g.H)])


def _eye(g: _Frame) -> list[Face]:
    """The round eye at the tip; standing up, its underside comes to a 45 degree point so it prints."""
    if g.eye_r <= 0:
        return []
    if g.up is None:
        return [disc(g.tip_at, g.eye_r)]
    n = 64
    circle = [(g.eye_r * math.cos(2 * math.pi * k / n), g.eye_r * math.sin(2 * math.pi * k / n)) for k in range(n)]
    down = (-g.up[0], -g.up[1])
    return [poly(shift(clip_roof(circle, down, ROOF_DEG), g.tip_at))]


def _printable_void(void: Face, up: Point) -> list[Face]:
    """The largest part of a void under a 45 degree tent (towards `up`), so its roof needs no support.

    Unlike an opening, a void is bounded by members: its roof is filled down to the tent instead of
    being cut up into a point. The tent's apex is tried at points around the void, the roomiest wins.
    """
    a, b = _segments(void, _XZ)
    span = float(np.ptp(np.concatenate([a, b]), axis=0).max()) * 4
    t = math.tan(math.radians(ROOF_DEG))
    ux, uz = up
    sx, sz = uz, -ux  # sideways, perpendicular to up
    best: list[Face] = []
    best_area = 0.0
    for apex in a[:: max(1, len(a) // 48)]:
        ax, az = float(apex[0]), float(apex[1])
        tent = poly([
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
    """A flying buttress under a pointed window.

    A straight strut runs from the plate's foot to the arm near its tip. Above it, against the
    plate, a pointed (two-centred, equilateral) window rises to a sharp point just under the arm,
    with a solid spandrel beside it. The arm ends in an eye with a spear finial. Nervure ribs on
    the +Y face follow the window's head, the strut and the arm's lower edge.
    """
    w = max(GOTHIC_STRUT_W * g.t0, 2 * g.p.min_wall_mm)
    x0 = -g.pt / 2
    xe = min(GOTHIC_STRUT_TO * g.R, g.arm_end - g.eye_r - 2 * w)
    s0, s1 = (x0, w / 2), (xe, g.H - g.arm_t(xe) / 2)
    strut = band(s0, s1, w)
    # The strut's upper edge, the window's floor: z on it at x.
    du, dv = s1[0] - s0[0], s1[1] - s0[1]
    slope = dv / du
    lift = w / 2 * math.hypot(du, dv) / du

    def strut_top(x: float) -> float:
        return s0[1] + slope * (x - s0[0]) + lift

    span = GOTHIC_ARCH_SPAN * g.R
    rise = span * _SQRT3 / 2
    apex_z = g.H - g.arm_t(span / 2) - GOTHIC_APEX_GAP * g.t0
    spring = apex_z - rise
    head = [(u + span / 2, v + spring) for u, v in arch("pointed", span, rise, n=32)]  # right springer -> left
    if spring < strut_top(span) + w:
        raise ValueError(f"the gothic window does not fit above the strut: make the bracket taller than {g.H:g} mm")
    window = [(span, strut_top(span)), *head, (0.0, strut_top(0.0))]
    solid = _trim(fuse([_plate(g), _arm(g), strut, _spandrel(g, s0, s1, w), *_eye(g), *_finial(g)]), g)
    solid = max((solid - poly(window)).faces(), key=lambda f: f.area)

    off = g.edge + g.rib_w / 2 + 0.3  # a rib stays clear of the edge chamfer
    hood = [(x, z) for x, z in offset_path(head, -off)]  # the window head, offset into the spandrel
    strut_rib = [(0.0 + off, strut_top(off) - lift), (xe - w, strut_top(xe - w) - lift)]
    arm_rib = [(span / 2, g.H - g.arm_t(span / 2) + off)]
    x_stop = g.arm_end - g.eye_r - g.rib_w
    while g.arm_t(x_stop) < off + g.rib_w / 2 + g.edge:
        x_stop -= 1.0
    arm_rib.append((x_stop, g.H - g.arm_t(x_stop) + off))
    return _Elevation(solid, min(g.pt, g.tip_t, w), ribs=[hood, strut_rib, arm_rib])


def _spandrel(g: _Frame, s0: Point, s1: Point, w: float) -> Face:
    """Everything above the strut, below the arm and in front of the plate (the window is cut from it)."""
    return poly([s0, s1, (s1[0], g.H - 0.5), (s0[0], g.H - 0.5)])


def _finial(g: _Frame) -> list[Face]:
    """The gothic spear finial beyond the eye: its flanks are steep enough to print standing up."""
    if g.d.name != "gothic" or g.eye_r <= 0:
        return []
    x, z = g.tip_at
    r = g.eye_r
    return [poly([(x + 0.4 * r, z + 0.8 * r), (g.R, z), (x + 0.4 * r, z - 0.8 * r)])]


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
    plate = poly([(-g.pt, 0), (0, 0), (0, g.H - g.t0 / 2), (-g.pt, g.H - g.t0 / 2)])
    solid = _trim(fuse([plate, arm, brace, *_eye(g)]), g)
    return _Elevation(solid, min(g.pt, g.tip_t, widths[-1]))


def _hitech(g: _Frame) -> _Elevation:
    bar = max(2 * g.p.min_wall_mm, HITECH_BAR * g.t0)
    node_d = HITECH_NODE * bar
    # The foot node sits on the plate face. The arm nodes sit on the arm's centre line, so the
    # diagonals run straight into the arm and their discs stay inside its outline: nothing bulges
    # below the arm, the junction is the 2D rounding's small fillet.
    arm_nodes = [(f * g.R, g.H - g.arm_t(f * g.R) / 2) for f in HITECH_NODES_AT]
    if node_d > min(g.t0, g.tip_t) - 2 * g.p.min_wall_mm:
        raise ValueError(f"hitech node {node_d:g} mm does not fit inside the {min(g.t0, g.tip_t):g} mm arm")
    nodes = [(0.0, bar)] + arm_nodes
    frame = truss(nodes, [(0, 1), (0, 2)], bar, node_d, p=g.p)
    solid = _trim(fuse([_plate(g), _arm(g), frame, *_eye(g)]), g)
    return _Elevation(solid, min(g.pt, g.tip_t, bar))


def _parametric(g: _Frame) -> _Elevation:
    """A web under a sagging spline, its whole field perforated by a graded hex lattice."""
    solid, web = _web(g, PARAM_SAG)
    return _Elevation(solid, min(g.pt, g.tip_t), web=web)


def _web(g: _Frame, sag: float, from_back: bool = False) -> tuple[Face, Face]:
    """(solid, web): plate, arm and a web under a sagging spline from the plate's foot to the arm.

    from_back starts the spline at the plate's back corner (so the foot has no step) and ends it just
    inside the arm (so it crosses the arm's underside cleanly instead of leaving a sliver).
    """
    xe = min(WEB_TO * g.R, g.arm_end - g.eye_r - 4 * g.edge)
    if from_back:
        s, e = (-g.pt, 0.0), (xe, g.H - g.arm_t(xe) + 0.5)
    else:
        s, e = (-g.pt / 2, 0.0), (xe, g.H - g.arm_t(xe))
    chord = math.hypot(e[0] - s[0], e[1] - s[1])
    under = catenary(s, e, sag * chord, n=16)
    top = g.H if from_back else g.H - 0.5  # from the back corner the fill also forms the plate's top
    fill = poly(under + [(xe, top), (s[0], top)])
    # Starting at the back corner, the fill already holds the plate; a plate rectangle would stick out
    # below the spline at the plate's front foot.
    parts = [_arm(g), fill, *_eye(g)] if from_back else [_plate(g), _arm(g), fill, *_eye(g)]
    solid = _trim(fuse(parts), g)
    web = max((fill - _arm(g) - _plate(g)).faces(), key=lambda f: f.area)
    return solid, web


def _biomech(g: _Frame) -> _Elevation:
    """A web filled with the organic cell lattice: irregular rounded cells, finest at the plate-arm corner.

    The whole silhouette speaks the same language: every corner is rounded in 2D, the bends where the
    web meets the arm with BIO_BEND x root_t, the outer corners with BIO_OUTER x root_t. Only the wall
    face stays flat: its two corners take at most the keyholes' margin, so the keyholes sit on flat.
    """
    solid, web = _web(g, BIO_SAG, from_back=True)
    # The keyholes keep 4 x min_wall from the plate's ends. Standing on the wall face the corners
    # at the bed would hang if rounded: they keep the bed chamfer instead.
    wall_r = 4 * g.p.min_wall_mm * 0.8 if g.up is None else 0.0

    def radius(pos: Vector, convex: bool) -> float:
        if not convex:
            return BIO_BEND * g.t0
        return wall_r if pos.X < -g.pt + 0.1 else BIO_OUTER * g.t0

    solid = round_corners(solid, g.d, g.edge, 0.0, radius=radius)
    return _Elevation(solid, min(g.pt, g.tip_t), web=web)


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


def _keyhole_footprint(g: _Frame, k: _Keyhole, grow: float, boss: bool = False, run_on: float = 0.0) -> list[Point]:
    """The keyhole's outline in the elevation (x, z), grown by `grow`; with boss, the pad round its
    channel, which runs on `run_on` further past the channel's ends (room for its corner finish)."""
    x1 = max(k.front, 0.0) + grow if boss else k.front + grow
    x0 = -g.pt / 2 if boss else -g.pt
    lo, hi = k.z_lo - grow - run_on, k.z_hi + grow + run_on
    return [(x0, lo), (x1, lo), (x1, hi), (x0, hi)]


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
        tool = tool + extrude(cap_face(2 * k.head_r, up, plane), amount=reach)
        tool = tool + _lip_ramp(g, k, up, z_entry, slot_len)
    return tool


def _lip_ramp(g: _Frame, k: _Keyhole, up: Point, z_entry: float, slot_len: float) -> Solid:
    """Lying down, the lip over the slot gets a 46 degree underside instead of a flat ceiling.

    The lip holds the head against the plate. Seen along the slot, its underside climbs from the
    slot's edge at the head's face (x = -plate_t + back) towards the wall face at a slope steeper
    than 45 degrees, so it prints as a roof. The head still bears on the full lip at the channel.
    """
    sign = 1.0 if up[0] > 0 else -1.0  # +Y up: the lip over +Y; -Y up: over -Y
    x_face = -g.pt + k.back
    x_wall = -g.pt - 1
    t = math.tan(math.radians(ROOF_DEG))
    rise = (x_face - x_wall) * t
    y_slot = sign * k.slot_w / 2
    tri = [
        Vector(x_face + 0.01, y_slot, z_entry),
        Vector(x_wall, y_slot, z_entry),
        Vector(x_wall, y_slot + sign * rise, z_entry),
    ]
    return Solid.extrude(Face(Wire.make_polygon(tri, close=True)), Vector(0, 0, slot_len))


# --- lattices and relief ----------------------------------------------------------------------------


def _lattice_cut(g: _Frame, elev: _Elevation, keepouts: list[Face], print_down: str, edge: float) -> LatticeCut | None:
    """The dialect's lattice: parametric's graded hex field in the web, hitech's triangle pockets on the arm."""
    if g.d.name in ("parametric", "biomech"):
        organic = g.d.name == "biomech"
        border = (BIO_BORDER if organic else PARAM_BORDER) * g.p.min_wall_mm
        cell = (BIO_CELL if organic else PARAM_HEX_CELL) * g.p.min_wall_mm
        # The field follows the web's outline: the web inset by a solid border.
        region = max(offset(elev.web, -border, kind=Kind.ARC).faces(), key=lambda f: f.area)
        plane = Plane(region)
        field = _corner_field(g, region, plane, cell)
        up = in_plane_up(plane, print_down)
        if organic:
            return lattice(
                region, g.p, kind="organic", cell=cell, bar_max=BIO_BAR_MAX * g.p.min_wall_mm,
                field=field, keepout=keepouts, up=up, seed=BIO_SEED,
            )
        return lattice(
            region, g.p, kind="hex", cell=cell, bar_max=PARAM_BAR_MAX * g.p.min_wall_mm,
            field=field, keepout=keepouts, up=up,
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


def _corner_field(g: _Frame, region: Face, plane: Plane, cell: float):
    """field(x, y, z): 1 nearest the plate-arm corner, where the bending peaks, 0 at the far end of the region."""
    return point_field(region, plane, (0.0, g.H - g.t0), cell)


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
    return extrude_y(cut.tool, g.spec.depth + 2)


def _rib_solid(g: _Frame, path: list[Point], width: float) -> Solid:
    """A relief rib on the +Y face along an (x, z) path.

    Standing up (the +Y face is then a wall) both ends are cut back at a slope a little steeper than
    45 degrees, so no end is a flat shelf hanging out of the wall.
    """
    h = RIB_HEIGHT_LAYERS * g.p.layer_mm
    solid = rib([(u, -v) for u, v in path], width, h, _side_plane(g), p=g.p)
    if g.up is None:
        return solid
    for end, before in ((path[0], path[1]), (path[-1], path[-2])):
        solid = one(solid - _ramp_cutter(g, end, before, width, h))
    return solid


def _ramp_cutter(g: _Frame, end: Point, before: Point, width: float, h: float) -> Solid:
    """A wedge that trims a rib's end to a slope rising from the wall at the end over RIB_RAMP x h."""
    d = np.array([end[0] - before[0], end[1] - before[1]])
    d /= np.linalg.norm(d)
    side = np.array([-d[1], d[0]])
    y0 = g.spec.depth / 2
    run = RIB_RAMP * h

    def at(along: float, lift: float, across: float) -> Vector:
        x, z = np.array(end) + d * along + side * across
        return Vector(float(x), y0 + lift, float(z))

    a = width / 2 + 1
    tri = [at(1.0, -1.0 / RIB_RAMP, -a), at(-run, h, -a), at(1.0, h + 1, -a)]
    face = Face(Wire.make_polygon(tri, close=True))
    return Solid.extrude(face, Vector(float(side[0]), 0, float(side[1])) * (2 * a))


def _printable_runs(g: _Frame, path: list[Point]) -> list[list[Point]]:
    """The parts of a rib path that stand steep enough to print when the +Y face is a wall.

    Lying down every rib prints on top and the whole path is one run.
    """
    if g.up is None:
        return [path]
    runs, cur = [], [path[0]]
    for a, b in zip(path, path[1:]):
        d = np.array(b) - np.array(a)
        up = np.array(g.up)
        steep = abs(float(d @ np.array([up[1], -up[0]]))) <= _RIB_MAX_SLOPE * float(np.linalg.norm(d))
        if steep:
            cur.append(b)
        else:
            if len(cur) >= 2:
                runs.append(cur)
            cur = [b]
    if len(cur) >= 2:
        runs.append(cur)
    return [r for r in runs if math.dist(r[0], r[-1]) > 3 * RIB_RAMP * RIB_HEIGHT_LAYERS * g.p.layer_mm]


# --- shared tools -----------------------------------------------------------------------------------


def _tip_tool(g: _Frame):
    x, z = g.tip_at
    d = g.spec.depth
    hole = Pos(x, -(d / 2 + 1), z) * Rot(90, 0, 0) * fasteners.clearance_hole(g.spec.tip_hole, d + 2, g.p)
    if g.up is None:
        return hole
    cap = cap_face(_hole_d(g.spec.tip_hole, g.p), g.up, Plane(origin=(x, 0, z), x_dir=(1, 0, 0), z_dir=(0, -1, 0)))
    return hole + extrude_y(cap, d + 2)
