"""Hanger kit: a ceiling mount bar and two arms with cradles for a long object, joined by dovetails.

Frame: the ceiling is z = 0, the mount bar is centred on x = 0 (z from -mount_h to 0) and is screwed
up into the ceiling. Arm A runs to -X, arm B to +X. The object lies along X with its end faces at
x = +-span/2 and its bottom at z = -drop; each arm ends in a cradle round its end of the object.
The depth runs along Y centred on y = 0.

Every piece is an elevation in Plane.XZ extruded along Y and prints lying on its -Y face
(print_down "-y"): the styling is all through-cuts and outline, which print without support, and
the load acts in the layer plane. The dovetails slide along Y, which is vertical in print. A tenon
stands on the bed with its piece, so the piece holding the socket carries the closed end and the
stop wall below the tenon's bed face: a socket piece (the mount, even arm segments) is
`slide_fit + joint.stop` deeper on its -Y side. An arm slides into the mount from +Y.

The cradle pocket fits the end profile plus `p.slide_fit_mm` per side, centred on y = 0. It is open
on top and on +Y: a wall on +Y would be a roof over the pocket in print, so the closed wall is the
one on -Y, lying on the bed. The object is lowered in from above or slid in from +Y onto that wall.

Arms longer than the bed are cut perpendicular to their centreline into equal segments, each cut a
dovetail sitting in a solid joint band across the arm. Odd segments carry tenons, even ones sockets.

Rules of thumb (part 1 has no load calculation): the hub is 1.5 x arm_t long, the cradle floor half
of arm_t, the end wall one arm_t; nothing of the arm comes inward of the end wall below the
object's top plus one more object height (room to lift the end in).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from types import MappingProxyType
from typing import Literal

import numpy as np
from build123d import Box, Compound, Cylinder, Face, Kind, Plane, Pos, Rot, Solid, mirror, offset

from cadlib import fasteners
from cadlib.config import Profile
from cadlib.style.archetypes.elevation import (
    RIB_HEIGHT_LAYERS, RIB_WIDTH_WALLS, THIN_EDGE, band, cap_face, extrude_y, fuse, offset_path, one, point_field,
    poly, round_corners,
)
from cadlib.style.archetypes.types import Kit, Load, Piece, Support, Tunable
from cadlib.style.dialects import Dialect, edge_size, finish_extrusion, get_dialect
from cadlib.style.joints import DovetailSpec, dovetail
from cadlib.style.lattice import _inside, _segments, lattice
from cadlib.style.log import StyleNote, drain, note
from cadlib.style.members import catenary, curved_beam, rib, truss
from cadlib.style.outline import Point, arch, to_face

PRINT_DOWN = "-y"
ALLOWED_PRINT_DOWN = ("-y",)

# Archetype ratios (dimensionless, see the module docstring).
HUB_L = 1.5               # hub length along X / arm_t
FLOOR_T = 0.5             # cradle floor / arm_t
END_WALL = 1.0            # cradle end wall (the foot of the post) / arm_t
LIFT = 1.0                # free room above the object's top / its height (at least 2 x arm_t)
SCREW_RECESS = 1 / 3      # the screw head sits this share of mount_h up from the room face
JOINT_GAP = 2.0           # solid round a segment joint's socket / min_wall
GOTHIC_W = 1.25           # rail, strut and post width / arm_t (and room for a nervure rib on top)
GOTHIC_LANCETS = 4        # lancet windows in the spandrel, from the post towards the hub
GOTHIC_LANCET_RISE = 1.4  # lancet head rise / span (taller than equilateral: a sharp lancet point)
GOTHIC_FINIAL = 1.5       # pendant finial under the cradle / post width
GOTHIC_PENDANT = 0.45     # mount pendant span / gap between screws
GAUDI_ROOT = 1.0          # sweep width at the hub / mount_h
GAUDI_SAG = 0.1           # inner catenary brace sag / chord
GAUDI_BRACE = (1.1, 0.7)  # brace width at the hub and at the post / arm_t
GAUDI_BELLY = 0.3         # mount underside sag / mount_h
HITECH_BAR = 0.4          # truss diagonal / arm_t (floored at 2 x min_wall)
HITECH_PANEL = 2.0        # truss panel length / truss height at the hub
HITECH_TRI_CELL = 6.0     # mount pocket triangle side / min_wall
HITECH_POCKET = 1 / 3     # mount pocket depth / depth
WEB_HOG = 0.15            # web underside rises this share of its chord above it
PARAM_HEX_CELL = 6.5      # hex pitch / min_wall
PARAM_BAR_MAX = 4.0       # thickest hex bar (at the hub) / min_wall
PARAM_BELLY = 0.2         # mount underside sag / mount_h
BIO_SAG = 0.12            # biomech web underside sags this share of its chord below it
BIO_CELL = 8.0            # smallest organic cell / min_wall (larger than the cantilever's: a web four times the area)
BIO_BAR_MAX = 3.0         # thickest organic bar / min_wall
BIO_MOUNT_CELL = 5.0      # smallest organic cell in the mount / min_wall (the cantilever's: the arm web's would not fit)
BIO_SEED = 0              # organic lattice seed: the same seed, the same kit
BIO_BEND = 1.5            # rounding where members meet / arm_t
BIO_OUTER = 0.8           # rounding of outer corners / arm_t
BIO_BELLY = 0.35          # mount underside sag / mount_h
WEB_BORDER = 2.0          # solid rim round a lattice field / min_wall
RIB_BAND_GAP = 0.5        # a relief rib stops this far (/ min_wall) beyond half its width from a joint band

_SQRT3 = math.sqrt(3.0)
_BIG = 1e4


@dataclass(frozen=True)
class EndProfile:
    """Cross-section of one end of the object in YZ: a rectangle, or a trapezoid `width` wide on top and `narrow` at the bottom."""

    kind: Literal["rect", "trapezoid"]
    width: float
    height: float
    narrow: float | None = None


@dataclass(frozen=True)
class HangerSpec:
    span: float                 # between the object's end faces, mm
    end_a: EndProfile           # the end at -X
    end_b: EndProfile           # the end at +X
    drop: float                 # from the ceiling down to the object's bottom, mm
    mount_len: float = 70.0     # mount bar length along X, mm
    mount_h: float = 18.0       # mount bar height (and arm hub height), mm
    depth: float = 38.0         # extrusion depth along Y, mm
    arm_t: float = 8.0          # arm member width in the elevation, mm
    cradle_len: float = 20.0    # how far the object's end lies in its cradle along X, mm
    screw: str = "3"            # countersunk wood screw diameter, mm (cadlib.fasteners.wood_screw_countersunk_hole)
    screw_count: int = 2
    joint: DovetailSpec | None = None  # None: the defaults with length = depth
    load_n: float = 15.0        # weight of the object, N


def hanger_kit(style: str, spec: HangerSpec, p: Profile) -> Kit:
    """The mount, arm A and arm B (or their segments) in the given dialect; see the module docstring.

    Built once per (style, spec, p) and cached; the kit's pieces are read-only. Every call logs the
    style notes of all pieces again. A model that builds one piece calls hanger_piece instead, so
    its build report gets that piece's notes only.
    """
    kit, notes = _build(style, spec, p)
    for name in kit.pieces:
        _replay(notes[name])
    return kit


def hanger_piece(style: str, spec: HangerSpec, p: Profile, name: str) -> Piece:
    """One piece of the (cached) kit, logging the style notes its build left."""
    kit, notes = _build(style, spec, p)
    if name not in kit.pieces:
        raise ValueError(f"no piece {name!r} in this kit, there are: {', '.join(kit.pieces)}")
    _replay(notes[name])
    return kit.pieces[name]


def _replay(notes: tuple[StyleNote, ...]) -> None:
    for n in notes:
        note(n.tool, n.message, n.level)


@lru_cache(maxsize=16)
def _build(style: str, spec: HangerSpec, p: Profile) -> tuple[Kit, dict[str, tuple[StyleNote, ...]]]:
    """(kit, notes per piece): the style notes are captured while each piece is built.

    A note on the arms' shared body belongs to every arm piece. The caller's own notes logged
    before the build are put back untouched.
    """
    earlier = drain()
    try:
        dialect = get_dialect(style)
        joint = spec.joint or DovetailSpec(length=spec.depth)
        _validate(spec, joint, p)
        deep = p.slide_fit_mm + joint.stop  # a socket piece reaches this much further down on -Y
        pieces = {"mount": Piece(_mount(spec, joint, dialect, p, deep), PRINT_DOWN, ALLOWED_PRINT_DOWN)}
        notes = {"mount": tuple(drain())}
        g = _frame(spec, joint, dialect, p)
        # Both arms share one elevation (built for the taller end) and differ only in the cradle pocket.
        arms = _arms(g, deep, [spec.end_a, spec.end_b])
        arm_notes = tuple(drain())
        for side, segments in zip("ab", arms):
            if side == "a":
                segments = [mirror(s, about=Plane.YZ) for s in segments]
            names = [f"arm-{side}"] if len(segments) == 1 else [f"arm-{side}-{k}" for k in range(1, len(segments) + 1)]
            for name, solid in zip(names, segments):
                pieces[name] = Piece(solid, PRINT_DOWN, ALLOWED_PRINT_DOWN)
                notes[name] = arm_notes
    finally:
        drain()
        _replay(tuple(earlier))
    x_load = spec.span / 2 - spec.cradle_len / 2
    kit = Kit(
        pieces=MappingProxyType(pieces),
        supports=[Support((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))],
        loads=[Load((s * x_load, 0.0, -spec.drop), (0, 0, -spec.load_n / 2)) for s in (-1, 1)],
        tunables={
            "arm_t": Tunable("arm_t", spec.arm_t, 2 * p.min_wall_mm, spec.mount_h),
            "depth": Tunable("depth", spec.depth, _min_depth(spec, p), 80.0),
            "mount_h": Tunable("mount_h", spec.mount_h, joint.wide + 4 * p.min_wall_mm, 40.0),
        },
    )
    return kit, notes


# --- sizes --------------------------------------------------------------------------------------


def _min_depth(spec: HangerSpec, p: Profile) -> float:
    """The pocket plus a -Y wall of two min_walls on each side (the pocket is centred)."""
    return max(spec.end_a.width, spec.end_b.width) + 2 * p.slide_fit_mm + 4 * p.min_wall_mm


def _validate(spec: HangerSpec, joint: DovetailSpec, p: Profile) -> None:
    for name, end in (("end_a", spec.end_a), ("end_b", spec.end_b)):
        if end.kind not in ("rect", "trapezoid"):
            raise ValueError(f"{name}: unknown end profile {end.kind!r}, there are: rect, trapezoid")
        if end.kind == "trapezoid" and (end.narrow is None or not 0 < end.narrow < end.width):
            raise ValueError(f"{name}: a trapezoid needs 0 < narrow < width")
        if end.width <= 0 or end.height <= 0:
            raise ValueError(f"{name}: width and height must be positive")
    if spec.depth < _min_depth(spec, p):
        raise ValueError(f"depth {spec.depth:g} mm leaves no 2 x min_wall wall beside a cradle pocket: make it at least {_min_depth(spec, p):g} mm")
    if spec.arm_t < 2 * p.min_wall_mm:
        raise ValueError(f"arm_t {spec.arm_t:g} mm is below 2 x min_wall = {2 * p.min_wall_mm:g} mm")
    if spec.mount_h < joint.wide + 4 * p.min_wall_mm:
        raise ValueError(f"mount_h {spec.mount_h:g} mm leaves no 2 x min_wall round the {joint.wide:g} mm dovetail")
    if joint.length != spec.depth:
        raise ValueError(f"the dovetail runs the whole depth: joint.length {joint.length:g} must equal depth {spec.depth:g}")
    if spec.screw_count < 1:
        raise ValueError("the mount needs at least one screw")
    if spec.cradle_len < 2 * p.min_wall_mm:
        raise ValueError(f"cradle_len {spec.cradle_len:g} mm is too short")
    h = max(spec.end_a.height, spec.end_b.height)
    need = spec.mount_h + 3 * spec.arm_t + h + max(h, 2 * spec.arm_t)
    if spec.drop < need:
        raise ValueError(f"drop {spec.drop:g} mm leaves no room for the arms: at least {need:.0f} mm")
    if spec.span / 2 - spec.cradle_len < spec.mount_len / 2 + 3 * spec.arm_t:
        raise ValueError(f"span {spec.span:g} mm is too short for a {spec.mount_len:g} mm mount and {spec.cradle_len:g} mm cradles")
    _screw_xs(spec, joint, p)  # raises when the screws do not fit


def _screw_d(spec: HangerSpec) -> float:
    return float(spec.screw)


def _head_d(spec: HangerSpec, p: Profile) -> float:
    d = _screw_d(spec)
    if d not in fasteners.WOOD_SCREW_HEAD:
        raise ValueError(f"wood screw {spec.screw} mm isn't described, there are: {', '.join(f'{k:g}' for k in fasteners.WOOD_SCREW_HEAD)}")
    return fasteners.WOOD_SCREW_HEAD[d] + p.hole_clearance_mm


def _screw_xs(spec: HangerSpec, joint: DovetailSpec, p: Profile) -> list[float]:
    """Screw positions along the mount: spread between the sockets, a wall clear of each."""
    head_r = _head_d(spec, p) / 2
    a = spec.mount_len / 2 - joint.depth - p.slide_fit_mm - 2 * p.min_wall_mm - head_r
    n = spec.screw_count
    if a < 0 or (n > 1 and 2 * a / (n - 1) < 2 * head_r + 2 * p.min_wall_mm):
        raise ValueError(f"no room for {n} screws between the dovetail sockets of a {spec.mount_len:g} mm mount")
    return [0.0] if n == 1 else [float(x) for x in np.linspace(-a, a, n)]


@dataclass(frozen=True)
class _Frame:
    """Sizes of one arm in its canonical frame: running to +X (arm A is built so and mirrored)."""

    spec: HangerSpec
    joint: DovetailSpec
    d: Dialect
    p: Profile
    edge: float
    x_h0: float            # hub's mating face (against the mount's end)
    x_h1: float            # hub's outer face
    x_e: float             # the object's end face
    x_p0: float            # end wall / post inner face
    x_p1: float            # post outer face
    z_b: float             # the object's bottom = the cradle floor's top
    z_f: float             # the cradle floor's underside
    z_wall: float          # top of the cradle's -Y wall (the taller end's top)
    z_clear: float         # inward of the post nothing of the arm comes below this
    z_pt: float            # where the members meet the post (their underside is above z_clear)

    @property
    def t(self) -> float:
        return self.spec.arm_t

    @property
    def H(self) -> float:
        return self.spec.mount_h

    @property
    def x_pc(self) -> float:
        return (self.x_p0 + self.x_p1) / 2

    @property
    def hub_c(self) -> Point:
        return (self.x_h0, -self.H / 2)

    @property
    def rib_w(self) -> float:
        return RIB_WIDTH_WALLS * self.p.min_wall_mm


def _frame(spec: HangerSpec, joint: DovetailSpec, d: Dialect, p: Profile) -> _Frame:
    t = spec.arm_t
    h_clear = max(spec.end_a.height, spec.end_b.height)
    x_e = spec.span / 2
    x_p0 = x_e + p.slide_fit_mm
    z_b = -spec.drop
    z_clear = z_b + h_clear + max(LIFT * h_clear, 2 * t)
    return _Frame(
        spec=spec, joint=joint, d=d, p=p, edge=edge_size(d, spec.depth, p),
        x_h0=spec.mount_len / 2, x_h1=spec.mount_len / 2 + HUB_L * t,
        x_e=x_e, x_p0=x_p0, x_p1=x_p0 + END_WALL * t * (GOTHIC_W if d.name == "gothic" else 1.0),
        z_b=z_b, z_f=z_b - max(FLOOR_T * t, 2 * p.min_wall_mm), z_wall=z_b + h_clear + p.slide_fit_mm,
        z_clear=z_clear, z_pt=z_clear + t,
    )


# --- arm elevations -------------------------------------------------------------------------------


@dataclass
class _Elevation:
    solid: Face                      # the elevation with its inherent voids
    thin: float                      # the thinnest member: edge finishes stay below half of it
    centre: list[Point]              # centreline from the hub to the cradle; segment cuts are square to it
    web: Face | None = None          # the region a web lattice fills
    ribs: list[list[Point]] = field(default_factory=list)  # relief rib paths on the +Y face
    keep_sharp: list[Point] = field(default_factory=list)  # corners the 2D rounding leaves alone


def _hub(g: _Frame) -> Face:
    return poly([(g.x_h0, -g.H), (g.x_h1, -g.H), (g.x_h1, 0.0), (g.x_h0, 0.0)])


def _cradle(g: _Frame, post_top: float) -> list[Face]:
    """The post from post_top down to the floor, the floor under the pocket and the block of the -Y wall."""
    post = poly([(g.x_p0, g.z_f), (g.x_p1, g.z_f), (g.x_p1, post_top), (g.x_p0, post_top)])
    block = poly([(g.x_e - g.spec.cradle_len, g.z_f), (g.x_p0 + 0.5, g.z_f), (g.x_p0 + 0.5, g.z_wall), (g.x_e - g.spec.cradle_len, g.z_wall)])
    return [post, block]


def _hog(p0: Point, p1: Point, rise: float, n: int = 16) -> list[Point]:
    """A catenary from p0 to p1 bulging `rise` above the chord at its middle (the mirror of a hanging one)."""
    pts = catenary(p0, p1, rise, n)
    du, dv = p1[0] - p0[0], p1[1] - p0[1]
    return [(x, 2 * (p0[1] + dv * (x - p0[0]) / du) - z) for x, z in pts]


def _gothic(g: _Frame) -> _Elevation:
    """A triangle frame (ceiling rail, strut, post) whose spandrel is an arcade of pointed lancet windows.

    The lancets stand on the strut, their points under the rail, shorter towards the hub. Nervure
    ribs run along the rail, the strut, the post and over each window head; a pendant finial hangs
    under the cradle.
    """
    w = max(GOTHIC_W * g.t, 2 * (g.edge + g.rib_w / 2 + 0.3))
    rail = poly([(g.x_h0, -w), (g.x_p1, -w), (g.x_p1, 0.0), (g.x_h0, 0.0)])
    s0, s1 = g.hub_c, (g.x_pc, g.z_pt)
    strut = band(s0, s1, w)  # ends on the post's centre line, its cap inside the post
    du, dv = s1[0] - s0[0], s1[1] - s0[1]
    lift = w / 2 * math.hypot(du, dv) / du

    def strut_top(x: float) -> float:
        return s0[1] + dv / du * (x - s0[0]) + lift

    spandrel = poly([(g.x_h1, -w / 2), (g.x_p0 + 0.5, -w / 2), (g.x_p0 + 0.5, strut_top(g.x_p0) - 0.5), (g.x_h1, strut_top(g.x_h1) - 0.5)])
    finial = poly([(g.x_p0, g.z_f + 0.5), (g.x_p1, g.z_f + 0.5), (g.x_pc, g.z_f - GOTHIC_FINIAL * (g.x_p1 - g.x_p0))])
    solid = fuse([_hub(g), rail, strut, spandrel, *_cradle(g, 0.0), finial])
    faces = solid.clean().faces()
    solid = max(faces, key=lambda f: f.area)

    off = g.edge + g.rib_w / 2 + 0.3  # a rib stays clear of the edge chamfer
    pier = 2 * (off + g.rib_w / 2)
    x_lo, x_hi = g.x_h1 + pier, g.x_p0 - pier
    span = (x_hi - x_lo - (GOTHIC_LANCETS - 1) * pier) / GOTHIC_LANCETS
    apex = -w - 2 * off
    ribs = [[(g.x_h1, -w / 2), (g.x_p0 - off, -w / 2)], [(g.x_pc, -w - off), (g.x_pc, g.z_clear)]]
    kept = 0
    for i in range(GOTHIC_LANCETS):
        # The heads line up under the rail; towards the hub the strut rises, so a lancet that has
        # no room for its full height gets lower and narrower (down to an equilateral head).
        slot0 = x_hi - i * (span + pier) - span
        room = apex - strut_top(slot0) - pier / 2
        width = min(span, room / (_SQRT3 / 2))
        if width < 4 * g.p.min_wall_mm:
            continue
        x0 = slot0 + (span - width) / 2
        x1 = x0 + width
        head_rise = min(GOTHIC_LANCET_RISE * width, room)
        spring = apex - head_rise
        head = [(u + (x0 + x1) / 2, v + spring) for u, v in arch("pointed", width, head_rise, n=32)]
        window = [(x1, strut_top(x1)), *head, (x0, strut_top(x0))]
        solid = max((solid - poly(window)).faces(), key=lambda f: f.area)
        ribs.append(offset_path(head, -off))
        kept += 1
    if kept < GOTHIC_LANCETS:
        note("hanger", f"gothic: {GOTHIC_LANCETS - kept} of {GOTHIC_LANCETS} lancets too small for the spandrel, left solid", "info")
    ribs.append([(g.x_h1 + off, strut_top(g.x_h1 + off) - lift), (g.x_p0 - w, strut_top(g.x_p0 - w) - lift)])
    return _Elevation(solid, min(w, pier), centre=[g.hub_c, (g.x_pc, g.z_pt), (g.x_pc, g.z_b)], ribs=ribs)


def _gaudi(g: _Frame) -> _Elevation:
    """One sweep from the hub curving down into the post, and a hanging catenary brace under it.

    The sweep is a quarter ellipse, as wide as the hub where it leaves it, tapering by the dialect's
    ratio; the brace and the sweep frame one large organic opening. Everything is softly rounded.
    """
    # The sweep starts at the mating face as wide as the hub: it is the hub (a separate hub block
    # would leave slivers along the sweep's spline edges). A straight millimetre at each end makes
    # the end caps exactly square: flat against the mount and flush with the post.
    a = g.x_pc - g.x_h0
    b = -g.H / 2 - g.z_pt
    n = 24
    arc = [(g.x_h0 + a * math.sin(math.pi / 2 * k / n), g.z_pt + b * math.cos(math.pi / 2 * k / n)) for k in range(n + 1)]
    path = [arc[0], (g.x_h0 + 1.0, arc[0][1]), *arc[1:], (g.x_pc, g.z_pt - 1.0)]
    w0 = GAUDI_ROOT * g.H
    w1 = g.x_p1 - g.x_p0
    widths = [w0, *np.linspace(w0, max(g.d.taper * w0, w1), n + 1), w1]
    sweep = curved_beam(path, widths, p=g.p)
    if sweep.normal_at().Y < 0:
        sweep = -sweep
    bw0, bw1 = (max(r * g.t, 2 * g.p.min_wall_mm) for r in GAUDI_BRACE)
    s, e = (g.x_h1 - bw0 / 2, -g.H + bw0 / 2), (g.x_p0 + bw1 / 2, g.z_pt)
    chord = math.hypot(e[0] - s[0], e[1] - s[1])
    centre = catenary(s, e, GAUDI_SAG * chord, n=16)
    brace = curved_beam(centre, list(np.linspace(bw0, bw1, len(centre))), p=g.p)
    if brace.normal_at().Y < 0:
        brace = -brace
    solid = fuse([sweep, brace, *_cradle(g, g.z_pt - 1.0)])
    solid = max(solid.clean().faces(), key=lambda f: f.area)
    return _Elevation(solid, min(w1, bw1), centre=[*path, (g.x_pc, g.z_b)], keep_sharp=_hub_face(g))


def _hitech(g: _Frame) -> _Elevation:
    """A triangulated truss: a chord along the ceiling, a lower chord to the post, Warren diagonals between."""
    t = g.t
    bar = max(2 * g.p.min_wall_mm, HITECH_BAR * t)
    top = poly([(g.x_h0, -t), (g.x_p1, -t), (g.x_p1, 0.0), (g.x_h0, 0.0)])
    s0, s1 = g.hub_c, (g.x_pc, g.z_pt)
    chord = band(s0, s1, t)  # ends on the post's centre line, its cap inside the post
    # Panel points: on the top chord's centre line and on the lower chord's, alternating.
    x0, x1 = g.x_h1, g.x_p0 - t / 2
    panels = max(2, round((x1 - x0) / (HITECH_PANEL * g.H)))
    xs = np.linspace(x0, x1, 2 * panels + 1)
    slope = (s1[1] - s0[1]) / (s1[0] - s0[0])
    nodes = [(float(x), -t / 2 if k % 2 == 0 else s0[1] + slope * (float(x) - s0[0])) for k, x in enumerate(xs)]
    frame = truss(nodes, [(k, k + 1) for k in range(len(nodes) - 1)], bar, bar, p=g.p)
    solid = fuse([_hub(g), top, chord, frame, *_cradle(g, 0.0)])
    solid = max(solid.clean().faces(), key=lambda f: f.area)
    return _Elevation(solid, bar, centre=[g.hub_c, (g.x_pc, g.z_pt), (g.x_pc, g.z_b)], keep_sharp=_hub_face(g))


def _web(g: _Frame, bow: float, outer_curve: bool) -> tuple[Face, Face, list[Point]]:
    """(solid, web, centre): hub, post and a web from the ceiling down to a curved underside.

    The underside rises `bow` x its chord above the chord (a concave web), or sags below it when
    `bow` is negative (a full, bellied web). outer_curve sweeps the outer contour from the hub's top
    down to the post in a quarter ellipse instead of the square ceiling corner.
    """
    s, e = (g.x_h1, -g.H), (g.x_p0, g.z_pt)
    chord = math.hypot(e[0] - s[0], e[1] - s[1])
    under = _hog(s, e, bow * chord) if bow > 0 else catenary(s, e, -bow * chord, n=16)
    if outer_curve:
        a, b = g.x_p1 - g.x_h1, -g.z_pt
        n = 24
        top = [(g.x_h1 + a * math.sin(math.pi / 2 * k / n), g.z_pt + b * math.cos(math.pi / 2 * k / n)) for k in range(n + 1)]
    else:
        top = [(g.x_h1, 0.0), (g.x_p1, 0.0), (g.x_p1, g.z_pt)]
    fill = poly([*top, *reversed(under)])
    solid = fuse([_hub(g), fill, *_cradle(g, g.z_pt + g.t)])
    solid = max(solid.clean().faces(), key=lambda f: f.area)
    border = WEB_BORDER * g.p.min_wall_mm
    web = fill - _hub(g) - poly([(g.x_p0 - border, g.z_f), (g.x_p1 + 1, g.z_f), (g.x_p1 + 1, g.z_pt + 2 * g.t), (g.x_p0 - border, g.z_pt + 2 * g.t)])
    web = max(web.faces(), key=lambda f: f.area)
    half = max(g.H, g.joint.wide + 2 * JOINT_GAP * g.p.min_wall_mm) / 2
    centre = [g.hub_c, *offset_path(under, half + border)[1:-1], (g.x_pc, g.z_pt), (g.x_pc, g.z_b)]
    return solid, web, centre


def _parametric(g: _Frame) -> _Elevation:
    """A web under the ceiling with a rising spline underside, perforated by a hex lattice graded from the hub."""
    solid, web, centre = _web(g, WEB_HOG, outer_curve=False)
    return _Elevation(solid, g.t, centre=centre, web=web, keep_sharp=_hub_face(g))


def _biomech(g: _Frame) -> _Elevation:
    """A web whose outer contour sweeps from the hub down into the post, an organic cell lattice inside.

    Every corner but the hub's mating face is rounded: the bends with BIO_BEND x arm_t, the outer
    corners with BIO_OUTER x arm_t.
    """
    solid, web, centre = _web(g, -BIO_SAG, outer_curve=True)
    return _Elevation(solid, g.t, centre=centre, web=web, keep_sharp=_hub_face(g))


def _hub_face(g: _Frame) -> list[Point]:
    return [(g.x_h0, 0.0), (g.x_h0, -g.H)]


_BUILDERS = {"gothic": _gothic, "gaudi": _gaudi, "hitech": _hitech, "parametric": _parametric, "biomech": _biomech}


# --- the arm, its segments and joints ---------------------------------------------------------------


@dataclass(frozen=True)
class _Cut:
    at: Point
    d: Point   # unit direction of the centreline there, from the hub towards the cradle


def _arms(g: _Frame, deep: float, ends: list[EndProfile]) -> list[list[Solid]]:
    """For each end, the arm's pieces in the canonical frame, from the hub out: [arm] or [segment 1, ...]."""
    elev = _BUILDERS[g.d.name](g)
    _check_clearance(g, elev.solid)
    cuts = _cuts(g, elev)
    face, bands = _with_bands(g, elev.solid, cuts)
    face = _round(g, face, elev.keep_sharp)

    edge = min(g.edge, THIN_EDGE * elev.thin)
    if edge < g.edge:
        note("hanger", f"{g.d.name}: edge {g.edge:.1f} mm shrunk to {edge:.1f} mm, thinnest member {elev.thin:.1f} mm", "info")
    tool = _lattice_tool(g, elev, bands)
    depth = g.spec.depth
    bodies: dict[float, Solid] = {}

    def body(y0: float) -> Solid:
        """The finished arm over y0 <= y <= depth / 2, without its pocket."""
        if y0 in bodies:
            return bodies[y0]
        solid = finish_extrusion(extrude_y(face, depth / 2 - y0, y0), g.d, depth, PRINT_DOWN, g.p, edge)
        if tool is not None:
            solid = one(solid - extrude_y(tool, depth + 2 * deep + 2, y0 - 1), "the arm")
        if g.d.relief_ribs and elev.ribs:
            runs = [run for path in elev.ribs for run in _rib_runs(g, path, bands)]
            if runs:
                solid = one(solid + fuse([_rib_solid(g, run) for run in runs]), "the arm")
        bodies[y0] = solid
        return solid

    joints = _joints(g, cuts)
    pad = g.edge + 0.5
    arms = []
    for end in ends:
        pieces = []
        for k in range(len(cuts) + 1):
            what = "the arm" if not cuts else f"arm segment {k + 1}"
            socket_piece = k % 2 == 1  # segments 2, 4, ... hold the sockets
            y0 = -depth / 2 - (deep if socket_piece else 0.0)
            solid = body(y0)
            if k == len(cuts):
                solid = one(solid - _pocket(g, end), what)
            if cuts:
                solid = one(solid & extrude_y(poly(_region(cuts, k)), 4 * depth, -2 * depth), what)
            for jt in joints[k : k + 2]:
                if socket_piece:
                    solid = one(solid - _socket_tool(g.joint, g.p, jt), what)
                else:
                    solid = one(solid + _tenon(g.joint, g.p, jt, pad), what)
            pieces.append(solid)
        arms.append(pieces)
    return arms


