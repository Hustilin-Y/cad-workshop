import dataclasses

import pytest
from build123d import Box, Pos

from cad import main
from cadlib.checks import orient_for_print
from cadlib.config import load_profile
from cadlib.export import shape_to_mesh
from cadlib.style import log
from cadlib.style.archetypes.hanger import EndProfile, HangerSpec, hanger_kit, hanger_piece
from style_checks import assert_printable

P = load_profile()
STYLES = ["gothic", "gaudi", "hitech", "parametric", "biomech"]
SPEC = HangerSpec(span=400, end_a=EndProfile("rect", 32, 16), end_b=EndProfile("rect", 32, 7.2), drop=200)


def _common(a, b) -> float:
    """Volume of a & b (build123d gives None for an empty intersection)."""
    both = a & b
    return 0.0 if both is None else both.volume


@pytest.mark.parametrize("style", STYLES)
def test_pieces_fit_and_print(style):
    kit = hanger_kit(style, SPEC, P)
    assert set(kit.pieces) == {"mount", "arm-a", "arm-b"}
    for piece in kit.pieces.values():
        assert piece.solid.is_valid and len(piece.solid.solids()) == 1
        assert piece.print_down == "-y" and piece.allowed_print_down == ("-y",)
        mesh = shape_to_mesh(piece.solid)
        assert_printable(mesh, piece.print_down, P)
        assert max(orient_for_print(mesh, piece.print_down).extents[:2]) <= P.usable_volume_mm[0]


@pytest.mark.parametrize("style", STYLES)
def test_long_span_splits_arms(style):
    long = dataclasses.replace(SPEC, span=900)
    kit = hanger_kit(style, long, P)
    names = set(kit.pieces)
    assert {"arm-a-1", "arm-a-2", "arm-b-1", "arm-b-2"} <= names
    for name, piece in kit.pieces.items():
        assert len(piece.solid.solids()) == 1, name
        mesh = orient_for_print(shape_to_mesh(piece.solid), piece.print_down)
        assert max(mesh.extents[:2]) <= P.usable_volume_mm[0] - 10, name
        assert mesh.extents[2] <= P.usable_volume_mm[2], name


def test_arm_that_fits_is_not_split():
    # The elevation is 179 x 234 mm against a 236 mm limit: it fits whole, with its hub tenon.
    kit = hanger_kit("gothic", dataclasses.replace(SPEC, drop=215), P)
    assert set(kit.pieces) == {"mount", "arm-a", "arm-b"}
    for piece in kit.pieces.values():
        assert max(orient_for_print(shape_to_mesh(piece.solid), piece.print_down).extents[:2]) <= P.usable_volume_mm[0] - 10


def test_each_piece_gets_its_own_style_notes():
    spec = dataclasses.replace(SPEC, drop=207)  # a fresh cache entry: the build logs now
    log.drain()
    log.note("caller", "logged before the kit")
    mount = hanger_piece("gothic", spec, P, "mount")
    first = log.drain()
    hanger_piece("gothic", spec, P, "arm-a")
    arm = log.drain()
    hanger_piece("gothic", spec, P, "arm-a")
    again = log.drain()
    assert mount.print_down == "-y"
    assert any(n.tool == "caller" for n in first)  # the caller's own note is kept
    assert not any("lancets" in n.message for n in first)  # arm notes stay off the mount
    assert any("lancets" in n.message for n in arm)
    assert again == arm  # a cached piece logs its notes again


def test_kit_pieces_read_only():
    with pytest.raises(TypeError):
        hanger_kit("gothic", SPEC, P).pieces["extra"] = None


def test_cradle_fits_profile():
    arm = hanger_kit("gothic", SPEC, P).pieces["arm-a"].solid
    x0 = -SPEC.span / 2
    block = Pos(x0 + SPEC.cradle_len / 2, 0, -SPEC.drop + 8) * Box(SPEC.cradle_len, 32, 16)
    assert _common(arm, block) == pytest.approx(0, abs=1e-3)


def test_trapezoid_cradle_fits_profile():
    spec = dataclasses.replace(SPEC, end_b=EndProfile("trapezoid", 32, 16.5, narrow=17))
    arm = hanger_kit("hitech", spec, P).pieces["arm-b"].solid
    x0 = spec.span / 2
    # The narrow bottom, the slope and the full width above the end all fit; the pocket is open on +Y.
    xc = x0 - spec.cradle_len / 2
    bottom = Pos(xc, 0, -spec.drop + 0.5) * Box(spec.cradle_len, 17, 1)
    middle = Pos(xc, 0, -spec.drop + 8.25) * Box(spec.cradle_len, 17 + (32 - 17) / 2, 1)
    top = Pos(xc, 0, -spec.drop + 17) * Box(spec.cradle_len, 32, 1)
    for block in (bottom, middle, top):
        assert _common(arm, block) == pytest.approx(0, abs=1e-3)
    # ... and the -Y wall holds it: material right beside the end's slope.
    wall = Pos(xc, -(32 / 2 + P.slide_fit_mm + 1.0), -spec.drop + 12) * Box(spec.cradle_len, 1.0, 1.0)
    assert _common(arm, wall) == pytest.approx(wall.volume)


def test_hooks_declared():
    kit = hanger_kit("gaudi", SPEC, P)
    assert [l.force_n for l in kit.loads] == [(0, 0, -SPEC.load_n / 2)] * 2
    assert {round(l.point[0]) for l in kit.loads} == {-190, 190}
    assert kit.supports[0].normal == (0.0, 0.0, 1.0)
    assert set(kit.tunables) == {"arm_t", "depth", "mount_h"}


def test_kit_is_cached():
    assert hanger_kit("gothic", SPEC, P) is hanger_kit("gothic", SPEC, P)


def test_bad_spec():
    with pytest.raises(ValueError, match="depth"):
        hanger_kit("gothic", dataclasses.replace(SPEC, depth=30), P)
    with pytest.raises(ValueError, match="unknown style"):
        hanger_kit("rococo", SPEC, P)


def test_kit_command(repo_copy, capsys):
    mount = repo_copy("parts/example-hanger-kit")
    repo_copy("parts/example-hanger-kit-arm-a")
    repo_copy("parts/example-hanger-kit-arm-b")
    assert main(["kit", str(mount)]) == 0
    assert "FAIL" not in capsys.readouterr().out
    assert (mount / "out" / "example-hanger-kit.3mf").exists()
