"""cadlib.finish: edge roundings and chamfers, falling back to half the size when OCCT refuses."""

import math

import pytest
from build123d import Axis, Box, Pos

from cadlib.finish import bevel, soften

W, D, H = 20.0, 20.0, 10.0


def block():
    return (Pos(0, 0, H / 2) * Box(W, D, H)).solids()[0]


def vertical_edges(body):
    return body.edges().filter_by(Axis.Z)


def corner(r):
    """The area a rounding of radius r takes off a right angle."""
    return r * r * (1 - math.pi / 4)


def test_soften_vertical_edges():
    body, done = soften(block(), vertical_edges(block()), 2.0)
    assert done == 4 and body.is_valid
    assert body.volume == pytest.approx(W * D * H - 4 * corner(2.0) * H, rel=1e-4)


def test_soften_falls_back_to_half_radius():
    # 12 + 12 > 20: neighbouring roundings don't fit at the full radius, 6 does
    body, done = soften(block(), vertical_edges(block()), 12.0)
    assert done == 4
    assert body.volume == pytest.approx(W * D * H - 4 * corner(6.0) * H, rel=1e-4)


def test_bevel_bottom_edges():
    b = block()
    bottom = b.edges().group_by(Axis.Z)[0]
    body, done = bevel(b, bottom, 0.6)
    assert done == 4 and body.is_valid
    removed = W * D * H - body.volume
    # a 0.6 × 0.6 chamfer round the bottom: ≈ perimeter × s²/2 (a little less at the corners)
    assert removed == pytest.approx(2 * (W + D) * 0.6 * 0.6 / 2, rel=0.03)


def test_impossible_rounding_leaves_the_part_alone():
    b = block()
    body, done = soften(b, vertical_edges(b), 40.0)   # both 40 and 20 are over half the side
    assert done == 0 and body.volume == pytest.approx(W * D * H)