def _round(g: _Frame, face: Face, keep: list[Point]) -> Face:
    """2D rounding of the arm's corners; the hub's mating corners (and any in `keep`) stay sharp.

    hitech is crisp: its truss gets no 2D rounding (the 3D finish gives every edge its small
    rounding); rounding dozens of truss corners in 2D leaves short slivers between neighbouring
    arcs, and the 3D finish then falls back to edge-by-edge rounding, which takes minutes.
    """
    if g.d.name == "hitech":
        return face
    if g.d.name == "biomech":
        bend, outer = BIO_BEND * g.t, BIO_OUTER * g.t
    else:
        bend, outer = g.edge, min(g.edge, THIN_EDGE * g.t)

    def radius(pos, convex: bool) -> float:
        if any(abs(pos.X - x) < 0.5 and abs(pos.Z - z) < 0.5 for x, z in keep):
            return 0.0
        return outer if convex else bend

    return round_corners(face, g.d, bend, outer, radius=radius)


def _check_clearance(g: _Frame, face: Face) -> None:
    """Nothing of the arm inward of the end wall below z_clear, except the cradle under and beside the object."""
    room = [
        poly([(g.x_h0 + 0.01, g.z_wall + 0.01), (g.x_p0 - 0.01, g.z_wall + 0.01), (g.x_p0 - 0.01, g.z_clear), (g.x_h0 + 0.01, g.z_clear)]),
        poly([(g.x_h0 + 0.01, g.z_b + 0.01), (g.x_e - g.spec.cradle_len - 0.01, g.z_b + 0.01), (g.x_e - g.spec.cradle_len - 0.01, g.z_clear), (g.x_h0 + 0.01, g.z_clear)]),
    ]
    for r in room:
        common = face & r
        area = sum(f.area for f in common.faces()) if common is not None else 0.0
        if area > 1e-3:
            raise ValueError(f"the {g.d.name} arm reaches {area:.0f} mm2 into the room the object needs: make the drop larger")


