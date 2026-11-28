"""openGrid and Multiconnect interface: a part's back slides onto a Multiconnect snap or clips into a board.

Convention: the part's back face is the plane Z=0, the part lies below it (−Z) and the wall above
(+Z). `multiconnect_slot` is subtracted (it goes down into the part), `snap` is added (it stands up
toward the wall) and +Y is up on the wall. For a back face at the bottom of a part (printed back
down), turn the tool over about Y so up stays up:
`body -= Pos(x, y, z_back) * Rot(0, 180, 0) * multiconnect_slot(...)`. Rot(180, 0, 0) would turn
the slot upside down as well.

The sizes are the openGrid standard, clearances included, and are not taken from printer.toml:
parts must fit the official snaps and boards whatever the profile says.

Source and licence: "openGrid - Wall/Desk mounting framework/ecosystem" by David D,
https://makerworld.com/en/models/1179191-opengrid-wall-desk-mounting-framework-ecosystem ,
Creative Commons Attribution (CC BY). The dimensions here are derived from its modeling files
(sections through the STEP files named next to each value). The code is MIT like the rest of the
workshop; the openGrid and Multiconnect designs remain their authors'.
"""

from __future__ import annotations

import math

from build123d import (
    Axis,
    Box,
    Circle,
    Cone,
    Part,
    Plane,
    Polygon,
    Pos,
    Rectangle,
    Rot,
    SlotCenterToCenter,
    extrude,
    mirror,
    revolve,
)

from .config import Profile

EPS = 0.01  # tools stick out of the surface this much so the boolean leaves no skin

PITCH = 28.0     # grid pitch (openGrid board, every file)
BACK_MM = 6.4    # back thickness of the official Multiconnect backs (Multiconnect modeling files/top-back.step)

# Multiconnect slot, depth from the back face (Multiconnect modeling files/slot-negative.step,
# half-round-negative.step). The 0.15 clearance to the connector is included.
SLOT_DEPTH = 4.15
SLOT_NECK_HALF = 7.65        # neck 15.3 wide at the surface ...
SLOT_NECK_DEPTH = 0.438      # ... for this depth, then 45° outward
SLOT_WIDE_HALF = 10.15       # wide part 20.3, from 2.938 deep to the bottom; also the closed end radius
SLOT_FLARE_R = 11.0          # entry flare at the open end: R 10.15 at the bottom to R 11.0 at the surface
                             # (slot-opening.step)

# Detent of the snap-in slot (snap-in-slot-negative.step): half width of the wide part at a distance
# from the connector centre toward the open end. Outside these points the slot is 2 × 10.15 wide.
_DETENT = [
    (0.759, 10.150), (1.229, 10.139), (1.699, 10.106), (2.167, 10.052), (2.632, 9.976),
    (3.092, 9.878), (3.548, 9.759), (8.491, 10.130), (8.759, 10.150),
]

# openGrid snap (Snap modeling files/openGrid Bare Snap.step, openGrid Bare Lite Snap.step), in the
# file's own frame: wall side at Z=0, front (the part's side) at Z=height.
SNAP_HEIGHT = 6.8            # full board; Lite 3.4
SNAP_LITE_HEIGHT = 3.4
SNAP_FLATS = 24.8            # across flats
SNAP_CORNER = 4.818          # 45° corner leg
SNAP_SLIT = (11.1, 11.7, 12.4)  # slit from 11.1 to 11.7 off centre, 12.4 long with round ends;
                                # it stops 0.6 below the front
SNAP_GAP = (1.2, 0.8, 6.0)   # gap over the flex tab: from height-1.2 to height-0.8, half length 6.0
SNAP_WEDGE = (1.5, 0.4, 21.537)  # corner wedge at the front: grows at 45° from height-1.5 to
                                 # height-0.4, where its face is at x + y = 21.537
SNAP_BUMP = 0.4              # latch bump on each tab: 0.4 proud ...
SNAP_BUMP_HALF = 5.4         # ... 10.8 long, flat for |y| ≤ 1.915, then an R 15.38 arc to the tab
SNAP_BUMP_FLAT = 1.915
SNAP_BUMP_R = 15.38
SNAP_BUMP_RISE = 0.571       # 0.4 out over 0.571 in Z on both flanks
SNAP_BUMP_Z = {False: (3.4, 5.4), True: (0.2, 2.0)}  # bump from–to in Z, full and Lite


def multiconnect_slot(length: float, *, detent: bool = False, flare: bool = True) -> Part:
    """A Multiconnect slot to subtract from a back face at Z=0.

    +Y is up on the wall. The part is lowered onto the connector, so the slot opens downward at
    Y = −length (put that at the part's lower edge) and the part hangs on the closed round end, with
    the connector's centre at (0, 0). `detent` adds the snap-in bump below the connector that keeps
    the part from lifting off, `flare` the entry funnel at the open end.
    """
    if length < SLOT_WIDE_HALF:
        raise ValueError(
            f"Multiconnect slot {length} mm is too short: from the connector centre to the open end "
            f"at least {SLOT_WIDE_HALF} mm"
        )
    wide_top = SLOT_NECK_DEPTH + (SLOT_WIDE_HALF - SLOT_NECK_HALF)
    half = [
        (0, EPS), (SLOT_NECK_HALF, EPS), (SLOT_NECK_HALF, -SLOT_NECK_DEPTH),
        (SLOT_WIDE_HALF, -wide_top), (SLOT_WIDE_HALF, -SLOT_DEPTH), (0, -SLOT_DEPTH),
    ]
    full = half[1:5] + [(-x, z) for x, z in reversed(half[1:5])]
    straight = extrude(Plane.XZ * Polygon(*full, align=None), amount=length)  # Plane.XZ normal is +Y
    end = revolve(Plane.XZ * Polygon(*half, align=None), Axis.Z)
    slot = straight + end
    if detent:
        side = [(SLOT_WIDE_HALF + 1, _DETENT[0][0])] + [(x, y) for y, x in _DETENT]
        side += [(SLOT_WIDE_HALF + 1, _DETENT[-1][0])]
        bump = Pos(0, 0, -SLOT_DEPTH - EPS) * extrude(Polygon(*side, align=None), amount=SLOT_DEPTH + 2 * EPS, dir=(0, 0, 1))
        slot = slot - bump - mirror(bump, about=Plane.YZ)
    if flare:
        h = SLOT_DEPTH + EPS
        r_top = SLOT_FLARE_R + (SLOT_FLARE_R - SLOT_WIDE_HALF) * EPS / SLOT_DEPTH
        cone = Pos(0, length, -SLOT_DEPTH + h / 2) * Cone(SLOT_WIDE_HALF, r_top, h)
        keep = Pos(0, length - SLOT_FLARE_R, -SLOT_DEPTH / 2) * Box(
            4 * SLOT_FLARE_R, 2 * SLOT_FLARE_R, 2 * SLOT_DEPTH
        )
        slot += cone & keep
    return Rot(0, 0, 180) * slot  # built with the open end at +Y; the slot is symmetric in X


