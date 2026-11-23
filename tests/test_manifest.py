"""Print manifest model: PRINT_HINTS validation, check summary, hashes, stable JSON."""

import hashlib
import json

import pytest

from cadlib.checks import Report
from cadlib.config import load_profile
from cadlib.manifest import (
    HINT_KEYS,
    build_manifest,
    checks_summary,
    remove_stale,
    validate_hints,
    write_manifest,
)

FULL_HINTS = {
    "walls": 4,
    "infill_pct": 25,
    "infill_pattern": "gyroid",
    "supports": "tree",
    "brim": "outer",
    "material": "PETG",
    "material_reason": "near a lamp",
}


def test_hint_keys_are_the_closed_list():
    assert set(HINT_KEYS) == set(FULL_HINTS)


def test_validate_hints_accepts_full_set():
    assert validate_hints(dict(FULL_HINTS), load_profile()) == FULL_HINTS


def test_validate_hints_accepts_empty_and_none():
    assert validate_hints({}, load_profile()) == {}
    assert validate_hints(None, load_profile()) == {}


def test_validate_hints_rejects_unknown_key():
    with pytest.raises(ValueError) as err:
        validate_hints({"wall": 3}, load_profile())
    assert "wall" in str(err.value) and "walls" in str(err.value)


def test_validate_hints_rejects_bad_value():
    with pytest.raises(ValueError, match="supports"):
        validate_hints({"supports": "yes"}, load_profile())


@pytest.mark.parametrize(
    "key, value",
    [
        ("walls", 0), ("walls", 11), ("walls", True), ("walls", 3.0), ("walls", "3"),
        ("infill_pct", -1), ("infill_pct", 101), ("infill_pct", False),
        ("infill_pattern", "triangles"), ("infill_pattern", 1),
        ("supports", None), ("brim", "inner"),
        ("material_reason", "x" * 201), ("material_reason", 5),
    ],
)
def test_validate_hints_rejects_out_of_range(key, value):
    with pytest.raises(ValueError, match=key):
        validate_hints({key: value}, load_profile())


def test_validate_hints_boundaries_pass():
    hints = {"walls": 10, "infill_pct": 0, "material_reason": "x" * 200}
    assert validate_hints(hints, load_profile()) == hints
    assert validate_hints({"walls": 1, "infill_pct": 100}, load_profile())["infill_pct"] == 100


def test_validate_hints_not_a_dict():
    with pytest.raises(ValueError, match="PRINT_HINTS"):
        validate_hints(["walls"], load_profile())


def test_validate_hints_material_must_exist():
    with pytest.raises(ValueError, match="material") as err:
        validate_hints({"material": "TPU"}, load_profile())
    assert "PETG" in str(err.value)
    with pytest.raises(ValueError, match="material"):
        validate_hints({"material": "petg"}, load_profile())  # keys of [materials.*] are exact


def test_validate_hints_returns_a_copy():
    hints = {"walls": 3}
    out = validate_hints(hints, load_profile())
    out["walls"] = 5
    assert hints["walls"] == 3


def _report(*checks):
    r = Report()
    for c in checks:
        r.add(*c)
    return r


def test_checks_summary_from_report():
    r = _report(
        ("5. Islands", "warn",
         "places where printing starts in the air: 2: Z 3.0 mm at (1, 2); Z 4.0 mm at (5, 6). Needs supports or another orientation"),
        ("6. Overhangs", "warn", "40.0% of the area overhangs steeper than 45°: it won't print without supports, or turn the part"),
        ("5. Base", "ok", "10.0 mm² on the bed (50% of the footprint)"),
    )
    s = checks_summary(r)
    assert s == {
        "failed": False, "islands": 2, "bodies_above_bed": 0,
        "overhang_warn": True, "base_warn": False, "supports_suggested": True,
    }


