"""A set of parts in one 3MF, plate by plate (cad.py kit, cadlib.export.write_plates_3mf)."""

import re
import zipfile

import pytest
import trimesh

from cad import main
from cadlib.export import BAMBU_PLATE_GAP, layout_plate, plate_origin, write_plates_3mf

BED = (256.0, 256.0)


def test_plate_grid_follows_bambu_studio():
    # 7 plates: 3 columns, the second row below the first; a plate's step is the bed plus a fifth of it.
    step = 256 * (1 + BAMBU_PLATE_GAP)
    assert plate_origin(0, 7, BED) == (0, 0)
    assert plate_origin(2, 7, BED) == pytest.approx((2 * step, 0))
    assert plate_origin(3, 7, BED) == pytest.approx((0, -step))
    assert plate_origin(1, 2, BED) == pytest.approx((step, 0))


def test_parts_sharing_a_plate_go_in_rows_and_stay_on_the_bed():
    boxes = [trimesh.creation.box((100, 40, 10)) for _ in range(3)]
    centres = layout_plate(boxes, BED, 5)
    for (x, y), b in zip(centres, boxes):
        assert 5 <= x - 50 and x + 50 <= 251 and 5 <= y - 20 and y + 20 <= 251
    assert len({round(y) for _, y in centres}) == 2      # two fit in a row of 246 mm, the third starts a new row
    (x0, y0), (x1, y1), (_, y2) = centres
    assert y0 == y1 and x1 - x0 == pytest.approx(110)     # side by side, 10 mm apart
    assert y0 - y2 == pytest.approx(50)                    # the next row 10 mm below


def test_a_part_too_big_for_the_plate_is_refused():
    with pytest.raises(ValueError, match="plate"):
        layout_plate([trimesh.creation.box((250, 20, 10))], BED, 5)


def test_plates_3mf_has_every_part_as_an_object_inside_its_plate(tmp_path):
    a, b = trimesh.creation.box((20, 30, 10)), trimesh.creation.cylinder(8, 15)
    path = tmp_path / "set.3mf"
    write_plates_3mf([[("a", a)], [("b 1", b), ("b 2", b)], [("c", a)]], path, BED, 5)
    with zipfile.ZipFile(path) as z:
        model = z.read("3D/3dmodel.model").decode()
        config = z.read("Metadata/model_settings.config").decode()
    assert "production" not in model                        # plain core 3MF: Bambu Studio opens it as geometry
    assert re.findall(r'<object id="(\d+)" name="([^"]+)"', model) == [("1", "a"), ("2", "b 1"), ("3", "b 2"), ("4", "c")]
    plates = [re.findall(r'key="object_id" value="(\d+)"', p) for p in re.findall(r"<plate>(.*?)</plate>", config, re.S)]
    assert plates == [["1"], ["2", "3"], ["4"]]
    moves = {oid: (float(x), float(y)) for oid, x, y in
             re.findall(r'<item objectid="(\d+)" transform="1 0 0 0 1 0 0 0 1 ([-\d.]+) ([-\d.]+) 0"', model)}
    for n, ids in enumerate(plates):
        ox, oy = plate_origin(n, 3, BED)
        for oid in ids:
            x, y = moves[oid]
            assert ox < x < ox + BED[0] and oy < y < oy + BED[1]


def test_kit_command_builds_one_3mf_from_part_folders(tmp_path, capsys):
    for name, size in (("one", 20), ("two", 30)):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "model.py").write_text(
            "from build123d import Box, Pos\n"
            f"NAME = 'part-{name}'\n"
            "PRINT_DOWN = '+x'\n"
            "def build(p):\n"
            f"    return Pos(0, 0, 5) * Box({size}, 10, 10)\n", encoding="utf-8")
    (tmp_path / "one" / "kit.py").write_text(
        "KITS = {'demo': [[('.', 1)], [('../two', 2)]]}\n", encoding="utf-8")
    assert main(["kit", str(tmp_path / "one")]) == 0
    out = capsys.readouterr().out
    assert "2 plates, 3 parts" in out
    path = tmp_path / "one" / "out" / "demo.3mf"
    with zipfile.ZipFile(path) as z:
        model = z.read("3D/3dmodel.model").decode()
    assert re.findall(r'name="([^"]+)" type="model"', model) == ["part-one", "part-two 1", "part-two 2"]
    # PRINT_DOWN = +x: the parts stand on their end, as long as they were wide
    heights = [float(h) for h in re.findall(r'z="([\d.]+)"', model)]
    assert max(heights) == pytest.approx(30, abs=0.01)


def test_kit_command_without_kit_file_says_so(tmp_path, capsys):
    assert main(["kit", str(tmp_path)]) == 2
    assert "no kit.py" in capsys.readouterr().out
