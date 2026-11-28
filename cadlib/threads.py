"""Threads for printing: the turns as one body (a profile swept along a helix).

Two profiles, chosen by `down`:

- `down=None`: metric ISO 68-1, both flanks 30° from the radial plane, height 5H/8 = 0.5413·P.
  A nut's tooth is 7P/8 wide at the root and P/4 at the crest, a bolt's 3P/4 and P/8.
- `down=-1` (default) or `down=+1`: the printable profile. Printed with the axis upright, an ISO
  flank that faces the bed is a 60° overhang: each 0.2 mm layer steps out ~0.35 mm, most of a line
  width, and the turns droop and peel. Here the flank on the `down` side (-Z or +Z of the model as
  it lies on the bed) is 45°, the other stays ISO 30°. The root width stays ISO, so the tooth is a
  little shorter (0.4755·P, 88% of ISO) with a P/8 crest. A printable nut still fits a metal ISO bolt:
  its 30° flank matches the bolt's, its 45° flank only leaves more room in the bolt's groove.

A printed pair must face its 45° flanks at each other in the assembly: the external thread's 45°
flank faces -Z, the internal one's +Z. A jar neck printed upright (down=-1) takes a cap printed
upside down (down=+1). If both parts print the same way up, make one of them ISO (down=None).

An OCCT quirk: swept turns fuse with the sleeve only when they lie entirely within its
height. If the turns are trimmed beforehand or stick out past the end, fuse silently drops them or
returns two bodies. So the tube is built 2 pitches longer at each end,
the turns are fused, and then the finished body is trimmed to height.

A printed thread always needs clearance: pass the diameter with the clearance included
(THREAD_D + p.thread_clearance_mm for an internal one). Take the clearance from the printer profile.
"""

from __future__ import annotations

import math

from build123d import Box, Cylinder, Helix, Plane, Polygon, Pos, Solid, sweep

ISO_THREAD_H = 0.541266   # ISO thread height as a share of the pitch (5H/8, H = 0.866P)
ISO_FLANK_DEG = 30.0      # ISO flank angle from the radial plane
PRINT_FLANK_DEG = 45.0    # the flank facing the bed in the printable profile: a 45° overhang
ROOT_W = 0.875            # internal thread: tooth width at the root (major Ø) as a share of the pitch
EXT_CREST_W = 0.125       # external thread: tooth width at the crest (major Ø): P/8
PRINT_CREST_W = 0.125     # printable internal tooth: width at the crest; sets the tooth height
EMBED = 0.2               # the turn's root goes into the wall: a volume merge, not a touch
# ISO metric coarse pitches, ISO 261:1998 (series 1), mm.
ISO_COARSE_PITCH = {"M3": 0.5, "M4": 0.7, "M5": 0.8, "M6": 1.0, "M8": 1.25, "M10": 1.5, "M12": 1.75}
FLANK_PAST = 0.05         # the flanks run this far into the wall before the root turns square: a corner
                          # exactly on the wall's cylinder sweeps into a tangent edge and the fuse drops the turns


def _flanks(down: int | None) -> tuple[float, float]:
    """Tangents of the lower (-Z) and upper (+Z) flank angles."""
    if down not in (None, -1, 1):
        raise ValueError(f"down must be -1, +1 or None (ISO), got {down!r}")
    iso, printed = math.tan(math.radians(ISO_FLANK_DEG)), math.tan(math.radians(PRINT_FLANK_DEG))
    return (printed if down == -1 else iso), (printed if down == 1 else iso)


def thread_height(pitch: float, down: int | None = -1) -> float:
    """Radial height of the turns: ISO 5H/8, or the shorter printable tooth."""
    if down is None:
        return ISO_THREAD_H * pitch
    lo, hi = _flanks(down)
    return (ROOT_W - PRINT_CREST_W) * pitch / (lo + hi)


def minor_diameter(major_d: float, pitch: float, down: int | None = -1) -> float:
    """Minor diameter of the thread (at the crests of the nut's turns, the core of a bolt)."""
    return major_d - 2 * thread_height(pitch, down)


