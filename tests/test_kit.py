"""A set of parts in one 3MF, plate by plate (cad.py kit, cadlib.export.write_plates_3mf)."""

import hashlib
import json
import re
import zipfile
from pathlib import Path

import pytest
import trimesh

from cad import main
from cadlib.export import BAMBU_PLATE_GAP, layout_plate, plate_origin, write_plates_3mf

BED = (256.0, 256.0)
FIXTURE = Path(__file__).parent / "fixtures" / "manifest" / "kit.print.json"


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
    assert re.findall(r'name="([^"]+)" type="model"', model) == ["part-one", "part-two#1", "part-two#2"]
    # PRINT_DOWN = +x: the parts stand on their end, as long as they were wide
    heights = [float(h) for h in re.findall(r'z="([\d.]+)"', model)]
    assert max(heights) == pytest.approx(30, abs=0.01)


def test_kit_command_without_kit_file_says_so(tmp_path, capsys):
    assert main(["kit", str(tmp_path)]) == 2
    assert "no kit.py" in capsys.readouterr().out


def _kit_part(root, name, size, extra=""):
    folder = root / name
    folder.mkdir()
    (folder / "model.py").write_text(
        "from build123d import Box, Pos\n"
        f"NAME = '{name}'\n"
        f"{extra}"
        "def build(p):\n"
        f"    return Pos(0, 0, 5) * Box({size}, 10, 10)\n", encoding="utf-8")
    return folder


def _kit(tmp_path, plates, parts):
    """parts: {name: (size, extra model lines)}; the kit lives in the folder of the first part."""
    for name, (size, extra) in parts.items():
        _kit_part(tmp_path, name, size, extra)
    first = tmp_path / next(iter(parts))
    (first / "kit.py").write_text(f"KITS = {{'demo': {plates!r}}}\n", encoding="utf-8")
    return first


def _kit_manifest(folder):
    return json.loads((folder / "out" / "demo.print.json").read_text(encoding="utf-8"))


def test_kit_writes_manifest_per_plate(tmp_path):
    first = _kit(tmp_path, [[(".", 1)], [("../two", 1)]], {"one": (20, ""), "two": (30, "")})
    assert main(["kit", str(first)]) == 0
    m = _kit_manifest(first)
    assert m["kind"] == "kit" and m["name"] == "demo" and m["file"] == "demo.3mf"
    assert m["print_ready"] is True and m["schema"] == 1 and m["hints"] == {}
    assert [p["index"] for p in m["plates"]] == [1, 2]
    assert [[o["name"] for o in p["objects"]] for p in m["plates"]] == [["one"], ["two"]]
    assert m["plates"][1]["objects"][0]["bbox_mm"] == pytest.approx([30, 10, 10], abs=0.01)
    assert m["plates"][1]["objects"][0]["volume_mm3"] == pytest.approx(3000, rel=0.001)
    grams = [p["estimate"]["grams"] for p in m["plates"]]
    assert all(g > 0 for g in grams) and grams[1] > grams[0]
    assert m["estimate"]["grams"] == pytest.approx(sum(grams), abs=0.11)
    assert all(p["checks"]["failed"] is False for p in m["plates"]) and m["checks"]["failed"] is False
    assert "hint_conflicts" not in m["plates"][0]
    assert m["file_sha256"] == hashlib.sha256((first / "out" / "demo.3mf").read_bytes()).hexdigest()
    raw = (first / "out" / "demo.print.json").read_bytes()
    assert raw.endswith(b"\n") and b"\r" not in raw


def test_kit_manifest_object_is_the_turned_part(tmp_path):
    first = _kit(tmp_path, [[(".", 1)]], {"one": (40, "PRINT_DOWN = '+x'\n")})
    assert main(["kit", str(first)]) == 0
    obj = _kit_manifest(first)["plates"][0]["objects"][0]
    assert obj["bbox_mm"][2] == pytest.approx(40, abs=0.01)


def test_kit_plate_checks_are_the_worst_of_its_parts(tmp_path):
    # Standing on its 10 mm end the 40 mm bar keeps a base; a part floating above the bed (two
    # bodies, one expected) must show up in the plate's checks while a clean plate stays clean.
    floating = (
        "from build123d import Box, Pos\n"
        "NAME = 'two'\n"
        "def build(p):\n"
        "    return Pos(0, 0, 5) * Box(20, 10, 10) + Pos(0, 0, 40) * Box(10, 10, 10)\n"
    )
    first = _kit(tmp_path, [[(".", 1)], [("../two", 1)]], {"one": (20, ""), "two": (20, "")})
    (tmp_path / "two" / "model.py").write_text(floating, encoding="utf-8")
    assert main(["kit", str(first)]) == 0
    clean, dirty = _kit_manifest(first)["plates"]
    assert clean["checks"]["supports_suggested"] is False
    assert dirty["checks"]["supports_suggested"] is True
    assert dirty["checks"]["islands"] + dirty["checks"]["bodies_above_bed"] > 0


