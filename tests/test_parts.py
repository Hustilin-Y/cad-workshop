"""Этап 3: пример кронштейна и команда new part."""

import math
from pathlib import Path

import pytest

import cad
from cad import main
from cadlib.meshio import load_mesh

ROOT = Path(__file__).resolve().parent.parent
BRACKET = ROOT / "parts" / "example-bracket"


def _expected_bracket_volume(m, hole_d: float) -> float:
    """Объём кронштейна аналитически: Г-профиль ± скругления, минус отверстия и фаски."""
    t, r, ro, c = m.THICKNESS, m.INNER_FILLET, m.OUTER_FILLET, m.ENTRY_CHAMFER
    corner = lambda radius: radius**2 * (1 - math.pi / 4)  # noqa: E731  площадь «уголка» скругления
    profile = m.LEG_X * t + (m.LEG_Z - t) * t + corner(r) - corner(ro)
    r1, r2 = hole_d / 2, hole_d / 2 + c
    chamfer_extra = math.pi * c / 3 * (r1**2 + r1 * r2 + r2**2) - math.pi * r1**2 * c
    holes = 2 * (math.pi * r1**2 * t + chamfer_extra)
    return profile * m.WIDTH - holes


def test_bracket_builds_with_expected_volume(capsys, repo_copy):
    bracket = repo_copy("parts/example-bracket")
    assert main(["build", str(bracket)]) == 0
    out = capsys.readouterr().out
    assert "FAIL" not in out and "WARN" not in out

    module = cad.load_model(bracket)
    from cadlib.config import load_profile

    hole_d = 4.3 + load_profile().hole_clearance_mm
    mesh = load_mesh(bracket / "out" / "example-bracket.stl")
    assert mesh.volume == pytest.approx(_expected_bracket_volume(module, hole_d), rel=0.002)
    assert tuple(round(v, 2) for v in mesh.extents) == (40.0, 25.0, 40.0)
    for ext in ("step", "stl", "3mf", "png"):
        assert (bracket / "out" / f"example-bracket.{ext}").exists()


def test_bracket_rejects_thin_wall(monkeypatch):
    module = cad.load_model(BRACKET)
    monkeypatch.setattr(module, "THICKNESS", 1.0)
    from cadlib.config import load_profile

    with pytest.raises(ValueError, match="минимальной стенки"):
        module.build(load_profile())


def test_new_part_from_template(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cad, "ROOT", tmp_path)
    assert main(["new", "part", "wall-hook"]) == 0
    folder = tmp_path / "parts" / "wall-hook"
    assert (folder / "model.py").read_text(encoding="utf-8").count('NAME = "wall-hook"') == 1
    assert "# wall-hook" in (folder / "README.md").read_text(encoding="utf-8")
    assert main(["build", str(folder)]) == 0

    assert main(["new", "part", "wall-hook"]) == 2       # уже есть
    assert main(["new", "part", "Крюк"]) == 2            # недопустимое имя
    out = capsys.readouterr().out
    assert "уже существует" in out and "только строчные" in out
