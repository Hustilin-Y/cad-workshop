"""Workflow features: orientation finder, print-ready export, weight estimate, --set, build --all."""

from pathlib import Path

import numpy as np
import pytest
import trimesh

import cad
from cad import main
from cadlib.config import load_profile
from cadlib.estimate import estimate
from cadlib.meshio import load_mesh
from cadlib.orient import rank_orientations

MUSHROOM = (
    "from build123d import Box, Pos\n"
    'NAME = "shroom"\n'
    'PRINT_DOWN = "+z"\n'
    "def build(p):\n"
    "    return Pos(0, 0, 10) * Box(6, 6, 20) + Pos(0, 0, 22.5) * Box(60, 60, 5)\n"
)


def write_model(folder: Path, text: str) -> Path:
    folder.mkdir(parents=True)
    (folder / "model.py").write_text(text, encoding="utf-8")
    return folder


# --- orientation ----------------------------------------------------------------


def standing_plate(tmp_path) -> Path:
    plate = trimesh.creation.box((80, 4, 50))
    plate.apply_translation((0, 0, 25))
    path = tmp_path / "plate.stl"
    plate.export(path)
    return path


def test_orient_lays_a_standing_plate_flat(tmp_path, capsys):
    path = standing_plate(tmp_path)
    ranked = rank_orientations(load_mesh(path), load_profile())
    assert ranked[0].label in ("+Y", "-Y") and ranked[0].height_mm == pytest.approx(4.0)
    assert main(["orient", str(path), "--top", "2"]) == 0
    out = capsys.readouterr().out
    assert 'Best: PRINT_DOWN = "+y"' in out or 'Best: PRINT_DOWN = "-y"' in out
    assert (tmp_path / "out" / "plate-orient-1.png").stat().st_size > 0


def test_orient_prefers_the_cap_of_a_mushroom(tmp_path):
    folder = write_model(tmp_path / "m", MUSHROOM.replace('PRINT_DOWN = "+z"\n', ""))
    assert main(["build", str(folder)]) == 0
    best = rank_orientations(load_mesh(folder / "out" / "shroom.stl"), load_profile())[0]
    assert best.label == "+Z" and not best.notes


def test_print_ready_export_turns_mesh_files_only(tmp_path, capsys):
    folder = write_model(tmp_path / "shroom", MUSHROOM)
    assert main(["build", str(folder), "--print-ready"]) == 0
    assert "print-ready: STL/3MF turned with +Z on the bed" in capsys.readouterr().out
    for ext in ("stl", "3mf"):
        mesh = load_mesh(folder / "out" / f"shroom.{ext}")
        assert mesh.bounds[0][2] == pytest.approx(0, abs=1e-6)
        bottom = mesh.vertices[:, 2] < 0.01
        assert np.ptp(mesh.vertices[bottom][:, 0]) == pytest.approx(60, abs=0.01)  # the cap is on the bed
    from build123d import import_step

    step = import_step(folder / "out" / "shroom.step")
    assert step.bounding_box().min.Z == pytest.approx(0, abs=1e-3)  # STEP stays as designed: stem down
    assert step.bounding_box().max.Z == pytest.approx(25, abs=1e-3)


# --- weight -----------------------------------------------------------------------


def test_weight_of_a_20mm_cube():
    cube = trimesh.creation.box((20, 20, 20))
    est = estimate(cube, load_profile(material="PLA"))
    assert est.solid_g == pytest.approx(8.0 * 1.24, rel=1e-6)
    assert 3.0 < est.printed_g < 6.0   # a slicer says about 4 g at 15% infill
    assert est.cost is None