def _centre_length(centre: list[Point]) -> tuple[np.ndarray, np.ndarray]:
    pts = np.array(centre)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    return pts, np.concatenate([[0.0], np.cumsum(seg)])


def _cut_at(centre: list[Point], s: float) -> _Cut:
    pts, acc = _centre_length(centre)
    i = int(np.clip(np.searchsorted(acc, s) - 1, 0, len(pts) - 2))
    d = pts[i + 1] - pts[i]
    d = d / np.linalg.norm(d)
    at = pts[i] + d * (s - acc[i])
    return _Cut((float(at[0]), float(at[1])), (float(d[0]), float(d[1])))


def _cuts(g: _Frame, elev: _Elevation) -> list[_Cut]:
    """The fewest equal (seated) cuts along the centreline that leave every segment within the bed.

    A segment's size is its elevation with the joint bands plus the tenons it carries, so an arm
    that fits whole is never cut.
    """
    limit = g.p.usable_volume_mm[0] - 10
    _, acc = _centre_length(elev.centre)
    worst = (0.0, 0.0)
    for n in range(1, 8):
        cuts = [_seat(g, elev.solid, _cut_at(elev.centre, acc[-1] * k / n)) for k in range(1, n)]
        face, _ = _with_bands(g, elev.solid, cuts)
        sizes = [_segment_size(g, face, cuts, k) for k in range(n)]
        if all(max(size) <= limit for size in sizes):
            return cuts
        worst = max(sizes, key=max)
    raise ValueError(
        f"the arm does not fit the bed even in 7 segments: the largest is {worst[0]:.0f} x {worst[1]:.0f} mm, "
        f"the bed takes {limit:.0f} mm (usable {g.p.usable_volume_mm[0]:.0f} less a 10 mm margin)"
    )


