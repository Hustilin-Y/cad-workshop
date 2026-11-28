"""Printed joints: a dovetail tenon with a snap detent and the matching socket tool.

Print orientation the joint assumes: the slide axis (+Y of the local frame) is vertical in print.
The trapezoid then lies in a horizontal plane, so every flank is a vertical wall and the detent
bump is the only sloped surface (its slope stays within 45° of vertical). Print the socket with
its closed end (the stop wall, y = length) on the bed and the mouth (y = 0) up: a closed end on
top would be a 12 mm bridge, longer than the 10 mm bridge limit. The tenon may stand on either end.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Plane, Polygon, Pos, Solid, Sphere, extrude

from cadlib.checks import OVERHANG_DEG
from cadlib.config import Profile

_EPS = 0.01
_OVERSHOOT = 1.0  # the socket tool runs this far past the open faces (x = 0 and y = 0) for a clean cut
_FLANK = math.tan(math.radians(OVERHANG_DEG))


@dataclass(frozen=True)
class DovetailSpec:
    """Rhombus tenon: from the neck (at x = 0) it widens at the flank angle to `wide`, runs flat, and narrows to the neck."""

    length: float  # along the slide (Y)
    neck: float = 8.0  # width (Z) at the root and at the tip
    wide: float = 12.0  # width (Z) of the flat part
    depth: float = 8.0  # tenon height (X)
    stop: float = 3.0  # wall the caller leaves closing the socket at the far end
    detent: float = 0.4  # bump height above the wide flank
    detent_r: float = 1.4  # bump sphere radius


def _run(spec: DovetailSpec) -> float:
    """X distance over which the width changes from the neck to wide (45° flank)."""
    return (spec.wide - spec.neck) / 2 / _FLANK


def _validate(spec: DovetailSpec, p: Profile) -> None:
    if spec.wide <= spec.neck:
        raise ValueError(f"wide {spec.wide:g} mm must exceed neck {spec.neck:g} mm")
    run = _run(spec)
    if spec.depth < 2 * run:
        raise ValueError(
            f"depth {spec.depth:g} mm is too short: flanks steeper than {OVERHANG_DEG:g} deg, "
            f"need at least {2 * run:g} mm for neck {spec.neck:g} and wide {spec.wide:g}"
        )
    if spec.neck < 2 * p.min_wall_mm:
        raise ValueError(f"neck {spec.neck:g} mm is below two min_wall ({2 * p.min_wall_mm:g} mm)")
    if spec.stop < p.min_wall_mm:
        raise ValueError(f"stop {spec.stop:g} mm is below min_wall {p.min_wall_mm:g} mm")
    if spec.detent > 0:
        if spec.detent > spec.detent_r * (1 - math.cos(math.radians(OVERHANG_DEG))) + 1e-9:
            raise ValueError(
                f"detent {spec.detent:g} mm is too tall for radius {spec.detent_r:g} mm: its slope exceeds {OVERHANG_DEG:g} deg"
            )
        footprint = 2 * math.sqrt(spec.detent_r**2 - (spec.detent_r - spec.detent) ** 2)
        if footprint + 2 * p.slide_fit_mm > spec.depth - 2 * run or footprint > spec.length:
            raise ValueError("detent does not fit on the flat flank or along the tenon")


def _profile(spec: DovetailSpec, root: float = _EPS) -> list[tuple[float, float]]:
    """Closed outline in (x, z), starting `root` inside the mating face (x = 0) at neck width for a clean fuse."""
    n, w, run, d = spec.neck / 2, spec.wide / 2, _run(spec), spec.depth
    return [(-root, -n), (0, -n), (run, -w), (d - run, -w), (d, -n), (d, n), (d - run, w), (run, w), (0, n), (-root, n)]


def _socket_profile(spec: DovetailSpec, clear: float) -> list[tuple[float, float]]:
    """Tenon outline pushed out by `clear` along every flank (true clearance on slopes too), open through x = 0."""
    import manifold3d as mf

    pts = _profile(spec, _OVERSHOOT)
    cs = mf.CrossSection([pts], mf.FillRule.Positive)
    if cs.area() == 0:
        cs = mf.CrossSection([pts[::-1]], mf.FillRule.Positive)
    return [tuple(v) for v in cs.offset(clear, mf.JoinType.Miter, 2.0).to_polygons()[0]]


def _xz_prism(points, y0: float, y1: float) -> Solid:
    """Prism over a polygon in the XZ plane, spanning y0..y1."""
    face = Plane.XZ * Polygon(*points, align=None)  # local y of Plane.XZ is world Z
    solid = extrude(face, amount=y1 - y0)
    return Pos(0, y0 - solid.bounding_box().min.Y, 0) * solid  # extrusion direction follows the normal: align by fact


def _detent_center(spec: DovetailSpec) -> tuple[float, float, float]:
    """Sphere centre: mid-length, mid-flat, inside the +Z wide flank so that `detent` of it protrudes."""
    return (spec.depth / 2, spec.length / 2, spec.wide / 2 - (spec.detent_r - spec.detent))


def dovetail(spec: DovetailSpec, p: Profile) -> tuple[Solid, Solid]:
    """(tenon, socket_tool) in a local frame.

    The tenon grows from x = 0 towards +x and slides along +Y over y = 0..length, trapezoid in XZ centred on z = 0.
    The socket tool is the tenon grown by p.slide_fit_mm on every flank and the tip, open at y = 0 and x = 0,
    closed at y = length + slide_fit_mm (leave `stop` of material beyond that end). A half-sphere bump on the
    +Z wide flank at mid-length snaps into a matching dimple in the tool.
    """
    _validate(spec, p)
    fit = p.slide_fit_mm
    tenon = _xz_prism(_profile(spec), 0.0, spec.length)
    tool = _xz_prism(_socket_profile(spec, fit), -_OVERSHOOT, spec.length + fit)
    if spec.detent > 0:
        cx, cy, cz = _detent_center(spec)
        tenon += Pos(cx, cy, cz) * Sphere(spec.detent_r)
        tool += Pos(cx, cy, cz) * Sphere(spec.detent_r + fit)  # protrudes `detent` past the socket flank too
    return tenon, tool
