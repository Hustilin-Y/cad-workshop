"""cadlib.threads: the turns merge into one body, the profile and volume are right."""

import math

import numpy as np
import pytest
from build123d import Pos, Sphere

from cadlib.export import export_all, shape_to_mesh
from cadlib.meshio import load_mesh
from cadlib.preview import section_loops
from cadlib.threads import ISO_THREAD_H, internal_thread_tube, minor_diameter


@pytest.mark.parametrize("major_d, pitch, length", [(38.35, 4.0, 10.0), (38.35, 4.0, 50.0), (12.3, 1.75, 15.0)])
def test_internal_thread_tube_is_one_solid_with_ridges(major_d, pitch, length):
    outer = major_d + 10
    tube = internal_thread_tube(outer, major_d, pitch, length)
    plain = math.pi * ((outer / 2) ** 2 - (major_d / 2) ** 2) * length
    # The turns take about (7P/8 + P/4)/2 · h per pitch around the mean-radius circle.
    h = ISO_THREAD_H * pitch
    ridge_per_mm = (0.875 + 0.25) / 2 * pitch * h * 2 * math.pi * (major_d / 2 - h / 2) / pitch
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


def test_sphere_export_has_no_degenerate_triangles(tmp_path):
    files = export_all(Pos(0, 0, 20) * Sphere(20), tmp_path, "ball", ("stl", "3mf"))
    for fmt in ("stl", "3mf"):
        mesh = load_mesh(files[fmt])
        assert mesh.is_watertight and len(mesh.split(only_watertight=False)) == 1
        assert np.all(mesh.area_faces > 1e-10)
