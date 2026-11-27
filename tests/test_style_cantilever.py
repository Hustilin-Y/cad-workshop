import time

import pytest

from cad import main
from cadlib.config import load_profile
from cadlib.export import shape_to_mesh
from cadlib.style.archetypes import CantileverSpec, cantilever
from style_checks import assert_printable

P = load_profile()
STYLES = ["gothic", "gaudi", "hitech", "parametric"]
SPEC = CantileverSpec(reach=120, height=90, depth=20, root_t=10, plate_t=6)


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("down", ["-y", "-x"])
def test_cantilever_printable(style, down):
    a = cantilever(style, SPEC, P, down)
    assert a.solid.is_valid and len(a.solid.solids()) == 1
    assert a.print_down == down and a.allowed_print_down == ("-y", "-x")
    assert_printable(shape_to_mesh(a.solid), down, P)


def test_bad_print_down():
    with pytest.raises(ValueError, match="-y.*-x"):
        cantilever("gothic", SPEC, P, "z")


def test_hooks_declared():
    a = cantilever("gaudi", SPEC, P)
    assert a.loads[0].force_n == (0, 0, -20.0) and a.supports and "root_t" in a.tunables
    t = a.tunables["root_t"]
    assert t.lo == 2 * P.min_wall_mm and t.hi == SPEC.height / 3 and t.value == SPEC.root_t
    assert a.supports[0].normal == (-1.0, 0.0, 0.0)


@pytest.mark.parametrize("style", STYLES)
def test_example_builds_fast(style, repo_copy, capsys):
    folder = repo_copy("parts/example-styles")
    t0 = time.perf_counter()
    assert main(["build", str(folder), "--set", f"STYLE={style!r}"]) == 0
    assert time.perf_counter() - t0 < 30
    assert "FAIL" not in capsys.readouterr().out


def test_unknown_style_via_set(repo_copy, capsys):
    assert main(["build", str(repo_copy("parts/example-styles")), "--set", "STYLE='gotic'"]) != 0
    captured = capsys.readouterr()
    assert "gothic, gaudi, hitech, parametric" in captured.out + captured.err
