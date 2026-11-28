"""Gridfinity: a base made to fit a drawer, split into bed-sized pieces, and bins for it.

Sizes are the Gridfinity standard as kennetek/gridfinity-rebuilt-openscad writes it
(https://github.com/kennetek/gridfinity-rebuilt-openscad, MIT License, Copyright (c) 2023 Kenneth
Hodson, on Gridfinity by Zachary Freedman, MIT). Read from its `src/core/standard.scad`,
`src/core/gridfinity-baseplate.scad`, `src/core/bin.scad` and `src/core/wall.scad` (2026-11-28); the
source variable is named next to each value. The standard's own sizes and clearances are kept as
they are, not taken from `printer.toml`, so bins and plates fit other people's. Everything else
(walls, the gap to the drawer, pockets for tools, the bed) comes from the profile `p`.

A drawer base: `baseplate_layout` fits whole cells into the drawer's inside size, the rest becomes a
solid rim, `split` cuts it into pieces that fit the bed, `drawer_base` builds them. Pieces are laid
side by side in the drawer, the drawer's walls hold them.

Coordinates: X and Y in the drawer's plane, Z up, the bottom on Z = 0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import (Align, Box, Circle, Part, Plane, Polygon, Pos, Rectangle, RectangleRounded, Rot, Sketch,
                       SlotOverall, extrude, loft)

from .config import Profile
from .magnets import magnet as _magnet
from .magnets import pocket as _pocket
from .magnets import pocket_depth as _pocket_depth
from .text import label as _label

# --- the standard ------------------------------------------------------------------------------

PITCH = 42.0            # GRID_DIMENSIONS_MM
UNIT_H = 7.0            # height unit: a bin's height_mm is units × 7, BASE_HEIGHT included
BIN_SIZE = 41.5         # BASE_TOP_DIMENSIONS: a 1 × 1 bin's footprint (BASE_GAP_MM = 0.5)
BIN_RADIUS = 3.75       # BASE_TOP_RADIUS = 7.5 / 2
BASE_HEIGHT = 7.0       # BASE_HEIGHT: the bin's base, solid floor by default (base_thickness)
# BASE_PROFILE: (inset growing outward, height) from the foot's bottom edge, 0.8 / 1.8 / 2.15
BASE_PROFILE = ((0.0, 0.0), (0.8, 0.8), (0.8, 2.6), (2.95, 4.75))
BASE_PROFILE_H = 4.75   # BASE_PROFILE_HEIGHT
# _BASEPLATE_PROFILE: the plate cell's cutter, 0.7 / 1.8 / 2.15, on top of a straight 0.35
PLATE_PROFILE = ((0.0, 0.0), (0.7, 0.7), (0.7, 2.5), (2.85, 4.65))
PLATE_HEIGHT = 5.0      # BASEPLATE_HEIGHT (plain style: no floor under the cells)
PLATE_RADIUS = 4.0      # BASEPLATE_OUTER_DIAMETER / 2: the cell opening's corner at the top
# STACKING_LIP_LINE, 0.7 / 1.8 / 1.9 above the wall top; tip filleted in the source
LIP_PROFILE = ((0.0, 0.0), (0.7, 0.7), (0.7, 2.5), (2.6, 4.4))
LIP_HEIGHT = 4.4        # STACKING_LIP_HEIGHT
LIP_SUPPORT_H = 1.2     # STACKING_LIP_SUPPORT_HEIGHT
LIP_TIP = 0.6           # STACKING_LIP_FILLET_RADIUS: here a flat 0.6 top instead of the fillet
WALL = 0.95             # d_wall
DIVIDER = 1.2           # d_div
MAGNET_FROM_SIDE = 8.0  # d_hole_from_side: magnet centres at ±(21 − 8) = ±13 from the cell centre
MAGNET_OFFSET = PITCH / 2 - MAGNET_FROM_SIDE
TAB_DEPTH = 15.85       # _tab_depth: the label shelf's depth
TAB_SUPPORT_H = 1.2     # _tab_support_height

ALIGNS = ("center", "-x", "+x", "-y", "+y")


# --- layout and split --------------------------------------------------------------------------


def max_piece_cells(p: Profile) -> int:
    """Most cells along one side of a piece that fit the bed's usable square."""
    ux, uy, _ = p.usable_volume_mm
    return int(min(ux, uy) // PITCH)


def split_counts(n: int, limit: int) -> list[int]:
    """n cells in as few pieces of at most `limit` as possible, as equal as possible, larger first."""
    return _even(n, math.ceil(n / limit))


def _even(n: int, k: int) -> list[int]:
    base, extra = divmod(n, k)
    return [base + 1] * extra + [base] * (k - extra)


@dataclass(frozen=True)
class _Axis:
    cells: int
    counts: tuple[int, ...]    # cells per piece along this axis
    rim_lo: float
    rim_hi: float
    gap: float                 # per side, to the drawer wall


def _axis(inside: float, p: Profile, side: str | None, name: str) -> _Axis:
    """Cells, pieces, rims and gap along one axis. `side` is None (centred), "lo" or "hi": the wall
    the grid is pushed against (its rim then goes all to the other side)."""
    usable = min(p.usable_volume_mm[:2])
    limit = max_piece_cells(p)
    n = int(inside // PITCH)
    while n >= 1:
        k = math.ceil(n / limit)
        while k <= n:
            counts = _even(n, k)
            spare = inside - n * PITCH - 2 * p.slide_fit_mm - (k - 1) * p.gridfinity_joint_mm
            if spare < 0:
                break
            if side is None:
                lo = hi = spare / 2 if spare / 2 >= p.min_wall_mm else 0.0
            else:
                rim = spare if spare >= p.min_wall_mm else 0.0
                lo, hi = (0.0, rim) if side == "lo" else (rim, 0.0)
            first = counts[0] * PITCH + lo + (hi if k == 1 else 0.0)
            last = counts[-1] * PITCH + hi + (lo if k == 1 else 0.0)
            if first <= usable + 1e-9 and last <= usable + 1e-9:
                return _Axis(n, tuple(counts), lo, hi, (inside - n * PITCH - lo - hi) / 2)
            k += 1
        n -= 1
    raise ValueError(f"{name} {inside:g} mm: not even one cell ({PITCH:g} mm plus "
                     f"{2 * p.slide_fit_mm:g} mm of gap) fits")


@dataclass(frozen=True)
class Layout:
    cells_x: int
    cells_y: int
    rim: tuple[float, float, float, float]   # solid rim on the −X, +X, −Y, +Y sides
    gap_x: float                             # gap to the drawer wall, per side
    gap_y: float
    inside: tuple[float, float]
    counts_x: tuple[int, ...]                # cells per piece along X, from −X
    counts_y: tuple[int, ...]


def baseplate_layout(inside_x: float, inside_y: float, p: Profile, align: str = "center") -> Layout:
    """Whole cells that fit the drawer's inside size with the gaps from the profile, the rest as a
    rim. `align`: "center" splits each rim between both sides; "-x", "+x", "-y", "+y" pushes the grid
    against that wall (its rim all on the opposite side), the other axis stays centred. A rim under
    `p.min_wall_mm` is not made: it stays gap."""
    if align not in ALIGNS:
        raise ValueError(f"align {align!r}: expected one of {', '.join(ALIGNS)}")
    sx = {"-x": "lo", "+x": "hi"}.get(align)
    sy = {"-y": "lo", "+y": "hi"}.get(align)
    ax = _axis(inside_x, p, sx, "drawer X")
    ay = _axis(inside_y, p, sy, "drawer Y")
    return Layout(ax.cells, ay.cells, (ax.rim_lo, ax.rim_hi, ay.rim_lo, ay.rim_hi), ax.gap, ay.gap,
                  (inside_x, inside_y), ax.counts, ay.counts)


@dataclass(frozen=True)
class Piece:
    name: str
    cells_x: int
    cells_y: int
    rim: tuple[float, float, float, float]   # −X, +X, −Y, +Y
    count: int


def split(layout: Layout, p: Profile) -> list[Piece]:
    """The layout's pieces, identical ones grouped with a count, named "a", "b", … from −X −Y."""
    groups: dict[tuple, int] = {}
    nx, ny = len(layout.counts_x), len(layout.counts_y)
    for j, cy in enumerate(layout.counts_y):
        for i, cx in enumerate(layout.counts_x):
            rim = (layout.rim[0] if i == 0 else 0.0, layout.rim[1] if i == nx - 1 else 0.0,
                   layout.rim[2] if j == 0 else 0.0, layout.rim[3] if j == ny - 1 else 0.0)
            key = (cx, cy, rim)
            groups[key] = groups.get(key, 0) + 1
    ux, uy, _ = p.usable_volume_mm
    pieces = []
    for k, ((cx, cy, rim), count) in enumerate(groups.items()):
        w, h = cx * PITCH + rim[0] + rim[1], cy * PITCH + rim[2] + rim[3]
        if w > ux + 1e-9 or h > uy + 1e-9:
            raise ValueError(f"piece {cx} × {cy} with its rim is {w:.1f} × {h:.1f} mm, over the bed")
        pieces.append(Piece(_name(k), cx, cy, rim, count))
    return pieces


def _name(k: int) -> str:
    s = ""
    k += 1
    while k:
        k, r = divmod(k - 1, 26)
        s = chr(ord("a") + r) + s
    return s


# --- solids ------------------------------------------------------------------------------------

EPS = 0.01   # tools stick out of a surface this much so a boolean leaves no skin


def _section(w: float, h: float, r: float, inset: float, z: float) -> Sketch:
    return Plane.XY.offset(z) * RectangleRounded(w - 2 * inset, h - 2 * inset, r - inset)


def _profile_solid(w: float, h: float, r: float, steps: list[tuple[float, float]]) -> Part:
    """A rounded-rectangle solid centred on the Z axis whose inset from (w, h, r) changes with height:
    `steps` is [(z, inset), ...] from the bottom up; equal insets give straight walls, others a
    ruled (conical at the corners) chamfer."""
    parts = []
    for (z0, i0), (z1, i1) in zip(steps, steps[1:]):
        if z1 - z0 <= 1e-9:
            continue
        parts.append(loft([_section(w, h, r, i0, z0), _section(w, h, r, i1, z1)], ruled=True))
    body = parts[0]
    for s in parts[1:]:
        body = body.fuse(s)
    return Part(body.clean().wrapped) if not isinstance(body, Part) else body.clean()


def _plate_cutter(z0: float) -> Part:
    """The empty space of one plate cell, its bottom at z0, open through the bottom and the top."""
    deepest = PLATE_PROFILE[-1][0]
    zb = z0 + PLATE_HEIGHT - PLATE_PROFILE[-1][1]   # the profile sits on a straight 0.35
    steps = [(z0 - EPS, deepest), (zb, deepest)]
    steps += [(zb + y, deepest - x) for x, y in PLATE_PROFILE[1:]]
    steps.append((z0 + PLATE_HEIGHT + EPS, 0.0))
    return _profile_solid(PITCH, PITCH, PLATE_RADIUS, steps)


def _magnet_check(size: str, p: Profile, max_depth: float | None = None):
    """The magnet and its pocket depth, if its pocket fits a bin foot's bottom at the standard spot
    (and is no deeper than `max_depth`)."""
    m = _magnet(size)
    if max_depth is not None and _pocket_depth(m, p) > max_depth + 1e-9:
        raise ValueError(f"magnet {m.name}: its pocket is {_pocket_depth(m, p):g} mm deep, a bin's base "
                         f"leaves room for {max_depth:g} mm")
    foot_half = BIN_SIZE / 2 - BASE_PROFILE[-1][0]       # 17.8: half the foot's bottom face
    room = 2 * (foot_half - MAGNET_OFFSET - p.min_wall_mm)
    if m.d + p.magnet_fit_mm > room + 1e-9:
        raise ValueError(f"magnet {m.name}: its pocket Ø {m.d + p.magnet_fit_mm:g} mm does not fit a bin "
                         f"foot at the standard spot (±{MAGNET_OFFSET:g} mm), at most Ø {room:.1f} mm")
    return m, _pocket_depth(m, p)


def _magnet_spots(cx: float, cy: float) -> list[tuple[float, float]]:
    o = MAGNET_OFFSET
    return [(cx + sx * o, cy + sy * o) for sx in (-1, 1) for sy in (-1, 1)]


def baseplate(cells_x: int, cells_y: int, p: Profile, *, rim=(0.0, 0.0, 0.0, 0.0),
              magnets: str | None = None) -> Part:
    """A plate piece: `cells_x` × `cells_y` open cells (standard profile, no floor) and a solid rim
    on the −X, +X, −Y, +Y sides. Bottom on Z = 0, the piece's −X −Y corner at the origin.
    `magnets` ("6x2", see `cadlib.magnets`) adds a floor with a pocket at each cell's four standard
    spots, opening up; the floor is the pocket's depth plus `p.min_wall_mm`."""
    if cells_x < 1 or cells_y < 1:
        raise ValueError(f"plate {cells_x} × {cells_y}: at least 1 × 1")
    floor = 0.0
    if magnets:
        m, depth = _magnet_check(magnets, p)
        floor = depth + p.min_wall_mm
    w = cells_x * PITCH + rim[0] + rim[1]
    h = cells_y * PITCH + rim[2] + rim[3]
    body = Box(w, h, floor + PLATE_HEIGHT, align=(Align.MIN, Align.MIN, Align.MIN))
    cutter = _plate_cutter(floor)
    for i in range(cells_x):
        for j in range(cells_y):
            cx, cy = rim[0] + (i + 0.5) * PITCH, rim[2] + (j + 0.5) * PITCH
            body -= Pos(cx, cy, 0) * cutter
            if magnets:
                for x, y in _magnet_spots(cx, cy):
                    body -= Pos(x, y, floor) * _pocket(m, p)
    return body


def piece_body(piece: Piece, p: Profile, magnets: str | None = None) -> Part:
    """The plate of one `split` piece."""
    return baseplate(piece.cells_x, piece.cells_y, p, rim=piece.rim, magnets=magnets)


def drawer_base(inside_x: float, inside_y: float, p: Profile, *, align: str = "center",
                magnets: str | None = None) -> list[tuple[str, Part, int]]:
    """A base for a drawer `inside_x` × `inside_y` mm, as pieces for a model's build(p) to return:
    [(name, plate, count), ...]. `cad.py build` writes each piece and one 3MF with a plate per copy."""
    return [(pc.name, piece_body(pc, p, magnets), pc.count)
            for pc in split(baseplate_layout(inside_x, inside_y, p, align), p)]


# --- bins --------------------------------------------------------------------------------------

MIN_COMPARTMENT = 5.0   # narrowest clear compartment a bin accepts, mm
MIN_SHELF = 5.0         # shallowest label shelf, mm
LABEL_DEPTH_LAYERS = 2  # the label is debossed this many layers into the shelf
NOTCH_D = 20.0          # finger notch diameter, mm


@dataclass(frozen=True)
class Pocket:
    """A pocket cut down from the top of a solid bin, for a tool or part.

    `size` is the object's own measured size (the fit `p.slide_fit_mm` is added): "rect" (w, l),
    "circle" (d,), "slot" (w, l) with round ends. `at` is from the bin's centre, `angle` turns it in
    plan (degrees), `notch` adds a round finger notch Ø `NOTCH_D` at its middle."""
    shape: str
    size: tuple[float, ...]
    depth: float
    at: tuple[float, float] = (0.0, 0.0)
    angle: float = 0.0
    notch: bool = False


def _pocket_sketch(pk: Pocket, fit: float):
    """The pocket's plan (centred, turned) and its half extents in X and Y."""
    if pk.shape == "rect" and len(pk.size) == 2:
        s = Rectangle(pk.size[0] + fit, pk.size[1] + fit)
    elif pk.shape == "circle" and len(pk.size) == 1:
        s = Circle((pk.size[0] + fit) / 2)
    elif pk.shape == "slot" and len(pk.size) == 2:
        w, l = pk.size[0] + fit, pk.size[1] + fit
        if l <= w:
            raise ValueError(f"pocket slot {pk.size}: the length must be more than the width")
        s = SlotOverall(l, w)
    else:
        raise ValueError(f"pocket {pk.shape} {pk.size}: expected rect (w, l), circle (d,) or slot (w, l)")
    if pk.notch:
        s = s + Circle(NOTCH_D / 2)
    s = Rot(0, 0, pk.angle) * s
    bb = s.bounding_box()
    return s, max(-bb.min.X, bb.max.X), max(-bb.min.Y, bb.max.Y)


def _cell_centres(cells_x: int, cells_y: int) -> list[tuple[float, float]]:
    return [((i - (cells_x - 1) / 2) * PITCH, (j - (cells_y - 1) / 2) * PITCH)
            for i in range(cells_x) for j in range(cells_y)]


def _foot() -> Part:
    deepest = BASE_PROFILE[-1][0]
    return _profile_solid(BIN_SIZE, BIN_SIZE, BIN_RADIUS, [(y, deepest - x) for x, y in BASE_PROFILE])


def _cavity_steps(top: float, wall: float, lip: bool, solid: bool) -> list[tuple[float, float]]:
    """Insets of the bin's inside from the outer outline, from the floor (or the lip) up."""
    lip_in = LIP_PROFILE[-1][0]                       # 2.6: the lip's inset at its bottom
    steps: list[tuple[float, float]] = []
    if not solid and top > BASE_HEIGHT:
        steps.append((BASE_HEIGHT, wall))
        if not lip:
            return steps + [(top + EPS, wall)]
        z_support = top - LIP_SUPPORT_H - (lip_in - wall)   # 45° from the wall out to the lip
        if z_support > BASE_HEIGHT:
            steps += [(z_support, wall), (top - LIP_SUPPORT_H, lip_in)]
        else:
            steps = [(BASE_HEIGHT, lip_in)]
        steps.append((top, lip_in))
    elif lip:
        steps.append((top - EPS, lip_in))
    if lip:
        (_, _), (x1, y1), (x2, y2), (x3, y3) = LIP_PROFILE
        z_tip = top + y2 + (lip_in - x2 - LIP_TIP)          # the chamfer meets the flat 0.6 top
        steps += [(top + y1, lip_in - x1), (top + y2, lip_in - x2), (z_tip, LIP_TIP),
                  (top + LIP_HEIGHT + EPS, LIP_TIP)]
    return steps


def bin_body(cells_x: int, cells_y: int, units: int, p: Profile, *, lip: bool = True,
             divisions: tuple[int, int] = (1, 1), widths: list[float] | None = None,
             label: str | None = None, shelf: bool = False, magnets: str | None = None,
             pockets=(), solid: bool = False) -> Part:
    """A Gridfinity bin `cells_x` × `cells_y` cells and `units` × 7 mm high (the base included, the
    stacking lip on top of that), centred on the Z axis, bottom on Z = 0.

    - `divisions` (nx, ny): equal compartments; `widths`: clear widths of the compartments along X
      from −X in mm, the last compartment takes what is left (replaces nx).
    - `shelf`: a label shelf at the back (+Y) of each compartment row, 45° under it (no supports);
      `label` is debossed into each shelf.
    - `magnets` ("6x2", `cadlib.magnets`): pockets from below at each foot's four standard spots.
    - `solid`: filled to the top, for `pockets` (tool shapes) cut down from the top.
    Walls and dividers are the standard's or `p.min_wall_mm`, whichever is thicker."""
    if units < 1:
        raise ValueError(f"bin height {units} units: at least 1 (7 mm)")
    if cells_x < 1 or cells_y < 1:
        raise ValueError(f"bin {cells_x} × {cells_y}: at least 1 × 1")
    if pockets and not solid:
        raise ValueError("pockets are cut into a solid bin: pass solid=True")
    if label and not shelf:
        raise ValueError("a label goes on the label shelf: pass shelf=True")
    if solid and (shelf or tuple(divisions) != (1, 1) or widths):
        raise ValueError("a solid bin has no compartments or label shelf")
    w, h = cells_x * PITCH - (PITCH - BIN_SIZE), cells_y * PITCH - (PITCH - BIN_SIZE)
    top = units * UNIT_H
    wall = max(WALL, p.min_wall_mm)
    div = max(DIVIDER, p.min_wall_mm)
    inner_w, inner_h = w - 2 * wall, h - 2 * wall
    m = depth = None
    if magnets:
        m, depth = _magnet_check(magnets, p, max_depth=BASE_HEIGHT - p.min_wall_mm)
    floor_top = BASE_PROFILE_H + p.min_wall_mm
    plans = []
    for pk in pockets:
        s, hx, hy = _pocket_sketch(pk, p.slide_fit_mm)
        if pk.depth <= 0 or pk.depth > top - floor_top + 1e-9:
            raise ValueError(f"pocket {pk.shape} {pk.size}: {pk.depth:g} mm is too deep, the bin leaves "
                             f"{top - floor_top:.1f} mm above its feet")
        x, y = pk.at
        if abs(x) + hx > inner_w / 2 + 1e-9 or abs(y) + hy > inner_h / 2 + 1e-9:
            raise ValueError(f"pocket {pk.shape} {pk.size} at {pk.at}: does not fit inside the walls "
                             f"({inner_w:.1f} × {inner_h:.1f} mm)")
        plans.append((pk, s))

    body = Pos(0, 0, BASE_PROFILE_H) * extrude(RectangleRounded(w, h, BIN_RADIUS), top - BASE_PROFILE_H)
    foot = _foot()
    for cx, cy in _cell_centres(cells_x, cells_y):
        body = body.fuse(Pos(cx, cy, 0) * foot)
    if lip:
        body = body.fuse(Pos(0, 0, top) * extrude(RectangleRounded(w, h, BIN_RADIUS), LIP_HEIGHT))
    steps = _cavity_steps(top, wall, lip, solid)
    if len(steps) >= 2:
        body = body.cut(_profile_solid(w, h, BIN_RADIUS, steps))
    if not solid and top > BASE_HEIGHT:
        body = _compartments(body, inner_w, inner_h, top, tuple(divisions), widths, div, shelf, label, p)
    if m is not None:
        tool = Rot(180, 0, 0) * _pocket(m, p)        # opens at Z = 0, goes up into the foot
        for cx, cy in _cell_centres(cells_x, cells_y):
            for x, y in _magnet_spots(cx, cy):
                body = body.cut(Pos(x, y, 0) * tool)
    for pk, s in plans:
        body = body.cut(Pos(pk.at[0], pk.at[1], top - pk.depth) * extrude(s, pk.depth + EPS))
    return body.clean()


def _splits(total: float, n: int, div: float) -> list[float]:
    """Divider centres for n equal compartments across `total` (from −total/2)."""
    clear = (total - (n - 1) * div) / n
    if clear < MIN_COMPARTMENT - 1e-9:
        raise ValueError(f"{n} compartments in {total:.1f} mm: each would be {clear:.1f} mm, under "
                         f"{MIN_COMPARTMENT:g} mm")
    return [-total / 2 + k * (clear + div) - div / 2 for k in range(1, n)]


def _compartments(body, inner_w, inner_h, top, divisions, widths, div, shelf, label, p):
    nx, ny = divisions
    if nx < 1 or ny < 1:
        raise ValueError(f"divisions {divisions}: at least (1, 1)")
    if widths:
        used = sum(widths) + len(widths) * div
        if min(widths) < MIN_COMPARTMENT or used > inner_w - MIN_COMPARTMENT + 1e-9:
            raise ValueError(f"compartment widths {widths}: with {div:g} mm dividers they take {used:.1f} mm "
                             f"and the last compartment needs {MIN_COMPARTMENT:g} mm, the bin has {inner_w:.1f}")
        xs, x = [], -inner_w / 2
        for v in widths:
            xs.append(x + v + div / 2)
            x += v + div
    else:
        xs = _splits(inner_w, nx, div)
    ys = _splits(inner_h, ny, div)
    hgt = top - BASE_HEIGHT
    for x in xs:
        body = body.fuse(Pos(x, 0, BASE_HEIGHT + hgt / 2) * Box(div, inner_h + EPS, hgt))
    for y in ys:
        body = body.fuse(Pos(0, y, BASE_HEIGHT + hgt / 2) * Box(inner_w + EPS, div, hgt))
    if not shelf:
        return body
    fronts = [-inner_h / 2] + [y + div / 2 for y in ys]
    backs = [y - div / 2 for y in ys] + [inner_h / 2]
    for front, back in zip(fronts, backs):
        depth = min(TAB_DEPTH, (back - front) / 2, top - BASE_HEIGHT - TAB_SUPPORT_H)
        if depth < MIN_SHELF:
            raise ValueError(f"label shelf: only {depth:.1f} mm of room, a shelf needs {MIN_SHELF:g} mm "
                             f"(a taller bin or fewer rows)")
        # in the YZ plane: plane X is world Y, plane Y is world Z
        prof = Polygon((back, top), (back - depth, top), (back - depth, top - TAB_SUPPORT_H),
                       (back, top - TAB_SUPPORT_H - depth), align=None)
        body = body.fuse(extrude(Plane.YZ * prof, amount=inner_w / 2 + EPS, both=True))
        if label:
            cut = LABEL_DEPTH_LAYERS * p.layer_mm
            size = min(depth * 0.6, 8.0)
            text = _label(label, size)
            tw = text.bounding_box().size.X
            if tw > inner_w - 4:
                text = _label(label, size * (inner_w - 4) / tw)
            body = body.cut(Pos(0, back - depth / 2, top - cut) * extrude(text, cut + EPS))
    return body
