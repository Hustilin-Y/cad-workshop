"""Coupon generator: labelled step series for any fit."""

import math
import shutil

import numpy as np
import pytest

from cadlib import coupon as cp
from cadlib.config import load_profile
from cadlib.export import shape_to_mesh
from cadlib.preview import section_loops
from cadlib.threads import minor_diameter

P = load_profile()


def _hole_diameters(part, z):
    """Sorted X widths of every inner contour of the section Z=z (holes, pockets)."""
    loops = section_loops(shape_to_mesh(part), "z", z)
    outer = max(np.ptp(lp[:, 0]) for lp in loops)
    return sorted(round(float(np.ptp(lp[:, 0])), 2) for lp in loops if np.ptp(lp[:, 0]) < outer - 1e-6)


# --- values and the registry ---------------------------------------------------------------------


def test_values():
    assert cp.values(0, 0.5, 0.1) == [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    assert cp.values(0.15, 0.5, 0.05) == [0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]
    assert cp.values(0.2, 0.2, 0.05) == [0.2]


@pytest.mark.parametrize("args", [(0.5, 0.0, 0.1), (0.0, 0.5, 0.0), (0.0, 0.5, -0.1)])
def test_values_rejects_bad_range(args):
    with pytest.raises(ValueError, match="--from|--step"):
        cp.values(*args)


def test_label_text():
    assert [cp.label_text(c) for c in (0.0, 0.05, 0.5, 0.25)] == [".00", ".05", ".50", ".25"]


def test_unknown_feature_lists_known():
    with pytest.raises(ValueError, match="hole.*magnet"):
        cp.make("bolt", P)


# --- hole ----------------------------------------------------------------------------------------


def test_hole_coupon():
    c = cp.make("hole", P)
    assert c.key == "hole_clearance_mm" and c.bodies == 1 and c.name == "coupon-hole-d8"
    assert len(c.body.solids()) == 1
    assert _hole_diameters(c.body, 1.0) == pytest.approx([8.0, 8.1, 8.2, 8.3, 8.4, 8.5], abs=0.05)


def test_wraps_into_rows_on_the_bed():
    c = cp.make("hole", P, start=0.0, stop=2.9, step=0.1)   # 30 holes
    bb = c.body.bounding_box()
    w, d, _ = P.usable_volume_mm
    assert bb.size.X <= w and bb.size.Y <= d
    assert bb.size.Y > 2 * (8 + 2.9)                        # more than one row
    assert len(_hole_diameters(c.body, 1.0)) == 30


def test_too_many_samples_raise():
    with pytest.raises(ValueError, match="at most"):
        cp.make("hole", P, start=0.0, stop=20.0, step=0.05)


# --- press, slide --------------------------------------------------------------------------------


def test_press_coupon_holes_pins_and_key():
    c = cp.make("press", P)
    assert c.key == "press_fit_mm" and c.bodies == 2 and len(c.body.solids()) == 2
    cs = cp.values(0.0, 0.25, 0.05)
    plate, key = sorted(c.body.solids(), key=lambda s: -s.volume)
    assert _hole_diameters(plate, 1.0) == pytest.approx([8 + x for x in cs], abs=0.05)
    pins = section_loops(shape_to_mesh(plate), "z", cp.PLATE_T + 2)
    assert sorted(round(float(np.ptp(lp[:, 0])), 2) for lp in pins) == pytest.approx(
        sorted(8 - x for x in cs), abs=0.05)
    assert _hole_diameters(key, 1.0) == pytest.approx([8.0], abs=0.05)
    assert [round(float(np.ptp(lp[:, 0])), 2) for lp in section_loops(shape_to_mesh(key), "z", cp.PLATE_T + 2)] \
        == pytest.approx([8.0], abs=0.05)


def test_slide_defaults():
    c = cp.make("slide", P)
    assert c.key == "slide_fit_mm"
    plate = max(c.body.solids(), key=lambda s: s.volume)
    assert len(_hole_diameters(plate, 1.0)) == 8              # 0.15 … 0.50


# --- magnet --------------------------------------------------------------------------------------


def test_magnet_needs_measurements():
    with pytest.raises(ValueError, match="caliper"):
        cp.make("magnet", P)
    with pytest.raises(ValueError, match="caliper"):
        cp.make("magnet", P, d=6)


def test_magnet_pockets():
    c = cp.make("magnet", P, d=6, h=2)
    assert c.key == "magnet_fit_mm" and c.name == "coupon-magnet-d6x2"
    depth = math.ceil(2 / P.layer_mm - 1e-9) * P.layer_mm
    floor = cp.magnet_floor(P)
    assert floor >= P.min_wall_mm
    top = c.body.bounding_box().max.Z
    assert top == pytest.approx(floor + depth, abs=0.01) or top > floor + depth   # labels stand above
    cs = cp.values(0.0, 0.3, 0.05)
    assert _hole_diameters(c.body, floor + depth / 2) == pytest.approx([6 + x for x in cs], abs=0.05)
    push = _hole_diameters(c.body, floor / 2)                 # push-out holes under each pocket
    assert len(push) == len(cs) and max(push) < 6


def test_magnet_fit_in_profile():
    assert load_profile().magnet_fit_mm == pytest.approx(0.1)
    assert load_profile(material="PETG").magnet_fit_mm == pytest.approx(0.15)


# --- thread --------------------------------------------------------------------------------------


def test_thread_rings():
    c = cp.make("thread", P)
    cs = cp.values(0.2, 0.5, 0.05)
    assert c.key == "thread_clearance_mm" and c.name == "coupon-thread-M8"
    solids = c.body.solids()
    assert len(solids) == c.bodies == len(cs)
    # every ring's crest radius matches the printable minor diameter of 8 + c
    found = []
    for s in solids:
        assert s.bounding_box().min.Z == pytest.approx(0, abs=0.01)
        inner = min(section_loops(shape_to_mesh(s), "z", 3.0), key=lambda lp: np.ptp(lp[:, 0]))
        # the ring's axis: centred in X, one ring radius (outer Ø 16 for M8) below the top; the tab runs to −Y
        bb = s.bounding_box()
        cx, cy = bb.center().X, bb.max.Y - 8.0
        found.append(round(2 * float(np.hypot(inner[:, 0] - cx, inner[:, 1] - cy).min()), 2))
    assert sorted(found) == pytest.approx(sorted(minor_diameter(8 + x, 1.25) for x in cs), abs=0.08)


def test_thread_unknown_size():
    with pytest.raises(ValueError, match="M8"):
        cp.make("thread", P, size="M7")


# --- CLI -----------------------------------------------------------------------------------------


@pytest.fixture
def workshop(tmp_path, monkeypatch):
    import cad
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    shutil.copytree(root / "calibration" / "coupons", tmp_path / "calibration" / "coupons")
    monkeypatch.setattr(cad, "ROOT", tmp_path)
    return tmp_path


@pytest.mark.parametrize("argv,name", [
    (["hole"], "coupon-hole-d8"),
    (["press"], "coupon-press-d8"),
    (["slide"], "coupon-slide-d8"),
    (["magnet", "--d", "6", "--h", "2"], "coupon-magnet-d6x2"),
    (["thread", "--size", "M6"], "coupon-thread-M6"),
])
def test_cli_builds_each_feature(workshop, capsys, argv, name):
    from cad import main

    assert main(["coupon", *argv]) == 0
    out = capsys.readouterr().out
    assert "FAIL" not in out and "WARN" not in out
    assert "printer.toml" in out                              # says where the result goes
    for ext in ("stl", "3mf", "png"):
        assert (workshop / "calibration" / "coupons" / "out" / f"{name}.{ext}").stat().st_size > 0


def test_cli_print_ready_and_range(workshop, capsys):
    from cad import main

    assert main(["coupon", "hole", "--from", "0.1", "--to", "0.3", "--step", "0.1", "--print-ready"]) == 0
    assert (workshop / "calibration" / "coupons" / "out" / "coupon-hole-d8.print.json").exists()


def test_cli_magnet_without_sizes_is_a_user_error(workshop, capsys):
    from cad import main

    assert main(["coupon", "magnet"]) == 2
    assert "caliper" in capsys.readouterr().out


def test_build_all_skips_coupons_folder():
    import cad

    folders = [d.name for d in (cad.ROOT / "calibration").glob("*") if (d / "model.py").exists()]
    assert "coupons" not in folders


# --- review fixes --------------------------------------------------------------------------------


def test_label_text_keeps_three_decimals():
    assert [cp.label_text(c) for c in (0.075, 0.025, 0.1, 1.125)] == [".075", ".025", ".10", "1.125"]


@pytest.mark.parametrize("feature,opts", [("hole", {"d": 0}), ("hole", {"d": -3}),
                                          ("magnet", {"d": 6, "h": 0}), ("magnet", {"d": 0, "h": 2})])
def test_sizes_must_be_positive(feature, opts):
    with pytest.raises(ValueError, match="above 0"):
        cp.make(feature, P, **opts)


def test_foreign_option_is_an_error():
    with pytest.raises(ValueError, match="--size"):
        cp.make("hole", P, size="M8")
    with pytest.raises(ValueError, match="--d"):
        cp.make("thread", P, d=8)


@pytest.mark.parametrize("size", ["M3", "M4", "M5"])
def test_small_threads_say_why(size):
    with pytest.raises(ValueError, match="M6"):
        cp.make("thread", P, size=size)


def test_small_magnet_keeps_a_ledge():
    c = cp.make("magnet", P, d=2, h=1)
    floor = cp.magnet_floor(P)
    pockets = _hole_diameters(c.body, floor + 0.1)
    push = _hole_diameters(c.body, floor - 0.1)
    assert min(pockets) == pytest.approx(2.0, abs=0.05)
    assert not push or max(push) <= 2.0 - 2 * 0.45          # at least ~0.5 mm ledge per side


def test_magnet_pocket_bottom_is_the_floor():
    c = cp.make("magnet", P, d=6, h=2)
    floor = cp.magnet_floor(P)
    assert min(_hole_diameters(c.body, floor + 0.05)) > 5.9      # pockets start right at the floor
    assert max(_hole_diameters(c.body, floor - 0.05)) < 3.0      # below it only the push-out holes


def test_cli_names_the_material_correction(workshop, capsys):
    from cad import main

    assert main(["coupon", "hole", "--from", "0.1", "--to", "0.2", "--material", "petg"]) == 0
    out = capsys.readouterr().out
    assert "clearance_add_mm" in out and "0.05" in out
