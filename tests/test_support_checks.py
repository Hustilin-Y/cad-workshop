"""Support checks: narrow base, bodies above the bed, islands, overhangs, print orientation."""

import trimesh

from cad import main
from cadlib import mesh as m
from cadlib.checks import check_mesh, orient_for_print
from cadlib.config import load_profile


def box(size, center):
    b = trimesh.creation.box(size)
    b.apply_translation(center)
    return b


def levels(mesh, print_down=None, bodies=1):
    return {c.name: (c.level, c.message) for c in check_mesh(mesh, load_profile(), bodies, print_down).checks}


def mushroom():
    """A 4 × 4 × 20 stem with an 80 × 80 × 5 cap on top."""
    return m.add(box((4, 4, 20), (0, 0, 10)), box((80, 80, 5), (0, 0, 22.5)))


def test_mushroom_warns_about_base_and_overhangs():
    result = levels(mushroom())
    assert result["5. Base"][0] == "warn" and "tip over" in result["5. Base"][1]
    assert result["6. Overhangs"][0] == "warn"
    assert result["5. Support"][0] == "ok"  # the cap rests on the stem: an overhang, not an island


def test_mushroom_upside_down_is_fine():
    result = levels(mushroom(), print_down="+z")
    assert result["5. Base"][0] == "ok"
    assert result["6. Overhangs"][0] == "info"
    assert result["Orientation"][0] == "info" and "+Z" in result["Orientation"][1]


def test_floating_body_warns_once():
    mesh = trimesh.util.concatenate([box((20, 20, 10), (0, 0, 5)), box((10, 10, 10), (40, 0, 45))])
    result = levels(mesh, bodies=2)
    assert result["5. Bodies above the bed"][0] == "warn" and "40.0" in result["5. Bodies above the bed"][1]
    assert "5. Islands" not in result  # a floating body's bottom is not also counted as an island


def stalactite(drop):
    """A 10 × 10 × 30 post, a beam on top reaching 40 mm sideways, and a stalactite hanging `drop` mm from its end."""
    post = box((10, 10, 30), (0, 0, 15))
    beam = box((50, 10, 5), (20, 0, 27.5))
    tip = box((6, 6, drop + 1), (40, 0, 25 - drop / 2 + 0.5))
    return m.add(post, beam, tip)


def test_stalactite_is_an_island():
    level, message = levels(stalactite(10))["5. Islands"]
    assert level == "warn" and "Z 15.0 mm at (40, 0)" in message


def test_short_ledge_merges_and_is_not_an_island():
    level, message = levels(stalactite(0.5))["5. Support"]
    assert level == "ok" and "join the part within 1 mm: 1" in message


def test_pocket_floor_and_bridge_are_not_islands():
    pocket = m.subtract(box((30, 30, 10), (0, 0, 5)), box((20, 20, 6), (0, 0, 8)))
    bridge = m.add(box((10, 10, 20), (-20, 0, 10)), box((10, 10, 20), (20, 0, 10)), box((50, 10, 4), (0, 0, 22)))
    for mesh in (pocket, bridge):
        assert levels(mesh)["5. Support"][0] == "ok"


def test_orient_for_print_puts_that_side_on_the_bed():
    plate = box((100, 5, 60), (0, 0, 30))
    turned = orient_for_print(plate, "-y")
    x, y, z = (round(float(v), 3) for v in turned.extents)
    assert z == 5.0 and sorted((x, y)) == [60.0, 100.0]  # a turn about Z doesn't matter to the checks


def test_build_uses_print_down_and_check_rejects_bad_side(tmp_path, capsys):
    folder = tmp_path / "shroom"
    folder.mkdir()
    (folder / "model.py").write_text(
        "from build123d import Box, Pos\n"
        'PRINT_DOWN = "+z"\n'
        "def build(p):\n"
        "    return Pos(0, 0, 10) * Box(6, 6, 20) + Pos(0, 0, 22.5) * Box(60, 60, 5)\n",
        encoding="utf-8",
    )
    assert main(["build", str(folder)]) == 0
    out = capsys.readouterr().out
    assert "WARN" not in out and "+Z on the bed" in out

    stl = folder / "out" / "shroom.stl"
    assert main(["check", str(stl)]) == 0
    assert "[WARN] 5. Base" in capsys.readouterr().out
    assert main(["check", str(stl), "--down", "up"]) == 2
    assert "--down: side 'up'" in capsys.readouterr().out