def _with_bands(g: _Frame, face: Face, cuts: list[_Cut]) -> tuple[Face, list[Face]]:
    """(the elevation with a joint band round every cut, the bands)."""
    bands = [_joint_band(g, face, c) for c in cuts]
    if not bands:
        return face, bands
    fused = fuse([face, *bands])
    return max(fused.clean().faces(), key=lambda f: f.area), bands


def _segment_size(g: _Frame, face: Face, cuts: list[_Cut], k: int) -> tuple[float, float]:
    """(X, Z) size of segment k as it lies on the bed: its elevation and the tenons sticking out of it."""
    part = face if not cuts else face & poly(_region(cuts, k))
    box = part.bounding_box()
    xs, zs = [box.min.X, box.max.X], [box.min.Z, box.max.Z]
    if k % 2 == 0:  # tenon pieces: segments 1, 3, ... (k = 0, 2, ...)
        reach = g.p.min_wall_mm + g.joint.depth
        for jt in _joints(g, cuts)[k : k + 2]:
            (x, z), (tx, tz) = jt.at, jt.t
            for along in (0.0, reach):
                for across in (-g.joint.wide / 2, g.joint.wide / 2):
                    xs.append(x + tx * along + tz * across)
                    zs.append(z + tz * along - tx * across)
    return max(xs) - min(xs), max(zs) - min(zs)


