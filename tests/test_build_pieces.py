"""A model whose build(p) returns several pieces: each built and checked, one 3MF with a plate per copy."""

import json
import re
import zipfile

from cad import main
from cadlib import gridfinity as gf
from cadlib.config import load_profile

TWO_PIECES = '''
from build123d import Align, Box

NAME = "twopiece"
PRINT_HINTS = {"goal": "cheap", "goal_reason": "test"}
WIDE = 20


def build(p):
    low = (Align.MIN, Align.MIN, Align.MIN)
    return [("a", Box(WIDE, 20, 5, align=low), 1), ("b", Box(30, 10, 5, align=low), 2)]
'''


def _model(tmp_path, text=TWO_PIECES):
    folder = tmp_path / "twopiece"
    folder.mkdir()
    (folder / "model.py").write_text(text, encoding="utf-8")
    return folder


def test_pieces_write_each_piece_and_a_plate_per_copy(tmp_path):
    folder = _model(tmp_path)
    assert main(["build", str(folder), "--print-ready"]) == 0
    out = folder / "out"
    assert (out / "twopiece-a.stl").is_file() and (out / "twopiece-b.stl").is_file()
    assert (out / "twopiece-a.png").is_file()
    with zipfile.ZipFile(out / "twopiece.3mf") as z:
        config = z.read("Metadata/model_settings.config").decode()
    assert len(re.findall(r"<plate>", config)) == 3
    manifest = json.loads((out / "twopiece.print.json").read_text(encoding="utf-8"))
    assert manifest["file"] == "twopiece.3mf"
    assert [len(p["objects"]) for p in manifest["plates"]] == [1, 1, 1]
    assert manifest["plates"][0]["hints"]["goal"] == "cheap"


def test_plain_build_of_pieces_writes_no_manifest(tmp_path):
    folder = _model(tmp_path)
    assert main(["build", str(folder)]) == 0
    assert (folder / "out" / "twopiece.3mf").is_file()
    assert not (folder / "out" / "twopiece.print.json").exists()


def test_piece_over_bed_fails_and_writes_no_manifest(tmp_path):
    folder = _model(tmp_path)
    assert main(["build", str(folder), "--print-ready", "--set", "WIDE=300"]) == 1
    assert not (folder / "out" / "twopiece.print.json").exists()


def test_bad_pieces_are_refused(tmp_path):
    folder = _model(tmp_path, TWO_PIECES.replace('("b", Box(30, 10, 5, align=low), 2)', '("a", 7, 0)'))
    assert main(["build", str(folder)]) == 2


def test_drawer_base_525x296():
    pieces = gf.drawer_base(525, 296, load_profile())
    assert sum(c for _, _, c in pieces) == 6
    assert sorted(n for n, _, _ in pieces) == list("abcdef")


def test_pieces_with_source_are_refused(tmp_path):
    folder = _model(tmp_path, TWO_PIECES + '\nSOURCE = "source/x.stl"\n')
    (folder / "source").mkdir()
    (folder / "source" / "x.stl").write_text("solid x\nendsolid x\n", encoding="utf-8")
    assert main(["build", str(folder)]) == 2


def test_pieces_with_volume_delta_are_refused(tmp_path):
    folder = _model(tmp_path, TWO_PIECES + "\nEXPECTED_VOLUME_DELTA = 100\n")
    assert main(["build", str(folder)]) == 2


def test_old_piece_files_are_removed(tmp_path):
    folder = _model(tmp_path)
    stale = folder / "out" / "twopiece-z.stl"
    stale.parent.mkdir()
    stale.write_text("old", encoding="utf-8")
    other = folder / "out" / "twopiece-notes.txt"       # not a build output: left alone
    other.write_text("keep", encoding="utf-8")
    assert main(["build", str(folder)]) == 0
    assert not stale.exists() and other.exists()
