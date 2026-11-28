"""Structural members as 2D faces in (u, v): tapered and curved beams, catenaries, trusses, ribs."""

from __future__ import annotations

import math

from build123d import Edge, Face, Plane, Solid, Vector, Wire
from scipy.optimize import brentq

from cadlib.config import Profile
from cadlib.style.outline import Point, to_face


def _check_wall(what: str, value: float, p: Profile) -> None:
    if value < p.min_wall_mm:
        raise ValueError(f"{what} {value:g} mm is below min_wall {p.min_wall_mm:g} mm")


def _at(plane: Plane, pt: Point) -> Vector:
    return Vector(plane.origin + plane.x_dir * pt[0] + plane.y_dir * pt[1])


def _unit(a: Point, b: Point) -> Point:
    d = math.hypot(b[0] - a[0], b[1] - a[1])
    if d < 1e-9:
        raise ValueError("member endpoints coincide")
    return ((b[0] - a[0]) / d, (b[1] - a[1]) / d)


def taper_beam(p0: Point, p1: Point, w0: float, w1: float, *, p: Profile, plane: Plane = Plane.XZ) -> Face:
    """Straight beam from p0 to p1, width linear from w0 to w1, flat ends square to the axis."""
    _check_wall("beam width", min(w0, w1), p)
    du, dv = _unit(p0, p1)
    nu, nv = -dv, du
    pts = [
        (p0[0] + nu * w0 / 2, p0[1] + nv * w0 / 2),
        (p1[0] + nu * w1 / 2, p1[1] + nv * w1 / 2),
        (p1[0] - nu * w1 / 2, p1[1] - nv * w1 / 2),
        (p0[0] - nu * w0 / 2, p0[1] - nv * w0 / 2),
    ]
    return to_face(pts, plane)


def curved_beam(centre: list[Point], widths: list[float], *, p: Profile, plane: Plane = Plane.XZ) -> Face:
    """Beam along a spline through `centre`, with `widths[i]` at point i. Both sides are splines."""
    if len(centre) < 3 or len(centre) != len(widths):
        raise ValueError("curved_beam needs at least 3 centre points and one width per point")
    _check_wall("beam width", min(widths), p)
    left: list[Point] = []
    right: list[Point] = []
    for i, (c, w) in enumerate(zip(centre, widths)):
        du, dv = _unit(centre[max(i - 1, 0)], centre[min(i + 1, len(centre) - 1)])
        left.append((c[0] - dv * w / 2, c[1] + du * w / 2))
        right.append((c[0] + dv * w / 2, c[1] - du * w / 2))
    side_a = Edge.make_spline([_at(plane, q) for q in left])
    side_b = Edge.make_spline([_at(plane, q) for q in reversed(right)])
    cap_end = Edge.make_line(_at(plane, left[-1]), _at(plane, right[-1]))
    cap_start = Edge.make_line(_at(plane, right[0]), _at(plane, left[0]))
    return Face(Wire([side_a, cap_end, side_b, cap_start]))


def catenary(p0: Point, p1: Point, sag: float, n: int = 32) -> list[Point]:
    """n + 1 points from p0 to p1 on a catenary hanging `sag` below the chord at its midpoint.

    "Below" is -v. The curve is a level-chord catenary sheared onto the chord, so for a sloped
    chord the vertical drop below the chord is `sag` at the middle.
    """
    if sag <= 0 or n < 2:
        raise ValueError("catenary needs sag > 0 and n >= 2")
    du, dv = p1[0] - p0[0], p1[1] - p0[1]
    if abs(du) < 1e-9:
        raise ValueError("catenary endpoints must differ in u")
    half = abs(du) / 2
    # sag = a (cosh(half / a) - 1)
    a = brentq(lambda a: a * (math.cosh(half / a) - 1) - sag, half / 50, 1e5 * half)
    pts = []
    for i in range(n + 1):
        t = i / n
        x = (t - 0.5) * abs(du)
        drop = a * (math.cosh(x / a) - math.cosh(half / a))  # 0 at the ends, -sag in the middle
        pts.append((p0[0] + du * t, p0[1] + dv * t + drop))
    return pts


def _disc(plane: Plane, centre: Point, d: float) -> Face:
    # Beams wind clockwise in (u, v), so the discs face the opposite way to fuse cleanly.
    return Face(Wire.make_circle(d / 2, Plane(origin=_at(plane, centre), z_dir=-plane.z_dir)))


def _fuse_one(parts: list[Face], what: str) -> Face:
    fused = parts[0]
    for f in parts[1:]:
        fused = fused + f
    faces = fused.clean().faces()
    if len(faces) != 1:
        raise ValueError(f"{what} is not one connected piece ({len(faces)} pieces)")
    return faces[0]


def truss(
    nodes: list[Point],
    members: list[tuple[int, int]],
    bar: float,
    node_d: float,
    *,
    p: Profile,
    plane: Plane = Plane.XZ,
) -> Face:
    """Bars of width `bar` between node indices, with a disc of diameter `node_d` at every node used.

    Bars and discs are fused into one Face, so the members must form a connected frame.
    """
    _check_wall("truss bar", bar, p)
    _check_wall("truss node", node_d, p)
    if not members:
        raise ValueError("truss needs at least one member")
    parts: list[Face] = [taper_beam(nodes[a], nodes[b], bar, bar, p=p, plane=plane) for a, b in members]
    for i in sorted({i for m in members for i in m}):
        parts.append(_disc(plane, nodes[i], node_d))
    return _fuse_one(parts, "truss")


def rib(path: list[Point], width: float, height: float, plane: Plane, *, p: Profile) -> Solid:
    """A rib of `width` along the (u, v) `path` on `plane`, raised `height` along the plane normal.

    Segments are flat-ended bars, so the rib is exactly as long as its path. Interior corners get
    a round join of diameter `width`.
    """
    _check_wall("rib width", width, p)
    if height <= 0 or len(path) < 2:
        raise ValueError("rib needs height > 0 and at least 2 path points")
    parts = [taper_beam(a, b, width, width, p=p, plane=plane) for a, b in zip(path, path[1:])]
    parts += [_disc(plane, q, width) for q in path[1:-1]]
    return Solid.extrude(_fuse_one(parts, "rib"), plane.z_dir * height)
