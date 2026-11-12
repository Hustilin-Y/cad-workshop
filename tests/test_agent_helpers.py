"""Помощники для агента: поворот и зеркало сетки, общий код деталей, заготовка _validate в шаблоне."""

from pathlib import Path

import numpy as np
import pytest
import trimesh

import cad
from cad import main
from cadlib import mesh as m
from cadlib.shared import load_module

ROOT = Path(__file__).resolve().parent.parent


def test_rotate_lays_a_plate_on_its_side():
    plate = trimesh.creation.box((40, 4, 20))
    plate.apply_translation((20, 2, 10))
    lying = m.drop_to_bed(m.rotate(plate, (90, 0, 0)))
    assert np.allclose(lying.extents, [40, 20, 4])  # 90° вокруг X: глубина и высота меняются местами
    assert lying.bounds[0][2] == pytest.approx(0)
    assert lying.volume == pytest.approx(plate.volume)
    assert np.allclose(m.rotate(plate, (0, 0, 90)).bounds.mean(axis=0), plate.bounds.mean(axis=0))


def test_mirror_keeps_normals_outward_and_place():
    wedge = m.subtract(trimesh.creation.box((20, 20, 20)), m.translate(trimesh.creation.box((20, 20, 20)), (10, 0, 10)))
    flipped = m.mirror(wedge, "x")
    assert flipped.volume == pytest.approx(wedge.volume) and flipped.volume > 0
    assert flipped.is_winding_consistent and flipped.is_watertight
    assert np.allclose(flipped.bounds, wedge.bounds)
    # вырез был в +X, у зеркальной копии — в −X: верхняя половина сдвинута в другую сторону
    top = lambda mesh: mesh.vertices[mesh.vertices[:, 2] > 5][:, 0].mean()  # noqa: E731
    assert np.sign(top(flipped)) == -np.sign(top(wedge))
    with pytest.raises(ValueError, match="ось"):
        m.mirror(wedge, "w")


def test_load_module_shares_one_instance(tmp_path):
    helper = tmp_path / "common-part" / "helper.py"
    helper.parent.mkdir()
    helper.write_text("LOADS = []\nLOADS.append(1)\nWIDTH = 12.5\n", encoding="utf-8")
    first, second = load_module(helper), load_module(tmp_path / "common-part" / ".." / "common-part" / "helper.py")
    assert first is second and first.WIDTH == 12.5 and first.LOADS == [1]
    with pytest.raises(ValueError, match="не найден"):
        load_module(tmp_path / "nope.py")


def test_lamp_hanger_arms_share_the_hanger_module():
    left = cad.load_model(ROOT / "parts" / "lamp-hanger-arm-left")
    right = cad.load_model(ROOT / "parts" / "lamp-hanger-arm-right")
    assert left.hanger is right.hanger


def test_template_validate_explains_a_thin_part(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cad, "ROOT", tmp_path)
    assert main(["new", "part", "thin-plate"]) == 0
    model = tmp_path / "parts" / "thin-plate" / "model.py"
    model.write_text(model.read_text(encoding="utf-8").replace("HEIGHT = 10.0", "HEIGHT = 0.3"), encoding="utf-8")
    assert main(["build", str(model.parent)]) == 2
    assert "HEIGHT = 0.3 мм тоньше минимальной стенки" in capsys.readouterr().out
