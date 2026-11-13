"""Threads for printing: the turns as one body (a profile swept along a helix).

The profile is metric ISO 68-1 (60°): thread height 5H/8 = 0.5413·P, width at the root
7P/8, at the crest P/4.

An OCCT quirk: swept turns fuse with the sleeve only when they lie entirely within its
height. If the turns are trimmed beforehand or stick out past the end, fuse silently drops them or
returns two bodies. So the tube is built 2 pitches longer at each end,
the turns are fused, and then the finished body is trimmed to height.

A printed thread always needs clearance: pass the diameter with the clearance included
(THREAD_D + p.slide_fit_mm for an internal one). Take the clearance from the printer profile.
"""

from __future__ import annotations

from build123d import Box, Cylinder, Helix, Plane, Polygon, Pos, Solid, sweep

ISO_THREAD_H = 0.541266   # thread height as a share of the pitch (5H/8, H = 0.866P)
ROOT_W = 0.875            # thread width at the root as a share of the pitch
CREST_W = 0.25            # thread width at the crest as a share of the pitch
EMBED = 0.2               # the turn's root goes into the wall: a volume merge, not a touch


def minor_diameter(major_d: float, pitch: float) -> float:
    """Minor diameter of the thread (at the crests of the nut's turns)."""
    return major_d - 2 * ISO_THREAD_H * pitch


def _ridge(base_r: float, crest_r: float, pitch: float, z0: float, z1: float) -> Solid:
    """Turns of a right-hand thread from base_r (root) to crest_r (crest), roughly from z0 to z1."""
    wb, wt = ROOT_W * pitch, CREST_W * pitch
    profile = Plane.XZ * Polygon((base_r, -wb / 2), (crest_r, -wt / 2), (crest_r, wt / 2), (base_r, wb / 2), align=None)
    ridge = Pos(0, 0, z0) * sweep(profile, path=Helix(pitch=pitch, height=z1 - z0, radius=base_r), is_frenet=True)
    return ridge.solids()[0]


def internal_thread_tube(outer_d: float, major_d: float, pitch: float, length: float) -> Solid:
    """A tube Ø outer_d, `length` high (from Z = 0), with an internal thread Ø major_d over its whole height."""
    if outer_d <= major_d:
        raise ValueError(f"outer Ø{outer_d} must be larger than the thread Ø{major_d}")
    margin = 2 * pitch
    z0, z1 = -margin, length + margin
    tall = Pos(0, 0, (z0 + z1) / 2) * (Cylinder(outer_d / 2, z1 - z0) - Cylinder(major_d / 2, z1 - z0))
    ridge = _ridge(major_d / 2 + EMBED, major_d / 2 - ISO_THREAD_H * pitch, pitch, z0 + pitch, z1 - pitch)

    fused = tall.solids()[0].fuse(ridge)
    if len(fused.solids()) != 1 or fused.volume < tall.volume + 0.5 * ridge.volume:
        raise RuntimeError("the turns did not fuse with the tube")  # guard against OCCT silently dropping turns
    trimmed = fused.solids()[0].intersect(Pos(0, 0, length / 2) * Box(outer_d + 2, outer_d + 2, length))
    solids = trimmed.solids()
    if len(solids) != 1:
        raise RuntimeError(f"after trimming the threaded tube fell apart into {len(solids)} bodies")
    return solids[0]