def test_checks_summary_bodies_base_and_failed():
    r = _report(
        ("1. Manifold", "fail", "open edges"),
        ("5. Bodies above the bed", "warn", "3 of the bodies don't touch the bed (bottom at 1.0, 2.0, 3.0 mm): they print only on supports"),
        ("5. Base", "warn", "almost no flat base (0.00 mm²): turn the part"),
        ("6. Overhangs", "info", "3.0% of the area overhangs steeper than 45°"),
    )
    s = checks_summary(r)
    assert s["failed"] is True
    assert s["bodies_above_bed"] == 3 and s["islands"] == 0
    assert s["base_warn"] is True and s["overhang_warn"] is False
    assert s["supports_suggested"] is True


def test_checks_summary_clean_and_missing():
    assert checks_summary(Report()) == {
        "failed": False, "islands": 0, "bodies_above_bed": 0,
        "overhang_warn": False, "base_warn": False, "supports_suggested": False,
    }
    r = _report(("5. Support", "ok", "every layer rests on the one below"))
    assert checks_summary(r)["supports_suggested"] is False


def test_checks_summary_unparsable_warning_is_an_error():
    r = _report(("5. Islands", "warn", "something unexpected"))
    with pytest.raises(ValueError, match="Islands"):
        checks_summary(r)


def _manifest(tmp_path, **over):
    f = tmp_path / "p.3mf"
    f.write_bytes(b"3mf-bytes")
    m = tmp_path / "model.py"
    m.write_bytes(b"print('model')\n")
    kw = dict(
        kind="part", name="p", file=f, print_ready=True, model_path=m,
        overrides={"WIDTH": "45"}, profile=load_profile(),
        plates=[{"index": 1, "objects": []}], checks=checks_summary(Report()),
        estimate_g=14.2, hints={"walls": 3}, original_sha256=None,
    )
    kw.update(over)
    return build_manifest(**kw), f, m


def test_build_manifest_hashes_and_schema(tmp_path):
    man, f, m = _manifest(tmp_path)
    assert man["schema"] == 1
    assert man["file_sha256"] == hashlib.sha256(f.read_bytes()).hexdigest()
    assert man["model_sha256"] == hashlib.sha256(m.read_bytes()).hexdigest()
    assert man["file"] == "p.3mf" and man["kind"] == "part" and man["print_ready"] is True
    assert man["estimate"] == {"grams": 14.2}
    assert man["hints"] == {"walls": 3}
    assert man["profile"]["material"] == "PLA" and man["profile"]["nozzle_mm"] == 0.4
    assert isinstance(man["profile"]["tolerances"], dict) and man["profile"]["tolerances"]
    src = man["source"]
    assert src["model_sha256"] == man["model_sha256"] and src["git_commit"] == man["git_commit"]
    assert src["overrides"] == {"WIDTH": "45"} and src["original_sha256"] is None
    assert man["git_commit"] is None or isinstance(man["git_commit"], str)
    json.dumps(man)  # serialisable


def test_build_manifest_git_unavailable(tmp_path, monkeypatch):
    import cadlib.manifest as mod

    def boom(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(mod.subprocess, "run", boom)
    man, _, _ = _manifest(tmp_path)
    assert man["git_commit"] is None and man["source"]["git_commit"] is None


def test_write_manifest_is_sorted_lf(tmp_path):
    man, _, _ = _manifest(tmp_path)
    out = tmp_path / "out" / "p.print.json"
    write_manifest(man, out)
    raw = out.read_bytes()
    assert raw.endswith(b"\n") and b"\r" not in raw
    text = raw.decode("utf-8")
    assert json.loads(text) == man
    assert text == json.dumps(man, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    assert text.index('"checks"') < text.index('"file"') < text.index('"schema"')


def test_remove_stale(tmp_path):
    p = tmp_path / "p.print.json"
    remove_stale(p)  # missing: no error
    p.write_text("{}", encoding="utf-8")
    remove_stale(p)
    assert not p.exists()
