"""Этап 2: CLI build/check/inspect/preview, калибровочный образец, отказ при выходе за стол."""

import hashlib
from pathlib import Path

import numpy as np
import pytest
import trimesh
from build123d import Box, Cylinder, Pos

from cad import main
from cadlib.export import export_all
from cadlib.preview import section_loops

ROOT = Path(__file__).resolve().parent.parent


def _write_model(folder: Path, body: str) -> Path:
    folder.mkdir(parents=True)
    (folder / "model.py").write_text(body, encoding="utf-8")
    return folder


def test_build_calibration(capsys):
    assert main(["build", str(ROOT / "calibration")]) == 0
    out = capsys.readouterr().out
    assert "FAIL" not in out and "WARN" not in out
    for ext in ("step", "stl", "3mf", "png"):
        assert (ROOT / "calibration" / "out" / f"tolerance-gauge.{ext}").stat().st_size > 0


def test_build_fails_when_too_big(tmp_path, capsys):
    folder = _write_model(
        tmp_path / "huge",
        "from build123d import Box, Pos\n"
        "def build(p):\n"
        "    return Pos(0, 0, 10) * Box(300, 20, 20)\n",
    )
    assert main(["build", str(folder)]) == 1
    out = capsys.readouterr().out
    assert "[FAIL] 3. Стол" in out
    assert "ПРОВАЛЕНА" in out


def test_build_uses_profile_flags(tmp_path, capsys):
    folder = _write_model(
        tmp_path / "hole",
        "from build123d import Box, Cylinder, Pos\n"
        "NAME = 'hole'\n"
        "def build(p):\n"
        "    return Pos(0, 0, 5) * Box(20, 20, 10) - Pos(0, 0, 5) * Cylinder((3 + p.hole_clearance_mm) / 2, 10)\n",
    )
    assert main(["build", str(folder), "--material", "abs", "--nozzle", "0.6"]) == 0
    assert "сопло 0.6, ABS" in capsys.readouterr().out
    mesh = trimesh.load(folder / "out" / "hole.stl")
    loops = section_loops(mesh, "z")
    hole = min(loops, key=lambda loop: np.ptp(loop[:, 0]))
    assert np.ptp(hole[:, 0]) == pytest.approx(3 + 0.2 + 0.1, abs=0.05)  # 3 мм + зазор + поправка ABS


def test_check_and_inspect(tmp_path, capsys):
    files = export_all(Pos(0, 0, 10) * Box(40, 30, 20), tmp_path, "box", ("stl",))
    assert main(["check", str(files["stl"])]) == 0
    assert main(["inspect", str(files["stl"])]) == 0
    out = capsys.readouterr().out
    assert "40.00 × 30.00 × 20.00 мм" in out
    assert "24000.0 мм³" in out


def test_check_warns_on_inches(tmp_path, capsys):
    files = export_all(Pos(0, 0, 0.5) * Box(1.5, 1, 1), tmp_path, "inch", ("stl",))
    assert main(["check", str(files["stl"])]) == 0
    assert "[WARN] 4. Единицы" in capsys.readouterr().out


def test_check_fails_on_open_mesh(tmp_path, capsys):
    mesh = trimesh.creation.box((20, 20, 20))
    mesh.update_faces(np.arange(len(mesh.faces) - 2))  # убрать два треугольника — дыра в сетке
    path = tmp_path / "open.stl"
    mesh.export(path)
    assert main(["check", str(path)]) == 1
    assert "[FAIL] 1. Сетка" in capsys.readouterr().out


def test_preview_never_writes_into_source(tmp_path):
    source = tmp_path / "remix" / "source"
    source.mkdir(parents=True)
    files = export_all(Pos(0, 0, 5) * Box(10, 10, 10), source, "orig", ("stl",))
    digest = hashlib.sha256(files["stl"].read_bytes()).hexdigest()
    assert main(["preview", str(files["stl"]), "--section", "x"]) == 0
    assert sorted(p.name for p in source.iterdir()) == ["orig.stl"]
    assert (tmp_path / "remix" / "out" / "orig.png").exists()
    assert hashlib.sha256(files["stl"].read_bytes()).hexdigest() == digest


def test_section_loops_box_with_hole():
    from cadlib.export import shape_to_mesh

    mesh = shape_to_mesh(Pos(0, 0, 5) * Box(20, 20, 10) - Pos(0, 0, 5) * Cylinder(4, 10))
    assert len(section_loops(mesh, "z")) == 2


def test_user_errors(tmp_path, capsys):
    assert main(["check", str(tmp_path / "nope.stl")]) == 2
    assert main(["build", str(tmp_path)]) == 2
    assert main(["build", str(ROOT / "calibration"), "--nozzle", "0.5"]) == 2
    out = capsys.readouterr().out
    assert "файл не найден" in out and "нет model.py" in out and "Сопло 0.5" in out
