"""Disc magnets: nominal sizes, the pocket tool and its fit from the profile."""

import math

import numpy as np
import pytest
from build123d import Box, Pos

from cadlib import magnets as mg
from cadlib.config import load_profile
from cadlib.export import shape_to_mesh
from cadlib.preview import section_loops

P = load_profile()


@pytest.mark.parametrize("text,d,h", [("5x4", 5, 4), ("10x3", 10, 3), ("6×2", 6, 2), ("5х4", 5, 4), (" 8 x 2 ", 8, 2)])
def test_parse_sizes(text, d, h):
    m = mg.magnet(text)
    assert (m.d, m.h) == (d, h)


@pytest.mark.parametrize("text", ["5", "x4", "0x2", "5x0", "abc", "-5x2"])
def test_bad_sizes(text):
    with pytest.raises(ValueError, match="DxH"):
        mg.magnet(text)


def test_catalogue_up_to_10x3():
    sizes = [mg.magnet(s) for s in mg.CATALOGUE]
    assert "5x4" in mg.CATALOGUE and "6x2" in mg.CATALOGUE and "10x3" in mg.CATALOGUE
    assert max(m.d for m in sizes) == 10 and max(m.h for m in sizes) <= 4


def test_pocket_depth_covers_the_tolerance():
    for s in mg.CATALOGUE:
        m = mg.magnet(s)
        depth = mg.pocket_depth(m, P)
        assert depth >= m.h + mg.TOLERANCE_MM - 1e-9                 # a +0.1 magnet stays flush
        assert depth < m.h + mg.TOLERANCE_MM + P.layer_mm + 1e-9
        assert math.isclose(depth / P.layer_mm, round(depth / P.layer_mm), abs_tol=1e-6)


def test_pocket_tool_size_and_place():
    m = mg.magnet("6x2")
    tool = mg.pocket(m, P)
    bb = tool.bounding_box()
    assert bb.max.Z > 0 and bb.min.Z == pytest.approx(-mg.pocket_depth(m, P), abs=0.01)
    body = Pos(0, 0, -5) * Box(20, 20, 10) - tool
    loops = section_loops(shape_to_mesh(body), "z", -1.0)
    hole = min(loops, key=lambda lp: np.ptp(lp[:, 0]))
    assert np.ptp(hole[:, 0]) == pytest.approx(6 + P.magnet_fit_mm, abs=0.03)


def test_pocket_follows_the_profile():
    petg = load_profile(material="PETG")
    m = mg.magnet("10x3")
    assert mg.pocket(m, petg).bounding_box().size.X == pytest.approx(10 + petg.magnet_fit_mm, abs=0.02)