def _joints(g: _Frame, cuts: list[_Cut]) -> list["_Joint"]:
    """The hub joint, then one per cut: joints[k] and joints[k + 1] are segment k's ends."""
    return [_hub_joint(g)] + [_cut_joint(g, c, odd=(k % 2 == 0)) for k, c in enumerate(cuts)]


def _region(cuts: list[_Cut], k: int) -> list[Point]:
    """Segment k's share of the plane: past cut k-1 and before cut k (square to the centreline there)."""
    poly_ = np.array([(-_BIG, -_BIG), (_BIG, -_BIG), (_BIG, _BIG), (-_BIG, _BIG)])
    for j, c in enumerate(cuts):
        sign = 1.0 if j < k else -1.0  # keep (q - at) . d >= 0 past an earlier cut, <= 0 before a later one
        poly_ = _clip(poly_, np.array(c.at), sign * np.array(c.d))
    return [(float(x), float(z)) for x, z in poly_]


def _clip(poly_: np.ndarray, at: np.ndarray, n: np.ndarray) -> np.ndarray:
    """The part of a convex polygon where (q - at) . n >= 0."""
    out = []
    for a, b in zip(poly_, np.roll(poly_, -1, axis=0)):
        da, db = (a - at) @ n, (b - at) @ n
        if da >= 0:
            out.append(a)
        if (da >= 0) != (db >= 0):
            out.append(a + (b - a) * da / (da - db))
    return np.array(out)