def snap(*, lite: bool = False) -> Part:
    """An openGrid snap to add to a back face at Z=0: it stands up to the wall (+Z).

    6.8 high for a full board, 3.4 for a Lite board. Centre it on a grid cell of the part's back
    (see `grid_positions`).
    """
    h = SNAP_LITE_HEIGHT if lite else SNAP_HEIGHT
    half = SNAP_FLATS / 2
    c = half - SNAP_CORNER
    octagon = [(c, -half), (half, -c), (half, c), (c, half), (-c, half), (-half, c), (-half, -c), (-c, -half)]
    body = extrude(Polygon(*octagon, align=None), amount=h)

    s_in, s_out, s_len = SNAP_SLIT
    slit = Pos((s_in + s_out) / 2, 0, -EPS) * extrude(
        SlotCenterToCenter(s_len - (s_out - s_in), s_out - s_in, rotation=90), amount=h - 0.6 + EPS
    )
    g_lo, g_hi, g_half = SNAP_GAP
    gap = Pos((s_out + half + 1) / 2, 0, h - (g_lo + g_hi) / 2) * Box(half + 1 - s_out, 2 * g_half, g_lo - g_hi)

    w_lo, w_hi, w_face = SNAP_WEDGE
    u0, u1 = (2 * c + SNAP_CORNER) / math.sqrt(2), w_face / math.sqrt(2)   # chamfer line, wedge face
    profile = Polygon((u0, h - w_lo), (u1, h - w_hi), (u1, h), (u0, h), align=None)
    diag = Plane(origin=(0, 0, 0), x_dir=(1, 1, 0), z_dir=(1, -1, 0))
    wedge = extrude(diag * profile, amount=half, both=True)
    wedge &= Pos(0, 0, h / 2) * Box(SNAP_FLATS, SNAP_FLATS, h)

    z0, z1 = SNAP_BUMP_Z[lite]
    out = half + SNAP_BUMP
    flank = extrude(
        Plane.XZ * Polygon(
            (half - 0.1, z0), (half, z0), (out, z0 + SNAP_BUMP_RISE), (out, z1 - SNAP_BUMP_RISE),
            (half, z1), (half - 0.1, z1), align=None,
        ),
        amount=SNAP_BUMP_HALF, both=True,
    )
    cx = out - SNAP_BUMP_R
    plan = Pos(cx, SNAP_BUMP_FLAT) * Circle(SNAP_BUMP_R) + Pos(cx, -SNAP_BUMP_FLAT) * Circle(SNAP_BUMP_R)
    plan += Pos(out - 1, 0) * Rectangle(2, 2 * SNAP_BUMP_FLAT)
    bump = flank & Pos(0, 0, z0 - 1) * extrude(plan, amount=z1 - z0 + 2)

    for k in range(4):
        turn = Rot(0, 0, 90 * k)
        body -= turn * slit
        body -= turn * gap
        body += turn * wedge
        body += turn * bump
    # the file's frame has the wall at Z=0: turn it so the front sits on the part's back at Z=0
    return Pos(0, 0, h) * Rot(180, 0, 0) * body


def grid_positions(width: float, height: float | None = None) -> list[tuple[float, float]]:
    """Centres of the whole 28 mm cells that fit in width × height, centred on (0, 0).

    Without a height: one row at Y = 0. Empty when not even one cell fits.
    """
    def axis(size: float) -> list[float]:
        n = int(size // PITCH + 1e-9)
        return [(i - (n - 1) / 2) * PITCH for i in range(n)]

    ys = [0.0] if height is None else axis(height)
    return [(x, y) for x in axis(width) for y in ys]


def require_cells(width: float, height: float | None = None) -> None:
    """For `_validate`: the back must hold at least one 28 mm cell, or it gets no interface at all."""
    for name, size in (("width", width), ("height", height)):
        if size is not None and size < PITCH - 1e-9:
            raise ValueError(f"back {name} {size} mm holds no openGrid cell: at least {PITCH:g} mm")


def require_back(thickness: float, p: Profile) -> None:
    """For `_validate`: a back with a Multiconnect slot must keep a wall behind the slot."""
    minimum = SLOT_DEPTH + p.min_wall_mm
    if thickness < minimum - 1e-9:
        raise ValueError(
            f"back {thickness} mm is too thin for a Multiconnect slot: at least {minimum:.2f} mm "
            f"(slot {SLOT_DEPTH} + wall {p.min_wall_mm}), the official backs are {BACK_MM} mm"
        )
