"""cadlib.threads: the turns merge into one body, the profile and volume are right."""

import math

import numpy as np
import pytest
from build123d import Pos, Rot, Sphere

from cadlib.export import export_all, shape_to_mesh
from cadlib.meshio import load_mesh
from cadlib.preview import section_loops
from cadlib.checks import overhang_fraction
from cadlib.threads import ISO_THREAD_H, external_thread_rod, internal_thread_tube, minor_diameter, thread_height


def test_printable_profile_height():
    assert thread_height(3.0, None) == pytest.approx(ISO_THREAD_H * 3.0)
    # root 7P/8, crest P/8, flanks tan45 + tan30
    assert thread_height(3.0) == pytest.approx(0.75 * 3.0 / (1 + math.tan(math.radians(30))))
    assert thread_height(3.0, +1) == pytest.approx(thread_height(3.0, -1))
    with pytest.raises(ValueError):
        thread_height(3.0, 0)


@pytest.mark.parametrize("major_d, pitch, length, down", [(38.35, 4.0, 10.0, None), (38.35, 4.0, 50.0, -1),
                                                          (12.3, 1.75, 15.0, -1), (12.3, 1.75, 15.0, +1)])
def test_internal_thread_tube_is_one_solid_with_ridges(major_d, pitch, length, down):
    outer = major_d + 10
    tube = internal_thread_tube(outer, major_d, pitch, length, down)
    plain = math.pi * ((outer / 2) ** 2 - (major_d / 2) ** 2) * length
    # The turns take about (7P/8 + crest)/2 · h per pitch around the mean-radius circle.
    h = thread_height(pitch, down)
    crest = 0.25 if down is None else 0.125
    ridge_per_mm = (0.875 + crest) / 2 * pitch * h * 2 * math.pi * (major_d / 2 - h / 2) / pitch
    assert tube.is_valid
    assert tube.volume == pytest.approx(plain + ridge_per_mm * length, rel=0.03)
    bb = tube.bounding_box()
    assert bb.min.Z == pytest.approx(0, abs=1e-6) and bb.max.Z == pytest.approx(length, abs=1e-6)


def test_thread_profile_in_section():
    tube = internal_thread_tube(48, 38.35, 4.0, 20)
    loops = section_loops(shape_to_mesh(tube), "y", 0.0)
    inner_x = np.concatenate([loop[:, 0] for loop in loops])
    inner_x = np.abs(inner_x[np.abs(inner_x) < 23])
    assert inner_x.min() == pytest.approx(minor_diameter(38.35, 4.0) / 2, abs=0.05)   # thread crests
    assert inner_x.max() == pytest.approx(38.35 / 2, abs=0.05)                       # bottom of the grooves = the wall


@pytest.mark.parametrize("major_d, pitch, length, down", [(46.0, 3.0, 6.0, None), (46.0, 3.0, 6.0, -1),
                                                          (12.0, 1.75, 15.0, -1)])
def test_external_thread_rod_is_one_solid_with_ridges(major_d, pitch, length, down):
    rod = external_thread_rod(major_d, pitch, length, down)
    core = math.pi * (minor_diameter(major_d, pitch, down) / 2) ** 2 * length
    h = thread_height(pitch, down)
    root = 0.75 if down is None else 0.875
    ridge_per_mm = (root + 0.125) / 2 * pitch * h * 2 * math.pi * (major_d / 2 - h / 2) / pitch
    assert rod.is_valid
    assert rod.volume == pytest.approx(core + ridge_per_mm * length, rel=0.03)
    bb = rod.bounding_box()
    assert bb.min.Z == pytest.approx(0, abs=1e-6) and bb.max.Z == pytest.approx(length, abs=1e-6)
    assert bb.max.X == pytest.approx(major_d / 2, abs=0.05)


def _clash(rod_down, nut_down) -> float:
    # Both helices start at the same angle; screwed together they meet half a turn apart.
    rod = Rot(0, 0, 180) * external_thread_rod(46.0, 3.0, 6.0, rod_down)
    nut = internal_thread_tube(52.0, 46.0 + 0.3, 3.0, 6.0, nut_down)
    clash = rod & nut
    return 0.0 if clash is None else sum(s.volume for s in clash.solids())


@pytest.mark.parametrize("rod_down, nut_down", [(None, None), (None, -1), (None, +1), (-1, +1), (+1, -1)])
def test_external_thread_fits_internal_with_clearance(rod_down, nut_down):
    # A printable nut fits an ISO (metal) bolt either way up; a printed pair faces its 45° flanks at each other.
    assert _clash(rod_down, nut_down) < 1e-3


def test_printed_pair_with_45_flanks_on_the_same_side_clashes():
    assert _clash(-1, -1) > 1.0


@pytest.mark.parametrize("down, steep", [(None, True), (-1, False)])
def test_printable_turns_have_no_steep_overhangs(down, steep):
    # Printed as modelled, ISO flanks facing the bed are 60° from vertical; the printable ones are 45°.
    mesh = shape_to_mesh(internal_thread_tube(20.0, 12.3, 1.75, 10.0, down))
    frac = overhang_fraction(mesh, 50.0)
    assert (frac > 0.05) if steep else (frac < 0.005)


def test_sphere_export_has_no_degenerate_triangles(tmp_path):
    files = export_all(Pos(0, 0, 20) * Sphere(20), tmp_path, "ball", ("stl", "3mf"))
    for fmt in ("stl", "3mf"):
        mesh = load_mesh(files[fmt])
        assert mesh.is_watertight and len(mesh.split(only_watertight=False)) == 1
        assert np.all(mesh.area_faces > 1e-10)
