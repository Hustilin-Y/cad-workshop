"""Этап 4: ремиксы — операции над сетками, new remix, проверка 7, защита source/, путь через STEP."""

import hashlib
import math
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest
import trimesh
from build123d import Box, Cylinder, Pos, export_step

import cad
from cad import main
from cadlib import mesh as m
from cadlib.meshio import load_mesh

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "remix" / "example-stub"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- пример из репозитория ----------------------------------------------------


def test_example_remix_volume_and_source_untouched(capsys):
    source = EXAMPLE / "source" / "stub-block.stl"
    before = _sha(source)
    assert main(["build", str(EXAMPLE)]) == 0
    out = capsys.readouterr().out
    assert "[OK  ] 7. Ожидаемое изменение" in out
    assert "[OK  ] Оригинал" in out
    assert "FAIL" not in out and "WARN" not in out
    assert _sha(source) == before == cad._recorded_hash(EXAMPLE / "SOURCE.md")

    module = cad.load_model(EXAMPLE)
    delta = load_mesh(EXAMPLE / "out" / "example-stub.stl").volume - load_mesh(source).volume
    assert delta == pytest.approx(module.EXPECTED_VOLUME_DELTA, rel=0.01)


def test_example_source_is_tracked_but_foreign_sources_are_not():
    def ignored(rel: str) -> bool:
        return subprocess.run(["git", "check-ignore", "-q", rel], cwd=ROOT).returncode == 0

    assert not ignored("remix/example-stub/source/stub-block.stl")
    assert ignored("remix/some-download/source/model.stl")
    assert ignored("remix/example-stub/out/example-stub.stl")


# --- полный цикл в чистой папке -------------------------------------------------


@pytest.fixture
def workshop(tmp_path, monkeypatch):
    """Пустая «мастерская»: new part/remix пишут в tmp_path, шаблоны берутся из проекта."""
    monkeypatch.setattr(cad, "ROOT", tmp_path)
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    return tmp_path, downloads


def test_new_remix_stl_flow(workshop, capsys):
    root, downloads = workshop
    original = downloads / "holder.stl"
    m.to_mesh(Pos(0, 0, 10) * Box(50, 30, 20)).export(original)

    assert main(["new", "remix", "holder-fix", str(original)]) == 0
    out = capsys.readouterr().out
    assert "50.00 × 30.00 × 20.00 мм" in out                       # inspect запускается сразу
    folder = root / "remix" / "holder-fix"
    copy = folder / "source" / "holder.stl"
    assert not os.access(copy, os.W_OK)                            # оригинал только для чтения
    assert cad._recorded_hash(folder / "SOURCE.md") == _sha(original)

    # Нетронутый шаблон собирается, но предупреждает, что правки нет.
    assert main(["build", str(folder)]) == 0
    assert "[WARN] 7. Правка" in capsys.readouterr().out

    # Правка: отверстие Ø10 насквозь.
    text = (folder / "remix.py").read_text(encoding="utf-8")
    text = text.replace(
        "    return body\n",
        "    return m.subtract(body, Pos(0, 0, 10) * Cylinder(5, 22))\n",
    ).replace("EXPECTED_VOLUME_DELTA = None", "EXPECTED_VOLUME_DELTA = -3.14159265 * 25 * 20")
    (folder / "remix.py").write_text(text, encoding="utf-8")
    assert main(["build", str(folder)]) == 0
    out = capsys.readouterr().out
    assert "[OK  ] 7. Ожидаемое изменение" in out
    assert _sha(copy) == _sha(original)


def test_build_fails_when_source_changed(workshop, capsys):
    root, downloads = workshop
    original = downloads / "part.stl"
    m.to_mesh(Pos(0, 0, 5) * Box(20, 20, 10)).export(original)
    main(["new", "remix", "tampered", str(original)])
    folder = root / "remix" / "tampered"
    source_md = folder / "SOURCE.md"
    source_md.write_text(source_md.read_text(encoding="utf-8").replace(_sha(original), "0" * 64), encoding="utf-8")
    capsys.readouterr()
    assert main(["build", str(folder)]) == 1
    assert "[FAIL] Оригинал" in capsys.readouterr().out