def _joint_size(g: _Frame) -> tuple[float, float]:
    """(half length along the centreline, half width across it) of the solid a segment joint needs."""
    half_len = g.joint.depth + g.p.slide_fit_mm + JOINT_GAP * g.p.min_wall_mm
    half_w = g.joint.wide / 2 + g.p.slide_fit_mm + JOINT_GAP * g.p.min_wall_mm
    return half_len, half_w


def _rect(c: _Cut, along: float, across: float, shift: float = 0.0) -> Face:
    """A rectangle round the cut point: `along` either way along the centreline, `across` either way square to it."""
    (x, z), (dx, dz) = c.at, c.d
    nx, nz = -dz, dx
    x, z = x + nx * shift, z + nz * shift
    return poly([(x - dx * along + nx * across, z - dz * along + nz * across), (x + dx * along + nx * across, z + dz * along + nz * across),
                 (x + dx * along - nx * across, z + dz * along - nz * across), (x - dx * along - nx * across, z - dz * along - nz * across)])


def _seat(g: _Frame, face: Face, c: _Cut) -> _Cut:
    """The cut point moved along the cut line to the middle of the arm's envelope there, when it is off it.

    Where the envelope across the cut is wider than the joint, the dovetail then sits inside it and
    no block has to stick out (a curved member's centreline runs close to the envelope's edge).
    """
    envelope = Face(face.outer_wire())
    nx, nz = -c.d[1], c.d[0]
    best = None
    for f in (envelope & _rect(c, 0.05, _BIG)).faces():
        ts = [(v.X - c.at[0]) * nx + (v.Z - c.at[1]) * nz for v in f.vertices()]
        lo, hi = min(ts), max(ts)
        gap = 0.0 if lo <= 0 <= hi else min(abs(lo), abs(hi))
        if best is None or gap < best[0]:
            best = (gap, lo, hi)
    if best is None:
        return c
    _, lo, hi = best
    half_w = _joint_size(g)[1] + 1.0  # the block stays a mm inside the envelope: no sliver along its edge
    t = 0.0 if hi - lo < 2 * half_w else min(max(0.0, lo + half_w), hi - half_w)
    return _Cut((c.at[0] + nx * t, c.at[1] + nz * t), c.d)


def _joint_band(g: _Frame, face: Face, c: _Cut) -> Face:
    """Solid across the arm round a (seated) cut: the envelope inside a strip, plus a block where the arm is too thin."""
    half_len, half_w = _joint_size(g)
    strip = Face(face.outer_wire()) & _rect(c, half_len, _BIG)
    return fuse([*strip.faces(), _rect(c, half_len, half_w)])


@dataclass(frozen=True)
class _Joint:
    at: Point      # (x, z) on the mating face where the tenon's root is centred
    t: Point       # unit direction the tenon points along, in (x, z)
    y_top: float   # the mouth (+Y face)

    def place(self, shape, p: Profile):
        """Joint frame -> world: local x along t, local y down along -Y from the mouth, local z = x cross y.

        The frame's origin sits NECK_RUN = min_wall inside the socket piece: the socket keeps a
        straight neck that long at its face, so the lip over the dovetail's 45 degree flank starts
        with a min_wall flat instead of a knife edge.
        """
        tx, tz = self.t
        run = p.min_wall_mm
        origin = (self.at[0] + tx * run, self.y_top, self.at[1] + tz * run)
        plane = Plane(origin=origin, x_dir=(tx, 0, tz), z_dir=(tz, 0, -tx))
        return plane.location * shape


def _hub_joint(g: _Frame) -> _Joint:
    return _Joint(g.hub_c, (-1.0, 0.0), g.spec.depth / 2)


def _cut_joint(g: _Frame, c: _Cut, odd: bool) -> _Joint:
    """At a cut the odd segment (nearer the hub when it is segment 1, 3, ...) carries the tenon."""
    return _Joint(c.at, c.d if odd else (-c.d[0], -c.d[1]), g.spec.depth / 2)


def _tenon(joint: DovetailSpec, p: Profile, jt: _Joint, pad: float) -> Solid:
    """The tenon with a neck-wide root from `pad` behind the mating face (a finished face edge leaves no gap under it)."""
    tenon, _ = dovetail(joint, p)
    back = p.min_wall_mm + pad
    root = Pos(-back / 2, joint.length / 2, 0) * Box(back, joint.length, joint.neck)
    return jt.place(tenon + root, p)


def _socket_tool(joint: DovetailSpec, p: Profile, jt: _Joint) -> Solid:
    """The socket tool with its straight neck out through the mating face."""
    _, tool = dovetail(joint, p)
    fit = p.slide_fit_mm
    out = p.min_wall_mm + 1.0
    length = joint.length + fit + 1.0
    neck = Pos(-out / 2, length / 2 - 1.0, 0) * Box(out, length, joint.neck + 2 * fit)
    return jt.place(tool + neck, p)


