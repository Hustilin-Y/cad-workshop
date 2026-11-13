"""Stage 3: fastener tools have the right sizes and follow the profile."""

import math

import numpy as np
import pytest
from build123d import Box, Pos

from cadlib import fasteners as f
from cadlib.config import load_profile
from cadlib.export import shape_to_mesh
from cadlib.preview import section_loops

P = load_profile()


def _hole_diameters(part, z):
    """Diameters (along X) of every contour of the body's section by the plane Z=z."""
    loops = section_loops(shape_to_mesh(part), "z", z)
    return sorted(round(float(np.ptp(loop[:, 0])), 2) for loop in loops)


def _block_minus(tool, top=10.0):
    return Pos(0, 0, top / 2) * Box(30, 30, top) - Pos(0, 0, top) * tool


@pytest.mark.parametrize("size", list(f.METRIC))
def test_clearance_hole_diameter(size):
    expected = f.METRIC[size].clear_fine + P.hole_clearance_mm
    body = _block_minus(f.clearance_hole(size, 10, P))
    assert _hole_diameters(body, 5)[0] == pytest.approx(expected, abs=0.05)


def test_counterbore_m4():
    m = f.METRIC["M4"]
    body = _block_minus(f.counterbore_hole("M4", 10, P))
    assert _hole_diameters(body, 9.5)[0] == pytest.approx(m.cbore_d + P.hole_clearance_mm, abs=0.05)
    assert _hole_diameters(body, 3)[0] == pytest.approx(m.clear_fine + P.hole_clearance_mm, abs=0.05)


def test_countersunk_is_90_degrees():
    m = f.METRIC["M3"]
    head = m.csk_d + P.hole_clearance_mm
    body = _block_minus(f.countersunk_hole("M3", 10, P))
    # At 0.5 mm deep a 90° cone is already 1 mm (2 × 0.5) narrower than the head.
    assert _hole_diameters(body, 9.5)[0] == pytest.approx(head - 1.0, abs=0.08)


def test_nut_pocket_across_flats_and_slot():
    m = f.METRIC["M3"]
    s = m.nut_s + P.slide_fit_mm
    body = _block_minus(f.nut_pocket("M3", P))
    loops = section_loops(shape_to_mesh(body), "z", 9)
    hexagon = min(loops, key=lambda loop: np.ptp(loop[:, 0]))
    assert np.ptp(hexagon[:, 1]) == pytest.approx(s, abs=0.05)                 # across flats: along Y
    assert np.ptp(hexagon[:, 0]) == pytest.approx(2 * s / math.sqrt(3), abs=0.05)  # across corners: along X

    slotted = _block_minus(f.nut_pocket("M3", P, slot=20))
    assert slotted.volume < body.volume


def test_insert_hole_depth_and_override():
    tool = f.insert_hole("M3", P, hole_d=4.2, length=5.0)
    lo = tool.bounding_box().min
    assert lo.Z == pytest.approx(-6.0, abs=0.02)          # length + 1 mm spare
    body = _block_minus(tool)
    assert _hole_diameters(body, 6)[0] == pytest.approx(4.2, abs=0.05)


def test_wood_screw_countersink():
    body = _block_minus(f.wood_screw_countersunk_hole(6.0, 10, P))
    assert _hole_diameters(body, 5)[0] == pytest.approx(6.0 + f.WOOD_SCREW_CLEARANCE + P.hole_clearance_mm, abs=0.05)
    # At 1 mm deep a 90° cone is 2 mm narrower than the Ø12 head (+ clearance).
    assert _hole_diameters(body, 9)[0] == pytest.approx(12.0 + P.hole_clearance_mm - 2.0, abs=0.08)
    with pytest.raises(ValueError, match="head_d"):
        f.wood_screw_countersunk_hole(7.0, 10, P)


def test_unknown_size():
    with pytest.raises(ValueError, match="M6"):
        f.clearance_hole("M6", 5, P)