def _ridge(points: list[tuple[float, float]], radius: float, pitch: float, z0: float, z1: float) -> Solid:
    """Turns of a right-hand thread: the (r, z) profile swept along a helix, roughly from z0 to z1."""
    profile = Plane.XZ * Polygon(*points, align=None)
    ridge = Pos(0, 0, z0) * sweep(profile, path=Helix(pitch=pitch, height=z1 - z0, radius=radius), is_frenet=True)
    return ridge.solids()[0]


def external_thread_rod(major_d: float, pitch: float, length: float, down: int | None = -1) -> Solid:
    """A rod with an external thread Ø major_d over its whole height, `length` high (from Z = 0).

    The core is the minor diameter; the turns reach major_d. For a printed pair, give the internal
    thread the clearance (internal_thread_tube(..., major_d + p.thread_clearance_mm, ...)) and keep
    this one nominal. `down`: see the module docstring.
    """
    margin = 2 * pitch
    z0, z1 = -margin, length + margin
    h = thread_height(pitch, down)
    lo, hi = _flanks(down)
    core_r, crest_r = major_d / 2 - h, major_d / 2
    c = EXT_CREST_W * pitch / 2
    f = FLANK_PAST
    z_lo, z_hi = -c - (h + f) * lo, c + (h + f) * hi
    points = [(core_r - EMBED, z_lo), (core_r - f, z_lo), (crest_r, -c),
              (crest_r, c), (core_r - f, z_hi), (core_r - EMBED, z_hi)]
    tall = Pos(0, 0, (z0 + z1) / 2) * Cylinder(core_r, z1 - z0)
    ridge = _ridge(points, core_r, pitch, z0 + pitch, z1 - pitch)

    fused = tall.solids()[0].fuse(ridge)
    if len(fused.solids()) != 1 or fused.volume < tall.volume + 0.5 * ridge.volume:
        raise RuntimeError("the turns did not fuse with the rod")
    trimmed = fused.solids()[0].intersect(Pos(0, 0, length / 2) * Box(major_d + 2, major_d + 2, length))
    solids = trimmed.solids()
    if len(solids) != 1:
        raise RuntimeError(f"after trimming the threaded rod fell apart into {len(solids)} bodies")
    return solids[0]


def internal_thread_tube(outer_d: float, major_d: float, pitch: float, length: float,
                         down: int | None = -1) -> Solid:
    """A tube Ø outer_d, `length` high (from Z = 0), with an internal thread Ø major_d over its whole height.

    `down`: see the module docstring.
    """
    if outer_d <= major_d:
        raise ValueError(f"outer Ø{outer_d} must be larger than the thread Ø{major_d}")
    margin = 2 * pitch
    z0, z1 = -margin, length + margin
    h = thread_height(pitch, down)
    lo, hi = _flanks(down)
    root_r, crest_r = major_d / 2, major_d / 2 - h
    w = ROOT_W * pitch / 2
    f = FLANK_PAST
    z_lo, z_hi = -w - f * lo, w + f * hi
    points = [(root_r + EMBED, z_lo), (root_r + f, z_lo), (crest_r, -w + h * lo),
              (crest_r, w - h * hi), (root_r + f, z_hi), (root_r + EMBED, z_hi)]
    tall = Pos(0, 0, (z0 + z1) / 2) * (Cylinder(outer_d / 2, z1 - z0) - Cylinder(major_d / 2, z1 - z0))
    ridge = _ridge(points, root_r, pitch, z0 + pitch, z1 - pitch)

    fused = tall.solids()[0].fuse(ridge)
    if len(fused.solids()) != 1 or fused.volume < tall.volume + 0.5 * ridge.volume:
        raise RuntimeError("the turns did not fuse with the tube")  # guard against OCCT silently dropping turns
    trimmed = fused.solids()[0].intersect(Pos(0, 0, length / 2) * Box(outer_d + 2, outer_d + 2, length))
    solids = trimmed.solids()
    if len(solids) != 1:
        raise RuntimeError(f"after trimming the threaded tube fell apart into {len(solids)} bodies")
    return solids[0]