def _pocket(g: _Frame, e: EndProfile) -> Solid:
    """The cradle pocket: the end profile plus slide fit per side, open on top and on +Y."""
    fit = g.p.slide_fit_mm
    half_top = e.width / 2 + fit
    half_bottom = (e.narrow / 2 + fit) if e.kind == "trapezoid" else half_top
    y_far = g.spec.depth / 2 + 1
    # Up to z_clear: the room over the object is empty there, but the rounding adds a concave fillet
    # where the end wall meets the cradle; cut lower, its sliver would end in a feather edge.
    z_top = max(g.z_clear, g.z_wall + 1, g.z_b + e.height + 1)
    pts = [(-half_bottom, g.z_b), (y_far, g.z_b), (y_far, z_top), (-half_top, z_top), (-half_top, g.z_b + e.height)]
    if half_bottom == half_top:
        pts.pop()
    plane = Plane(origin=(g.x_e - g.spec.cradle_len - 1, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    face = to_face(pts, plane)
    length = g.spec.cradle_len + 1 + fit
    solid = Solid.extrude(face, plane.z_dir * length)
    return solid


def _lattice_tool(g: _Frame, elev: _Elevation, bands: list[Face]) -> Compound | None:
    """The dialect's web lattice as 2D cutters: parametric's graded hex, biomech's organic cells."""
    if elev.web is None or g.d.name not in ("parametric", "biomech"):
        return None
    organic = g.d.name == "biomech"
    border = WEB_BORDER * g.p.min_wall_mm
    cell = (BIO_CELL if organic else PARAM_HEX_CELL) * g.p.min_wall_mm
    region = _inset(elev.web, border)
    plane = Plane(region)
    fld = point_field(region, plane, (g.x_h1, -g.H / 2), cell)
    keepout = [max(offset(b, border, kind=Kind.ARC).faces(), key=lambda f: f.area) for b in bands]
    if organic:
        cut = lattice(region, g.p, kind="organic", cell=cell, bar_max=BIO_BAR_MAX * g.p.min_wall_mm,
                      field=fld, keepout=keepout, up=None, seed=BIO_SEED)
    else:
        cut = lattice(region, g.p, kind="hex", cell=cell, bar_max=PARAM_BAR_MAX * g.p.min_wall_mm,
                      field=fld, keepout=keepout, up=None)
    return cut.tool


def _coarse(face: Face, step: float = 2.0) -> Face:
    """The face's outline as a polygon with points about `step` apart.

    The lattice samples curved edges every 0.25 mm; on a web this size that makes the organic
    lattice's convex clipping take many seconds. A polygon of 2 mm chords is within a few hundredths
    of a mm of the curve, well inside the lattice's solid border.
    """
    pts = []
    for e in face.outer_wire().edges():
        n = 1 if e.geom_type.name == "LINE" else max(2, math.ceil(e.length / step))
        pts += [(e.position_at(k / n).X, e.position_at(k / n).Z) for k in range(n)]
    return to_face(pts)


def _inset(face: Face, d: float) -> Face:
    """The largest piece of the face's outline moved in by d (round joins), as a polygon.

    manifold3d instead of OCCT's wire offset, which fails when a long concave web pinches into two.
    """
    import manifold3d as mf

    pts = [(v.X, v.Z) for v in _coarse(face).vertices()]
    cs = mf.CrossSection([pts], mf.FillRule.Positive)
    if cs.area() == 0:
        cs = mf.CrossSection([pts[::-1]], mf.FillRule.Positive)
    polys = cs.offset(-d, mf.JoinType.Round, 2.0, 16).to_polygons()
    best = max(polys, key=lambda q: abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(q, np.roll(q, -1, axis=0)))))
    return to_face([(float(u), float(v)) for u, v in best])


