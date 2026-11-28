from dataclasses import replace

import numpy as np
import pytest

from cadlib.config import load_profile
from cadlib.export import shape_to_mesh
from cadlib.style.joints import DovetailSpec, dovetail
from style_checks import steep_overhang_area

P = load_profile()
SPEC = DovetailSpec(length=30.0)
Y_SECTION = SPEC.length / 4  # clear of the detent at mid-length


def _section(solid):
    return shape_to_mesh(solid).section(plane_origin=[0, Y_SECTION, 0], plane_normal=[0, 1, 0])


def _extent(solid, axis):
    return float(_section(solid).vertices[:, axis].max())


def _dist_to_segments(pt, segments):
    best = np.inf
    for line in segments:
        for a, b in zip(line[:-1], line[1:]):
            ab = b - a
            t = np.clip(np.dot(pt - a, ab) / np.dot(ab, ab), 0, 1)
            best = min(best, float(np.linalg.norm(a + t * ab - pt)))
    return best


def test_tenon_fits_socket_tool():
    for spec in (SPEC, replace(SPEC, detent=0.0)):
        tenon, tool = dovetail(spec, P)
        assert tenon.is_valid and tool.is_valid
        assert (tenon - tool).volume < 1e-6
        assert tool.volume > tenon.volume


def test_gap_equals_slide_fit():
    tenon, tool = dovetail(SPEC, P)
    # section width on the wide flat flank (Z) and at the tip (X)
    assert _extent(tool, 2) - _extent(tenon, 2) == pytest.approx(P.slide_fit_mm, abs=0.01)
    assert _extent(tool, 0) - _extent(tenon, 0) == pytest.approx(P.slide_fit_mm, abs=0.01)
    # perpendicular gap on the 45 degree flank: from its midpoint to the tool wall
    run = (SPEC.wide - SPEC.neck) / 2
    mid = np.array([run / 2, Y_SECTION, SPEC.neck / 2 + run / 2])
    assert _dist_to_segments(mid, _section(tool).discrete) == pytest.approx(P.slide_fit_mm, abs=0.01)


def test_socket_open_at_mouth_closed_at_stop():
    _, tool = dovetail(SPEC, P)
    bb = tool.bounding_box()
    assert bb.max.Y == pytest.approx(SPEC.length + P.slide_fit_mm, abs=1e-6)
    assert bb.min.Y < 0 and bb.min.X < 0  # runs past the open faces


def test_detent_bump_and_dimple():
    tenon, tool = dovetail(SPEC, P)
    bare, bare_tool = dovetail(replace(SPEC, detent=0.0), P)
    assert tenon.bounding_box().max.Z == pytest.approx(SPEC.wide / 2 + SPEC.detent, abs=1e-3)
    assert bare.bounding_box().max.Z == pytest.approx(SPEC.wide / 2, abs=1e-3)
    assert tool.bounding_box().max.Z == pytest.approx(SPEC.wide / 2 + P.slide_fit_mm + SPEC.detent, abs=1e-3)
    assert tenon.volume > bare.volume and tool.volume > bare_tool.volume


def test_steep_flank_rejected():
    with pytest.raises(ValueError, match="steeper than 45"):
        dovetail(replace(SPEC, depth=3.0), P)


def test_thin_neck_rejected_for_wide_nozzle():
    p08 = load_profile(nozzle=0.8)
    assert p08.min_wall_mm == pytest.approx(2.4)
    dovetail(SPEC, P)  # the default 8 mm neck is fine
    with pytest.raises(ValueError, match="neck 4 mm"):
        dovetail(replace(SPEC, neck=4.0, wide=6.0), p08)


def test_thin_stop_and_tall_detent_rejected():
    with pytest.raises(ValueError, match="stop"):
        dovetail(replace(SPEC, stop=P.min_wall_mm / 2), P)
    with pytest.raises(ValueError, match="detent"):
        dovetail(replace(SPEC, detent=1.0), P)


def test_prints_without_overhangs_with_slide_axis_vertical():
    tenon, tool = dovetail(SPEC, P)
    # print_down "-y": the y = 0 face on the bed. Tool: closed end (y = length) on the bed, mouth up.
    assert steep_overhang_area(shape_to_mesh(tenon), "-y", P.max_bridge_mm) <= 1.0
    assert steep_overhang_area(shape_to_mesh(tool), "+y", P.max_bridge_mm) <= 1.0