def test_kit_copies_named_with_suffix(tmp_path):
    first = _kit(tmp_path, [[(".", 2), ("../two", 1)]], {"one": (20, ""), "two": (30, "")})
    assert main(["kit", str(first)]) == 0
    names = [o["name"] for o in _kit_manifest(first)["plates"][0]["objects"]]
    assert names == ["one#1", "one#2", "two"]
    with zipfile.ZipFile(first / "out" / "demo.3mf") as z:
        model = z.read("3D/3dmodel.model").decode()
    assert re.findall(r'name="([^"]+)" type="model"', model) == names


def test_kit_conflicting_hints_listed(tmp_path):
    first = _kit(tmp_path, [[(".", 1), ("../two", 1)], [("../three", 1), ("../four", 1)]], {
        "one": (20, "PRINT_HINTS = {'walls': 3, 'brim': 'none'}\n"),
        "two": (20, "PRINT_HINTS = {'walls': 5, 'brim': 'none'}\n"),
        "three": (20, "PRINT_HINTS = {'walls': 4}\n"),
        "four": (20, "PRINT_HINTS = {'walls': 4}\n"),
    })
    assert main(["kit", str(first)]) == 0
    a, b = _kit_manifest(first)["plates"]
    assert a["hints"] == {} and a["hint_conflicts"] == ["walls"]
    assert b["hints"] == {"walls": 4} and "hint_conflicts" not in b


def test_kit_hint_set_by_one_part_only_is_a_conflict(tmp_path):
    first = _kit(tmp_path, [[(".", 1), ("../two", 1)]], {
        "one": (20, "PRINT_HINTS = {'walls': 3}\n"), "two": (20, "")})
    assert main(["kit", str(first)]) == 0
    (plate,) = _kit_manifest(first)["plates"]
    assert plate["hints"] == {} and plate["hint_conflicts"] == ["walls"]


def test_kit_invalid_hint_is_an_error_and_leaves_no_manifest(tmp_path, capsys):
    first = _kit(tmp_path, [[(".", 1)]], {"one": (20, "PRINT_HINTS = {'walls': 99}\n")})
    stale = first / "out" / "demo.print.json"
    stale.parent.mkdir()
    stale.write_text("{}\n", encoding="utf-8")
    assert main(["kit", str(first)]) == 2
    assert "walls" in capsys.readouterr().out
    assert not stale.exists()


def test_kit_with_a_failing_part_writes_no_manifest(tmp_path):
    first = _kit(tmp_path, [[(".", 1)]], {"one": (300, "")})  # longer than the bed
    stale = first / "out" / "demo.print.json"
    stale.parent.mkdir()
    stale.write_text("{}\n", encoding="utf-8")
    main(["kit", str(first)])
    assert not stale.exists()


# The consumer's fixture pins the keys. Opaque (free-form) dicts are not compared inside. The
# fixture is a minimal kit: this producer also writes what a part manifest has (the model's hash
# and commit, the tolerances, the original's hash), which the tolerant consumer ignores.
OPAQUE = {("profile", "tolerances"), ("hints",), ("source", "overrides"), ("plates", "[]", "hints")}
PRODUCER_ONLY = {(): {"git_commit", "model_sha256"}, ("profile",): {"tolerances"}, ("source",): {"original_sha256"}}


def _keys_cover(written, fixture, path=()):
    if path in OPAQUE:
        assert isinstance(written, dict)
        return
    if isinstance(fixture, dict):
        assert isinstance(written, dict), path
        # hint_conflicts exists only on a plate that has conflicts
        optional = {"hint_conflicts"} if path == ("plates", "[]") else set()
        expected = set(fixture) | PRODUCER_ONLY.get(path, set())
        where = ".".join(path) or "<root>"
        assert set(written) - optional == expected - optional, f"{where}: {sorted(written)} != {sorted(expected)}"
        for key in set(fixture) & set(written):
            _keys_cover(written[key], fixture[key], path + (key,))
    elif isinstance(fixture, list):
        assert isinstance(written, list) and written and fixture
        _keys_cover(written[0], fixture[0], path + ("[]",))


def test_kit_manifest_has_the_fixtures_keys(tmp_path):
    first = _kit(tmp_path, [[(".", 2)], [("../two", 1)]], {
        "one": (20, "PRINT_HINTS = {'walls': 3}\n"), "two": (30, "")})
    assert main(["kit", str(first)]) == 0
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    _keys_cover(_kit_manifest(first), fixture)
    # the fixture's second plate shows the conflict shape: the same keys plus hint_conflicts
    assert set(fixture["plates"][1]) == set(fixture["plates"][0]) | {"hint_conflicts"}