def test_weight_cost_with_a_spool_price(tmp_path):
    from cadlib.config import PRINTER_TOML

    text = PRINTER_TOML.read_text(encoding="utf-8").replace(
        "density_g_cm3 = 1.24\n", "density_g_cm3 = 1.24\nprice_per_kg = 1000\n", 1
    )
    toml = tmp_path / "printer.toml"
    toml.write_text(text, encoding="utf-8")
    profile = load_profile(material="PLA", path=toml)
    est = estimate(trimesh.creation.box((20, 20, 20)), profile)
    assert est.cost == pytest.approx(est.printed_g, rel=1e-6)   # 1000 per kg = 1 per gram
    assert est.summary(profile).endswith(f"≈ {est.cost:.0f} UAH")


def test_check_reports_weight(tmp_path, capsys):
    assert main(["check", str(standing_plate(tmp_path))]) == 0
    assert "[INFO] Weight: ≈" in capsys.readouterr().out


# --- --set --------------------------------------------------------------------------


PLATE = (
    "from build123d import Box, Pos\n"
    "WIDTH = 40.0\n"
    "def build(p):\n"
    "    return Pos(0, 0, 2) * Box(WIDTH, 20, 4)\n"
)


def test_set_overrides_a_parameter_for_one_run(tmp_path, capsys):
    folder = write_model(tmp_path / "plate", PLATE)
    assert main(["build", str(folder), "--set", "WIDTH=55"]) == 0
    assert "set WIDTH = 55 (was 40.0)" in capsys.readouterr().out
    assert load_mesh(folder / "out" / "plate.stl").extents[0] == pytest.approx(55)
    assert "WIDTH = 40.0" in (folder / "model.py").read_text(encoding="utf-8")   # the file is untouched


def test_set_rejects_unknown_names(tmp_path, capsys):
    folder = write_model(tmp_path / "plate", PLATE)
    assert main(["build", str(folder), "--set", "LENGTH=5"]) == 2
    assert main(["build", str(folder), "--set", "WIDTH"]) == 2
    out = capsys.readouterr().out
    assert "no parameter LENGTH" in out and "expected NAME=VALUE" in out


def test_set_on_a_shared_module_is_undone_after_the_run(tmp_path):
    shared = tmp_path / "common" / "sizes.py"
    shared.parent.mkdir()
    shared.write_text("SIDE = 10.0\n", encoding="utf-8")
    folder = write_model(tmp_path / "cube", (
        "from pathlib import Path\n"
        "from build123d import Box, Pos\n"
        "from cadlib.shared import load_module\n"
        "sizes = load_module(Path(__file__).resolve().parent.parent / 'common' / 'sizes.py')\n"
        "def build(p):\n"
        "    return Pos(0, 0, sizes.SIDE / 2) * Box(sizes.SIDE, sizes.SIDE, sizes.SIDE)\n"
    ))
    assert main(["build", str(folder), "--set", "sizes.SIDE=14"]) == 0
    assert load_mesh(folder / "out" / "cube.stl").extents[2] == pytest.approx(14)
    module = cad.load_model(folder)
    assert module.sizes.SIDE == 10.0


# --- build --all ----------------------------------------------------------------------


def test_build_all_reports_each_model(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cad, "ROOT", tmp_path)
    write_model(tmp_path / "calibration", PLATE)
    write_model(tmp_path / "parts" / "good", PLATE)
    write_model(tmp_path / "parts" / "broken", "def build(p):\n    raise ValueError('wall too thin')\n")
    (tmp_path / "parts" / "notes").mkdir()   # a folder without a model is skipped
    assert main(["build", "--all"]) == 1
    out = capsys.readouterr().out
    assert "== building 3 models" in out
    assert "good" in out and "broken" in out and "wall too thin" in out
    assert "2 of 3 built, 1 failed" in out


def test_build_all_skips_logo_parts_without_logo_data(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cad, "ROOT", tmp_path)
    write_model(tmp_path / "parts" / "good", PLATE)
    write_model(tmp_path / "parts" / "plaque", (
        "from cadlib.logo import LogoMissing\n"
        "def build(p):\n"
        "    raise LogoMissing('no logo data')\n"
    ))
    assert main(["build", "--all"]) == 0
    out = capsys.readouterr().out
    assert "skipped" in out and "1 of 2 built, 1 skipped" in out
