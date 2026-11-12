"""Найдено ревью: STEP с кривизной, единицы 3MF, кодировка вывода, ошибки модели, крайние случаи
проверки 7, надписи без системного шрифта, память на больших сетках."""

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest
import trimesh
from build123d import Box, Pos, Sphere, export_step, extrude, fillet

from cad import main
from cadlib import export
from cadlib import mesh as m
from cadlib import preview
from cadlib.checks import Report, check_mesh, compare_to_original
from cadlib.config import load_profile
from cadlib.export import write_3mf
from cadlib.meshio import load_mesh
from cadlib.text import font_path, label

ROOT = Path(__file__).resolve().parent.parent


# --- STEP со скруглениями -----------------------------------------------------


@pytest.mark.parametrize("shape", ["rounded", "sphere"])
def test_check_step_with_curvature(tmp_path, capsys, shape):
    body = fillet(Box(20, 20, 10).edges(), 2) if shape == "rounded" else Sphere(10)
    step = tmp_path / f"{shape}.step"
    export_step(body, step)
    loaded = load_mesh(step)
    assert loaded.is_watertight and len(loaded.split(only_watertight=False)) == 1
    assert main(["check", str(step)]) == 0
    out = capsys.readouterr().out
    assert "FAIL" not in out and "отдельных тел: 1" in out


# --- единицы 3MF --------------------------------------------------------------


def test_3mf_in_inches_is_converted_to_mm(tmp_path):
    path = tmp_path / "inch.3mf"
    write_3mf(trimesh.creation.box((1, 1, 1)), path, "inch")
    with zipfile.ZipFile(path) as z:
        files = {n: z.read(n) for n in z.namelist()}
    files["3D/3dmodel.model"] = files["3D/3dmodel.model"].replace(b'unit="millimeter"', b'unit="inch"')
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    assert np.allclose(load_mesh(path).extents, 25.4)


def test_3mf_written_in_chunks_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "_3MF_CHUNK_ROWS", 7)  # кусков много, швы между ними проверяются
    sphere = trimesh.creation.icosphere(subdivisions=2, radius=10)
    path = tmp_path / "s.3mf"
    write_3mf(sphere, path, "s")
    back = load_mesh(path)
    assert len(back.faces) == len(sphere.faces) and back.is_watertight
    assert back.volume == pytest.approx(sphere.volume, rel=1e-4)


# --- вывод и ошибки CLI -------------------------------------------------------


def test_report_is_utf8_when_piped(tmp_path):
    stl = tmp_path / "cube.stl"
    trimesh.creation.box((20, 20, 20)).export(stl)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    out = subprocess.run(
        [sys.executable, str(ROOT / "cad.py"), "check", str(stl)], capture_output=True, env=env, check=True
    ).stdout
    assert "Сетка" in out.decode("utf-8")


def test_validate_error_is_a_message_not_a_traceback(tmp_path, capsys):
    folder = tmp_path / "thin"
    folder.mkdir()
    (folder / "model.py").write_text(
        "def build(p):\n    raise ValueError('стенка 0.3 мм тоньше минимума 0.8 мм')\n", encoding="utf-8"
    )
    assert main(["build", str(folder)]) == 2
    out = capsys.readouterr().out
    assert "модель не собралась: стенка 0.3 мм" in out and "Traceback" not in out


def test_subtract_everything_explains_itself():
    block = trimesh.creation.box((10, 10, 10))
    with pytest.raises(ValueError, match="не осталось ни одного треугольника"):
        m.subtract(block, trimesh.creation.box((20, 20, 20)))


# --- проверка 7 ---------------------------------------------------------------


def _levels(report: Report) -> dict[str, str]:
    return {c.name: c.level for c in report.checks}


def test_pure_move_is_not_reported_as_no_change():
    original = trimesh.creation.box((10, 10, 10))
    moved = original.copy()
    moved.apply_translation((5, 0, 0))
    report = Report()
    compare_to_original(original, moved, report, expected_delta_mm3=0)
    levels = _levels(report)
    assert "7. Правка" not in levels
    assert levels["7. Ожидаемое изменение"] == "ok"


def test_zero_expected_delta_still_catches_real_change():
    original = trimesh.creation.box((10, 10, 10))
    report = Report()
    compare_to_original(original, trimesh.creation.box((10, 10, 9)), report, expected_delta_mm3=0)
    assert _levels(report)["7. Ожидаемое изменение"] == "warn"


# --- надписи ------------------------------------------------------------------


def test_label_uses_packaged_font_and_is_watertight():
    assert font_path().name == "DejaVuSans-Bold.ttf"
    plate = Pos(0, 0, 1) * Box(40, 15, 2) + extrude(Pos(0, 0, 2) * label("АБВ 0.25", 5), amount=0.6)
    mesh = export.shape_to_mesh(plate)
    assert mesh.is_watertight
    assert check_mesh(mesh, load_profile(), 1).failed is False


# --- превью большой сетки -----------------------------------------------------


def test_preview_draws_a_simplified_copy_of_a_big_mesh(tmp_path, monkeypatch):
    monkeypatch.setattr(preview, "PREVIEW_MAX_FACES", 500)
    sphere = trimesh.creation.icosphere(subdivisions=4, radius=10)  # 5120 треугольников
    drawn = []
    real = preview._draw_view
    monkeypatch.setattr(preview, "_draw_view", lambda ax, mesh, *a: drawn.append(len(mesh.faces)) or real(ax, mesh, *a))
    png = preview.render_preview(sphere, tmp_path / "s.png", "s", section="z")
    assert png.stat().st_size > 0
    assert drawn and max(drawn) <= 600
    assert len(sphere.faces) == 5120  # исходная сетка не тронута
