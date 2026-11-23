"""`build --print-ready` writes out/<name>.print.json; any other build removes a stale one."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from cad import main

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "manifest" / "part.print.json"

MODEL = (
    "from build123d import Box, Pos\n"
    "NAME = 'tiny'\n"
    "WIDTH = 30.0\n"
    "{extra}"
    "def build(p):\n"
    "    return Pos(0, 0, 5) * Box(WIDTH, 20, 10)\n"
)


def _part(tmp_path: Path, extra: str = "") -> Path:
    folder = tmp_path / "tiny"
    folder.mkdir()
    (folder / "model.py").write_text(MODEL.format(extra=extra), encoding="utf-8")
    return folder


def _manifest(folder: Path) -> dict:
    return json.loads((folder / "out" / "tiny.print.json").read_text(encoding="utf-8"))


def test_print_ready_build_writes_manifest(tmp_path, capsys):
    folder = _part(tmp_path)
    assert main(["build", str(folder), "--print-ready"]) == 0
    assert "JSON" in capsys.readouterr().out
    m = _manifest(folder)
    assert m["schema"] == 1
    assert m["kind"] == "part"
    assert m["print_ready"] is True
    assert m["file"] == "tiny.3mf"
    assert m["file_sha256"] == hashlib.sha256((folder / "out" / "tiny.3mf").read_bytes()).hexdigest()
    assert m["profile"]["material"] == "PLA"
    assert m["profile"]["nozzle_mm"] == 0.4
    assert m["checks"]["failed"] is False
    assert m["estimate"]["grams"] > 0
    (plate,) = m["plates"]
    assert plate["index"] == 1
    (obj,) = plate["objects"]
    assert obj["name"] == "tiny"
    assert obj["bbox_mm"] == pytest.approx([30.0, 20.0, 10.0], abs=0.01)
    assert obj["volume_mm3"] == pytest.approx(6000.0, rel=0.001)
    raw = (folder / "out" / "tiny.print.json").read_bytes()
    assert raw.endswith(b"\n") and b"\r" not in raw


def test_plain_build_removes_stale_manifest(tmp_path):
    folder = _part(tmp_path)
    stale = folder / "out" / "tiny.print.json"
    stale.parent.mkdir()
    stale.write_text("{}\n", encoding="utf-8")
    assert main(["build", str(folder)]) == 0
    assert not stale.exists()


def test_failed_build_writes_no_manifest(tmp_path):
    folder = _part(tmp_path)
    stale = folder / "out" / "tiny.print.json"
    stale.parent.mkdir()
    stale.write_text("{}\n", encoding="utf-8")
    assert main(["build", str(folder), "--print-ready", "--set", "WIDTH=300"]) == 1
    assert not stale.exists()


def test_hints_from_model(tmp_path):
    folder = _part(tmp_path, "PRINT_HINTS = {'walls': 4}\n")
    assert main(["build", str(folder), "--print-ready"]) == 0
    assert _manifest(folder)["hints"] == {"walls": 4}


def test_invalid_hint_fails_the_build_naming_the_key(tmp_path, capsys):
    folder = _part(tmp_path, "PRINT_HINTS = {'walls': 99}\n")
    # Exit 2 is the CLI's code for every user error (a model's _validate failure too).
    assert main(["build", str(folder), "--print-ready"]) == 2
    assert "walls" in capsys.readouterr().out
    assert not (folder / "out").exists()  # fails before exporting


def test_overrides_recorded(tmp_path):
    folder = _part(tmp_path)
    assert main(["build", str(folder), "--print-ready", "--set", "WIDTH=45"]) == 0
    assert _manifest(folder)["source"]["overrides"] == {"WIDTH": "45"}


def test_remix_records_original_hash(repo_copy):
    example = repo_copy("remix/example-stub")
    assert main(["build", str(example), "--print-ready"]) == 0
    m = json.loads((example / "out" / "example-stub.print.json").read_text(encoding="utf-8"))
    original = example / "source" / "stub-block.stl"
    assert m["source"]["original_sha256"] == hashlib.sha256(original.read_bytes()).hexdigest()


def test_no_print_down_still_print_ready(tmp_path):
    folder = _part(tmp_path, "PRINT_DOWN = None\n")
    assert main(["build", str(folder), "--print-ready"]) == 0
    m = _manifest(folder)
    assert m["print_ready"] is True
    assert m["plates"][0]["objects"][0]["bbox_mm"] == pytest.approx([30.0, 20.0, 10.0], abs=0.01)


def test_print_down_turns_the_plate_object(tmp_path):
    folder = _part(tmp_path, "PRINT_DOWN = '-x'\n")
    assert main(["build", str(folder), "--print-ready"]) == 0
    bbox = _manifest(folder)["plates"][0]["objects"][0]["bbox_mm"]
    assert sorted(bbox) == pytest.approx([10.0, 20.0, 30.0], abs=0.01)
    assert bbox[2] == pytest.approx(30.0, abs=0.01)


# The consumer's fixture pins the keys. Opaque (free-form) dicts are not compared inside, and
# keys only the consumer's forward-compatibility test adds are skipped.
OPAQUE = {("profile", "tolerances"), ("hints",), ("source", "overrides")}
CONSUMER_ONLY = {"extra_future_field"}


def _same_keys(written, fixture, path=()):
    if path in OPAQUE:
        assert isinstance(written, dict)
        return
    if isinstance(fixture, dict):
        assert isinstance(written, dict), path
        expected = set(fixture) - (CONSUMER_ONLY if not path else set())
        assert set(written) == expected, f"{'.'.join(path) or '<root>'}: {sorted(written)} != {sorted(expected)}"
        for key in expected:
            _same_keys(written[key], fixture[key], path + (key,))
    elif isinstance(fixture, list):
        assert isinstance(written, list) and written and fixture
        _same_keys(written[0], fixture[0], path + ("[]",))


def test_part_manifest_has_the_fixtures_keys(tmp_path):
    folder = _part(tmp_path, "PRINT_HINTS = {'walls': 4}\n")
    assert main(["build", str(folder), "--print-ready", "--set", "WIDTH=45"]) == 0
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    _same_keys(_manifest(folder), fixture)