def _rib_runs(g: _Frame, path: list[Point], bands: list[Face], step: float = 0.25) -> list[list[Point]]:
    """The rib path with the stretches over the joint bands left out.

    The rib stops short of each band by half its width plus a margin, with its own square end.
    Cutting the finished rib along the band's edge instead leaves a knife-edge wedge wherever the
    rib crosses the cut at a slant. Pieces shorter than two rib widths are dropped.
    """
    if not bands:
        return [path]
    pts = np.array(path, dtype=float)
    acc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
    s = np.append(np.arange(0.0, acc[-1], step), acc[-1])
    at = np.column_stack([np.interp(s, acc, pts[:, 0]), np.interp(s, acc, pts[:, 1])])
    clear = g.rib_w / 2 + RIB_BAND_GAP * g.p.min_wall_mm
    covered = np.zeros(len(s), dtype=bool)
    for b in bands:
        grown = max(offset(b, clear, kind=Kind.ARC).faces(), key=lambda f: f.area)
        ra, rb = _segments(grown, Plane.XZ)
        covered |= _inside(at, ra, rb)
    runs, i = [], 0
    while i < len(s):
        if covered[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(s) and not covered[j + 1]:
            j += 1
        if s[j] - s[i] >= 2 * g.rib_w:
            inner = [tuple(map(float, pts[k])) for k in range(len(pts)) if s[i] + 0.05 < acc[k] < s[j] - 0.05]
            runs.append([tuple(map(float, at[i])), *inner, tuple(map(float, at[j]))])
        i = j + 1
    return runs


def _rib_solid(g: _Frame, path: list[Point]) -> Solid:
    """A relief rib on the +Y face (up in print) along an (x, z) path."""
    plane = Plane(origin=(0, g.spec.depth / 2, 0), x_dir=(1, 0, 0), z_dir=(0, 1, 0))  # u = X, v = -Z
    return rib([(u, -v) for u, v in path], g.rib_w, RIB_HEIGHT_LAYERS * g.p.layer_mm, plane, p=g.p)


# --- the mount ----------------------------------------------------------------------------------------


def _mount(spec: HangerSpec, joint: DovetailSpec, d: Dialect, p: Profile, deep: float) -> Solid:
    """The ceiling bar: styled underside, a dovetail socket at each end, countersunk screws up into the ceiling."""
    L2, H, D = spec.mount_len / 2, spec.mount_h, spec.depth
    xs = _screw_xs(spec, joint, p)
    head_r = _head_d(spec, p) / 2
    keep = [poly([(x - head_r - 2 * p.min_wall_mm, -H - _BIG), (x + head_r + 2 * p.min_wall_mm, -H - _BIG),
                  (x + head_r + 2 * p.min_wall_mm, 1.0), (x - head_r - 2 * p.min_wall_mm, 1.0)]) for x in xs]
    jb = joint.depth + p.slide_fit_mm + 2 * p.min_wall_mm  # solid end block round each socket
    face = poly([(-L2, -H), (L2, -H), (L2, 0.0), (-L2, 0.0)])
    belly = {"gaudi": GAUDI_BELLY, "parametric": PARAM_BELLY, "biomech": BIO_BELLY}.get(d.name)
    if belly is not None:
        under = catenary((-L2 + jb, -H + 0.5), (L2 - jb, -H + 0.5), belly * H + 0.5, n=16)
        face = fuse([face, poly([*under, (L2 - jb, -H / 2), (-L2 + jb, -H / 2)])])
        face = max(face.clean().faces(), key=lambda f: f.area)
    if d.name == "gothic":
        face = _pendants(face, xs, head_r, H, L2 - jb, p)
    # The wall over and under each socket is thin: edge finishes stay well inside it, and the bar's
    # ends keep square faces against the arms' hubs (only a small rounding at the room side).
    lip = (H - joint.wide) / 2 - p.slide_fit_mm
    edge = min(edge_size(d, D, p), THIN_EDGE * lip)
    end_r = max(lip - p.min_wall_mm, 0.0)
    if d.name == "biomech":
        bend, outer = BIO_BEND * spec.arm_t, BIO_OUTER * spec.arm_t
    else:
        bend = outer = edge_size(d, D, p)

    def radius(pos, convex: bool) -> float:
        if pos.Z > -1e-3:
            return 0.0  # the ceiling face stays flat to its edges
        if abs(pos.X) > L2 - 1e-3:
            return end_r
        return outer if convex else bend

    face = round_corners(face, d, bend, outer, radius=radius)
    y0 = -D / 2 - deep
    body = finish_extrusion(extrude_y(face, D / 2 - y0, y0), d, D, PRINT_DOWN, p, edge)

    if d.name in ("parametric", "biomech"):
        region = face & poly([(-L2 + jb, -H - _BIG), (L2 - jb, -H - _BIG), (L2 - jb, -WEB_BORDER * p.min_wall_mm), (-L2 + jb, -WEB_BORDER * p.min_wall_mm)])
        region = max(offset(max(region.faces(), key=lambda f: f.area), -WEB_BORDER * p.min_wall_mm, kind=Kind.ARC).faces(), key=lambda f: f.area)
        organic = d.name == "biomech"
        cell = (BIO_MOUNT_CELL if organic else PARAM_HEX_CELL) * p.min_wall_mm
        if organic:
            # Organic cells are seeded over their region: seeds under the screw strips would only make
            # cells that cross them and drop out. The bays between the strips are lattice regions of
            # their own (the edge margin replaces the keep-out's). The bar is short and carries the
            # arms at both ends: no grading, the smallest cells and the thickest bars all over (a
            # falling field would spread the seeds wider than the bay is tall).
            bays = [f for f in (region - keep).faces() if f.area > cell**2]
            cuts = [lattice(bay, p, kind="organic", cell=cell, bar_max=BIO_BAR_MAX * p.min_wall_mm,
                            field=lambda x, y, z: 1.0, up=None, seed=BIO_SEED) for bay in bays]
            holes = [f for c in cuts if c.tool is not None for f in c.tool.faces()]
            tool = Compound(holes) if holes else None
        else:
            fld = point_field(region, Plane(region), (0.0, 0.0), cell)
            tool = lattice(region, p, kind="hex", cell=cell, bar_max=PARAM_BAR_MAX * p.min_wall_mm,
                           field=fld, keepout=keep, up=None).tool
        if tool is not None:
            body = one(body - extrude_y(tool, D + deep + 2, y0 - 1), "the mount")
    if d.name == "hitech":
        rect = Face.make_rect(2 * (L2 - jb), H - 2 * edge,
                              Plane(origin=(0, D / 2, -H / 2), x_dir=(1, 0, 0), z_dir=(0, 1, 0)))
        cut = lattice(rect, p, kind="tri", cell=HITECH_TRI_CELL * p.min_wall_mm, keepout=keep, up=None)
        if cut.tool is not None:
            # Blind pockets in the +Y face, which is up in print.
            depth = HITECH_POCKET * D + 0.5
            pockets = Compound([Solid.extrude(Pos(0, 0.5, 0) * f, (0, -depth, 0)) for f in cut.tool.faces()])
            body = one(body - pockets, "the mount")

    socket = _socket_tool(joint, p, _Joint((L2, -H / 2), (-1.0, 0.0), D / 2))
    body = one(body - socket - mirror(socket, about=Plane.YZ), "the mount")
    for x in xs:
        for tool in _screw_tools(spec, p, x):
            body = one(body - tool, "the mount")
    return body


def _pendants(face: Face, xs: list[float], head_r: float, H: float, x_end: float, p: Profile) -> Face:
    """Gothic: an inverted pointed arch hangs under the bar in each gap between the screws and the ends."""
    stops = [-x_end, *xs, x_end]
    added = 0
    for a, b in zip(stops, stops[1:]):
        lo = a + (head_r + 2 * p.min_wall_mm if a != -x_end else 0.0)
        hi = b - (head_r + 2 * p.min_wall_mm if b != x_end else 0.0)
        span = GOTHIC_PENDANT * (b - a)
        if hi - lo < span or span < 4 * p.min_wall_mm:
            continue
        mid = (lo + hi) / 2
        pts = [(mid + u, -H + 0.5 - v) for u, v in arch("pointed", span, span * _SQRT3 / 2, n=24)]
        face = fuse([face, poly(pts)])
        added += 1
    if added == 0:
        note("hanger", "gothic: no gap between the screws wide enough for a pendant", "info")
    return max(face.clean().faces(), key=lambda f: f.area)


def _screw_tools(spec: HangerSpec, p: Profile, x: float) -> list[Solid]:
    """Countersunk wood screw from the room face up into the ceiling, with 45 degree caps towards +Y.

    The screw lies horizontal in print, so the shank, the countersink and the head well each get a
    teardrop roof pointing up (+Y). The tools are subtracted one by one: fused into one tool, a cap
    touching its cylinder tangentially leaves an invalid solid that cuts nothing.
    """
    H = spec.mount_h
    d = _screw_d(spec)
    hole_d = d + fasteners.WOOD_SCREW_CLEARANCE + p.hole_clearance_mm
    head_d = _head_d(spec, p)
    z_seat = -H + SCREW_RECESS * H
    shank = H - SCREW_RECESS * H + 1
    tool = Pos(x, 0, z_seat) * Rot(180, 0, 0) * fasteners.wood_screw_countersunk_hole(d, shank, p)
    below = 2 * H  # the well runs out through any styled underside
    well = Pos(x, 0, z_seat - below / 2) * Cylinder(head_d / 2, below + 0.01)
    up = (0.0, 1.0)

    def cap(dia: float, z: float):
        return cap_face(dia, up, Plane(origin=(x, 0, z), x_dir=(1, 0, 0), z_dir=(0, 0, 1)))

    cone_h = (head_d - hole_d) / 2
    caps = [
        Solid.extrude(cap(hole_d, z_seat), (0, 0, shank)),
        Solid.extrude(cap(head_d, z_seat - below), (0, 0, below)),
        Solid.make_loft([cap(head_d, z_seat).outer_wire(), cap(hole_d, z_seat + cone_h).outer_wire()], ruled=True),
    ]
    return [tool, well, *caps]
