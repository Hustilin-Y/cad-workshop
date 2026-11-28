"""Where a part lives: environment presets, service temperature against the plastic's HDT."""

from types import SimpleNamespace

import pytest

from cadlib import service as sv
from cadlib.checks import Report
from cadlib.config import load_profile


def _env(**kw):
    return sv.service_of(SimpleNamespace(**kw))


def _check(service, material, build_material=None):
    r = Report()
    sv.check_service(r, service, material, build_material or material)
    return {c.name: (c.level, c.message) for c in r.checks}


@pytest.mark.parametrize("env,material,level", [
    ("room", "PLA", "ok"),
    ("outdoor-sun", "PLA", "fail"),
    ("outdoor-sun", "PETG", "ok"),
    ("boat-sun", "PETG", "fail"),
    ("boat-sun", "ABS", "ok"),
    ("car-cabin", "PETG", "fail"),
    ("car-cabin", "ABS", "ok"),
    ("car-dash", "ABS", "fail"),
    ("car-dash", "ASA", "ok"),          # 100 − 10 = 90: exactly at the edge passes
])
def test_presets_at_their_edges(env, material, level):
    assert _check(_env(ENVIRONMENT=env), material)["Environment"][0] == level


def test_fail_names_the_plastics_that_pass():
    lvl, msg = _check(_env(ENVIRONMENT="car-dash"), "PLA")["Environment"]
    assert lvl == "fail" and "ASA" in msg and "ABS" not in msg.split("pass:")[-1]
    lvl, msg = _check(_env(ENVIRONMENT="outdoor-sun"), "PLA")["Environment"]
    assert all(m in msg for m in ("PETG", "ABS", "ASA"))


def test_service_temp_edge():
    s = _env(SERVICE_TEMP_C=61)
    assert s.temp_c == 61 and not s.sun
    assert _check(s, "PETG")["Environment"][0] == "ok"
    assert _check(_env(SERVICE_TEMP_C=61.5), "PETG")["Environment"][0] == "fail"


def test_too_hot_for_any_plastic():
    lvl, msg = _check(_env(SERVICE_TEMP_C=150), "ASA")["Environment"]
    assert lvl == "fail" and "no plastic" in msg


def test_both_keys_refused():
    with pytest.raises(ValueError, match="not both"):
        _env(ENVIRONMENT="room", SERVICE_TEMP_C=30)


def test_unknown_preset_lists_presets():
    with pytest.raises(ValueError, match="car-dash"):
        _env(ENVIRONMENT="sauna")


def test_bad_temperature():
    with pytest.raises(ValueError, match="SERVICE_TEMP_C"):
        _env(SERVICE_TEMP_C="hot")


def test_nothing_declared():
    assert _env() is None


def test_tpu_has_no_hdt_warns():
    assert _check(_env(ENVIRONMENT="room"), "TPU")["Environment"][0] == "warn"


def test_uv_note_for_sun_presets():
    assert _check(_env(ENVIRONMENT="outdoor-sun"), "PETG")["UV"][0] == "warn"
    assert "UV" not in _check(_env(ENVIRONMENT="outdoor-sun"), "ASA")
    assert "UV" not in _check(_env(ENVIRONMENT="car-cabin"), "ABS")


def test_material_mismatch_warns_about_fits():
    lines = _check(_env(ENVIRONMENT="car-dash"), "ASA", "PLA")
    assert lines["Environment"][0] == "ok"
    assert lines["Plastic"][0] == "warn" and "PLA" in lines["Plastic"][1]


def test_tpu_profile_loads():
    p = load_profile(material="TPU")
    assert p.material == "TPU" and "rigid" in p.material_note


# --- in the build -------------------------------------------------------------

PART = '''
from build123d import Align, Box
NAME = "envpart"
{decl}

def build(p):
    return Box(20, 20, 5, align=(Align.MIN, Align.MIN, Align.MIN))
'''

PIECES = '''
from build123d import Align, Box
NAME = "envpieces"
ENVIRONMENT = "car-dash"

def build(p):
    low = (Align.MIN, Align.MIN, Align.MIN)
    return [("a", Box(20, 20, 5, align=low), 1), ("b", Box(10, 10, 5, align=low), 1)]
'''


def _part(tmp_path, decl, text=PART, name="envpart"):
    folder = tmp_path / name
    folder.mkdir()
    (folder / "model.py").write_text(text.replace("{decl}", decl), encoding="utf-8")
    return folder


def test_build_fails_on_the_dashboard_in_pla(tmp_path, capsys):
    from cad import main
    folder = _part(tmp_path, 'ENVIRONMENT = "car-dash"')
    assert main(["build", str(folder)]) == 1
    out = capsys.readouterr().out
    assert "[FAIL] Environment" in out and "ASA" in out


def test_build_passes_in_asa(tmp_path):
    from cad import main
    assert main(["build", str(_part(tmp_path, 'ENVIRONMENT = "car-dash"')), "--material", "asa"]) == 0


def test_hint_material_is_checked(tmp_path, capsys):
    from cad import main
    folder = _part(tmp_path, 'ENVIRONMENT = "car-dash"\nPRINT_HINTS = {"material": "ASA"}')
    assert main(["build", str(folder)]) == 0
    out = capsys.readouterr().out
    assert "[OK  ] Environment" in out and "[WARN] Plastic" in out


def test_unknown_preset_exits_2(tmp_path):
    from cad import main
    assert main(["build", str(_part(tmp_path, 'ENVIRONMENT = "sauna"'))]) == 2


def test_no_declaration_no_line(tmp_path, capsys):
    from cad import main
    assert main(["build", str(_part(tmp_path, ""))]) == 0
    assert "Environment" not in capsys.readouterr().out


def test_each_piece_is_checked(tmp_path, capsys):
    from cad import main
    folder = _part(tmp_path, "", PIECES, "envpieces")
    assert main(["build", str(folder)]) == 1
    assert capsys.readouterr().out.count("[FAIL] Environment") == 2


def test_kit_part_is_checked(tmp_path, capsys):
    from cad import main
    _part(tmp_path, 'ENVIRONMENT = "car-dash"')
    (tmp_path / "kit.py").write_text('KITS = {"envkit": [[("envpart", 1)]]}\n', encoding="utf-8")
    assert main(["kit", str(tmp_path)]) == 1


def test_set_environment_on_a_part_without_one(tmp_path, capsys):
    from cad import apply_overrides, load_model, main
    folder = _part(tmp_path, "")
    assert main(["build", str(folder), "--set", "ENVIRONMENT=car-dash"]) == 1
    assert "[FAIL] Environment" in capsys.readouterr().out
    module = load_model(folder)
    restore = apply_overrides(module, ["SERVICE_TEMP_C=40"])
    assert module.SERVICE_TEMP_C == 40
    restore()
    assert not hasattr(module, "SERVICE_TEMP_C")       # put back as it was: absent
