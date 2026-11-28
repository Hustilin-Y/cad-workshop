import math

import pytest
from build123d import Plane

from cadlib.style.outline import arch, clip_roof, opening
from cadlib.style.plane import in_plane_up


def _max_roof_overhang_deg(pts):
    """Largest overhang (degrees from vertical) of the hole's roof, up = +v.

    A roof edge is one whose outward normal (pointing away from the hole's centroid) has v > 0;
    its overhang from vertical is the angle between that normal and the horizontal."""
    cu = sum(u for u, _ in pts) / len(pts)
    cv = sum(v for _, v in pts) / len(pts)
    worst = 0.0
    for (u0, v0), (u1, v1) in zip(pts, pts[1:] + pts[:1]):
        du, dv = u1 - u0, v1 - v0
        length = math.hypot(du, dv)
        if length < 1e-9:
            continue
        nu, nv = dv / length, -du / length
        if nu * ((u0 + u1) / 2 - cu) + nv * ((v0 + v1) / 2 - cv) < 0:
            nu, nv = -nu, -nv
        if nv > 0:
            worst = max(worst, math.degrees(math.asin(min(1.0, nv))))
    return worst


def test_steep_lancet_needs_no_clip():
    # The apex tangent of a pointed arch is steeper than 45 deg only from rise = span * (1 + sqrt 2) / 2.
    pts = arch("pointed", 20, 26)
    assert clip_roof(pts, (0, 1)) == pts


def test_equilateral_pointed_gets_45_cap():
    # Its apex tangents lie at 30 deg from horizontal, i.e. 60 deg overhang: the cap is needed.
    pts = arch("pointed", 20, 20 * math.sqrt(3) / 2)
    clipped = clip_roof(pts, (0, 1))
    assert clipped != pts
    assert _max_roof_overhang_deg(clipped) <= 45.0 + 1e-6


def test_catenary_gets_45_cap():
    clipped = clip_roof(arch("catenary", 30, 15), (0, 1))
    assert _max_roof_overhang_deg(clipped) <= 45.0 + 1e-6
    assert max(v for _, v in clipped) > 15.0  # the cap sits above the catenary apex


def test_circle_becomes_teardrop_when_up_sideways():
    clipped = clip_roof(arch("oval", 10, 10), (1, 0))
    assert max(u for u, _ in clipped) > 5.0  # tip grows towards +u
    assert _max_roof_overhang_deg([(-v, u) for u, v in clipped]) <= 45.0 + 1e-6  # turned so up is +v


def test_flat_plane_leaves_outline():
    pts = arch("round", 10, 5)
    assert clip_roof(pts, None) == pts


def test_opening_face_area():
    f = opening("round", 10, 5, None)
    assert f.area == pytest.approx(math.pi * 25 / 2, rel=0.01)


def test_non_convex_outline_rejected():
    with pytest.raises(ValueError, match="convex"):
        clip_roof([(0, 0), (4, 0), (2, 1), (4, 4), (0, 4)], (0, 1))


def test_drop_arch_is_convex_and_spans_base():
    pts = arch("pointed", 20, 10)
    assert min(u for u, _ in pts) == pytest.approx(-10) and max(u for u, _ in pts) == pytest.approx(10)
    assert max(v for _, v in pts) == pytest.approx(10)
    clip_roof(pts, (0, 1))  # raises when not convex


def test_xz_plane_maps_uv_to_xz():
    assert tuple(Plane.XZ.x_dir) == pytest.approx((1, 0, 0))
    assert tuple(Plane.XZ.y_dir) == pytest.approx((0, 0, 1))


def test_in_plane_up():
    assert in_plane_up(Plane.XZ, None) == pytest.approx((0, 1))
    assert in_plane_up(Plane.XZ, "-z") == pytest.approx((0, 1))
    assert in_plane_up(Plane.XZ, "-x") == pytest.approx((1, 0))
    assert in_plane_up(Plane.XY, "-z") is None
