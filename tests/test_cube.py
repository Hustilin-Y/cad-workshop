"""Этап 1: куб 20 мм собирается, проверки проходят, PNG создан."""

from build123d import Box, Pos

from cadlib.checks import check_mesh
from cadlib.config import load_profile
from cadlib.export import export_all
from cadlib.meshio import load_mesh
from cadlib.preview import render_preview


def test_cube_20mm(tmp_path):
    cube = Pos(0, 0, 10) * Box(20, 20, 20)
    files = export_all(cube, tmp_path, "cube")
    assert all(p.stat().st_size > 0 for p in files.values())

    profile = load_profile()
    for fmt in ("stl", "3mf", "step"):
        mesh = load_mesh(files[fmt])
        assert abs(mesh.volume - 8000) < 1, fmt
        report = check_mesh(mesh, profile)
        assert not report.failed, f"{fmt}:\n{report.format()}"
        assert not any(c.level == "warn" for c in report.checks), f"{fmt}:\n{report.format()}"

    png = render_preview(load_mesh(files["stl"]), tmp_path / "cube.png", "cube")
    assert png.stat().st_size > 10_000


def test_profile_nozzle_and_material():
    p = load_profile(nozzle=0.6, material="petg")
    assert p.min_wall_mm == 1.8
    assert p.hole_clearance_mm == 0.2 + 0.05