def test_new_remix_step_flow(workshop, capsys):
    """Путь через STEP: правка точная (B-rep), на выходе есть и STEP."""
    root, downloads = workshop
    original = downloads / "plate.step"
    export_step(Pos(0, 0, 3) * Box(40, 40, 6), original)

    assert main(["new", "remix", "plate-holes", str(original)]) == 0
    folder = root / "remix" / "plate-holes"
    text = (folder / "remix.py").read_text(encoding="utf-8")
    assert "import_step" in text
    text = text.replace(
        "    return body\n",
        "    body -= Pos(10, 10, 6) * f.clearance_hole('M3', 6, p)\n    return body\n",
    )
    (folder / "remix.py").write_text(text, encoding="utf-8")
    capsys.readouterr()
    assert main(["build", str(folder)]) == 0
    assert "FAIL" not in capsys.readouterr().out

    from build123d import import_step

    result = import_step(folder / "out" / "plate-holes.step")
    hole_d = 3.2 + 0.2
    assert result.volume == pytest.approx(40 * 40 * 6 - math.pi * hole_d**2 / 4 * 6, rel=1e-6)


def test_new_remix_rejects_bad_input(workshop, capsys):
    root, downloads = workshop
    (downloads / "model.blend").write_text("x")
    assert main(["new", "remix", "a", str(downloads / "missing.stl")]) == 2
    assert main(["new", "remix", "b", str(downloads / "model.blend")]) == 2
    out = capsys.readouterr().out
    assert "файл не найден" in out and "не поддерживается" in out


# --- операции над сетками -----------------------------------------------------


@pytest.fixture
def block():
    return m.to_mesh(Pos(0, 0, 10) * Box(40, 20, 20))


def test_scale_keeps_corner_on_bed(block):
    out = m.scale(block, (2, 1, 0.5))
    assert np.allclose(out.extents, (80, 20, 10))
    assert np.allclose(out.bounds[0], block.bounds[0])
    assert np.allclose(m.scale_to(block, (None, None, 50)).extents, (40, 20, 50))
    with pytest.raises(ValueError):
        m.scale(block, 0)


def test_cut_and_split(block):
    lower = m.cut(block, normal=(0, 0, -1), origin=(0, 0, 5))
    assert lower.is_watertight
    assert lower.volume == pytest.approx(40 * 20 * 5, rel=1e-5)
    left, right = m.split_by_plane(block, normal=(-1, 0, 0), origin=(0, 0, 0))
    assert left.volume + right.volume == pytest.approx(block.volume, rel=1e-5)
    assert left.bounds[1][0] == pytest.approx(0, abs=1e-4)


def test_add_and_subtract_with_build123d_tools(block):
    boss = Pos(0, 0, 22.5) * Cylinder(5, 10)             # Z 17.5…27.5: 2.5 мм внутри блока, 7.5 снаружи
    added = m.add(block, boss)
    assert added.volume == pytest.approx(block.volume + math.pi * 25 * 7.5, rel=1e-3)
    assert m.subtract(added, boss).volume < block.volume


def test_repair_broken_download(block):
    broken = block.copy()
    broken.faces[:5] = broken.faces[:5, ::-1]             # часть треугольников вывернута
    broken = trimesh.Trimesh(
        vertices=broken.vertices,
        faces=np.vstack([broken.faces, broken.faces[:3]]),   # дубли треугольников
        process=False,
    )
    result = m.repair(broken)
    assert result.changed and result.mesh.is_watertight
    assert result.mesh.volume == pytest.approx(block.volume, rel=1e-6)

    inverted = block.copy()
    inverted.invert()
    fixed = m.repair(inverted)
    assert fixed.mesh.volume > 0 and any("наизнанку" in n for n in fixed.notes)


def test_open_mesh_rejected_with_hint(block):
    open_mesh = block.copy()
    open_mesh.update_faces(np.arange(len(open_mesh.faces) - 1))
    with pytest.raises(ValueError, match="repair"):
        m.subtract(open_mesh, Pos(0, 0, 10) * Cylinder(2, 30))
