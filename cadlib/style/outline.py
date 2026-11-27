"""2D opening outlines (arches) in (u, v), clipped so their roof never overhangs more than 45°."""

from __future__ import annotations

import math
from typing import Literal

from build123d import Face, Plane, Vector, Wire
from scipy.optimize import brentq

ArchKind = Literal["pointed", "catenary", "round", "oval"]

Point = tuple[float, float]


def arch(kind: ArchKind, span: float, rise: float, n: int = 64) -> list[Point]:
    """Closed convex counter-clockwise outline, base on v = 0 from -span/2 to +span/2, apex at +v.

    pointed: two circular arcs meeting at the apex (a drop arch when rise < span*sqrt(3)/2).
    catenary: inverted catenary. round and oval: half ellipse of width span and height rise.
    The closing base edge runs from the last point back to the first.
    """
    if span <= 0 or rise <= 0:
        raise ValueError("arch span and rise must be positive")
    h = span / 2
    if kind in ("round", "oval"):
        return [(h * math.cos(math.pi * i / n), rise * math.sin(math.pi * i / n)) for i in range(n + 1)]
    if kind == "pointed":
        # Right arc: centre (c, 0), through (h, 0) and the apex (0, rise).
        c = (h * h - rise * rise) / (2 * h)
        r = h - c
        a_apex = math.atan2(rise, -c)
        m = max(n // 2, 2)
        right = [(c + r * math.cos(a_apex * i / m), r * math.sin(a_apex * i / m)) for i in range(m + 1)]
        right[-1] = (0.0, rise)
        left = [(-u, v) for u, v in reversed(right[:-1])]
        return right + left
    if kind == "catenary":
        a = brentq(lambda a: rise - a * (math.cosh(h / a) - 1), 1e-3 * span, 1e4 * span)
        us = [h - span * i / n for i in range(n + 1)]
        return [(u, rise - a * (math.cosh(u / a) - 1)) for u in us]
    raise ValueError(f"unknown arch kind {kind!r}")


def _rot(points: list[Point], deg: float) -> list[Point]:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(c * u - s * v, s * u + c * v) for u, v in points]


def _is_convex(pts: list[Point], tol: float = 1e-9) -> bool:
    n = len(pts)
    signs = set()
    for i in range(n):
        (ax, ay), (bx, by), (cx, cy) = pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        if abs(cross) > tol:
            signs.add(cross > 0)
    return len(signs) <= 1


def clip_roof(points: list[Point], up: tuple[float, float] | None, max_deg: float = 45.0) -> list[Point]:
    """Cap the roof of a convex outline so no edge overhangs more than max_deg from vertical.

    `up` is print "up" in (u, v), None for a plane lying flat (outline returned unchanged).
    The flat part of the upper chain is replaced by two lines at +/-max_deg from the horizontal
    meeting in a point. A clipped result is counter-clockwise, an untouched one is `points` itself.
    """
    if up is None:
        return points
    if not _is_convex(points):
        raise ValueError("clip_roof needs a convex outline")
    rot = 90.0 - math.degrees(math.atan2(up[1], up[0]))  # turns `up` onto +v
    pts = _rot(points, rot)
    n = len(pts)
    if sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1])) < 0:
        pts.reverse()
    t = math.tan(math.radians(max_deg))
    # In a counter-clockwise polygon the edges running towards -u form the upper chain.
    leaving = [i for i in range(n) if pts[(i + 1) % n][0] - pts[i][0] < -1e-12]
    if not leaving:
        return points
    start = next(i for i in leaving if (i - 1) % n not in leaving)
    chain = [(start + k) % n for k in range(len(leaving) + 1)]  # CCW: right to left
    ltr = chain[::-1]
    slope = [
        (pts[b][1] - pts[a][1]) / (pts[b][0] - pts[a][0]) for a, b in zip(ltr, ltr[1:])
    ]  # slope[k] is the edge leaving ltr[k] to the right
    lk = next((k for k, s in enumerate(slope) if s <= t), None)
    rk = next((k + 1 for k in range(len(slope) - 1, -1, -1) if slope[k] >= -t), None)
    if lk is None or rk is None or lk >= rk:
        return points  # the chain already stands at least as steep as the limit
    lu, lv = pts[ltr[lk]]
    ru, rv = pts[ltr[rk]]
    xu = (rv - lv + t * (lu + ru)) / (2 * t)
    apex = (xu, lv + t * (xu - lu))
    new_chain = [pts[i] for i in ltr[: lk + 1]] + [apex] + [pts[i] for i in ltr[rk:]]
    rest = [pts[(chain[-1] + k) % n] for k in range(1, n - len(chain) + 1)]
    return _rot(new_chain[::-1] + rest, -rot)


def to_face(points: list[Point], plane: Plane = Plane.XZ) -> Face:
    """Planar face of the (u, v) outline on `plane`."""
    pts3 = [plane.origin + plane.x_dir * u + plane.y_dir * v for u, v in points]
    return Face(Wire.make_polygon([Vector(p) for p in pts3], close=True))


def opening(
    kind: ArchKind,
    span: float,
    rise: float,
    up: tuple[float, float] | None,
    *,
    plane: Plane = Plane.XZ,
    at: tuple[float, float] = (0, 0),
) -> Face:
    """An arch opening on `plane`: apex turned to `up`, roof clipped to 45°, centred at `at`."""
    pts = arch(kind, span, rise)
    if up is not None:
        rot = 90.0 - math.degrees(math.atan2(up[1], up[0]))
        pts = _rot(pts, -rot)  # apex +v -> up
    pts = clip_roof(pts, up)
    pts = [(u + at[0], v + at[1]) for u, v in pts]
    return to_face(pts, plane)
