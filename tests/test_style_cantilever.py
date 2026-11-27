import importlib
import time
from dataclasses import replace

import numpy as np
import pytest

from cad import main
from cadlib.config import load_profile
from cadlib.export import shape_to_mesh
from cadlib.style.archetypes import CantileverSpec, cantilever
from cadlib.style.dialects import get_dialect
from cadlib.style.lattice import _inside, _point_seg_dist
from style_checks import assert_printable

# The package re-exports the function under the module's name, so reach the module itself.
CANTILEVER = importlib.import_module("cadlib.style.archetypes.cantilever")

P = load_profile()
STYLES = ["gothic", "gaudi", "hitech", "parametric", "biomech"]
SPEC = CantileverSpec(reach=120, height=90, depth=20, root_t=10, plate_t=6)


@pytest.mark.slow
@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("down", ["-y", "-x"])
def test_cantilever_printable(style, down):
    a = cantilever(style, SPEC, P, down)
    assert a.solid.is_valid and len(a.solid.solids()) == 1
    assert a.print_down == down and a.allowed_print_down == ("-y", "-x")
    mesh = shape_to_mesh(a.solid)
    assert_printable(mesh, down, P)
    # Every keyhole channel is closed in front by material (the plate or its boss), in both orientations.
    g = CANTILEVER._frame(SPEC, P, get_dialect(style), down)
    for k in CANTILEVER._keyholes(g):
        probes = [(k.front + P.min_wall_mm / 2, 0.0, z) for z in np.linspace(k.z - k.slide, k.z, 5)]
        assert mesh.contains(probes).all(), f"keyhole at z={k.z:.1f} open in front"


def test_bad_print_down():
    with pytest.raises(ValueError, match="-y.*-x"):
        cantilever("gothic", SPEC, P, "z")


def test_hooks_declared():
    a = cantilever("gaudi", SPEC, P)
    assert a.loads[0].force_n == (0, 0, -20.0) and a.supports and "root_t" in a.tunables
    t = a.tunables["root_t"]
    assert t.lo == 2 * P.min_wall_mm and t.hi == SPEC.height / 3 and t.value == SPEC.root_t
    assert a.supports[0].normal == (-1.0, 0.0, 0.0)


@pytest.mark.slow
@pytest.mark.parametrize("style", STYLES)
def test_example_builds_fast(style, repo_copy, capsys, within_budget):
    folder = repo_copy("parts/example-styles")
    t0 = time.perf_counter()
    assert main(["build", str(folder), "--set", f"STYLE={style!r}"]) == 0
    within_budget(time.perf_counter() - t0, 30)
    assert "FAIL" not in capsys.readouterr().out


def test_unknown_style_via_set(repo_copy, capsys):
    assert main(["build", str(repo_copy("parts/example-styles")), "--set", "STYLE='gotic'"]) != 0
    captured = capsys.readouterr()
    assert "gothic, gaudi, hitech, parametric, biomech" in captured.out + captured.err


@pytest.mark.parametrize("count", [1, 3])
def test_screw_count(count):
    a = cantilever("gaudi", replace(SPEC, screw_count=count), P)
    assert a.solid.is_valid and len(a.solid.solids()) == 1
    g = CANTILEVER._frame(replace(SPEC, screw_count=count), P, get_dialect("gaudi"), "-y")
    keys = CANTILEVER._keyholes(g)
    assert len(keys) == count
    for lower, upper in zip(keys[1:], keys):
        # keep-out discs apart and the footprints separated by a wall
        assert upper.z - lower.z >= 2 * g.keep_r
        assert lower.z_hi + P.min_wall_mm <= upper.z_lo


def test_too_many_screws():
    with pytest.raises(ValueError, match="no room for 6"):
        cantilever("gaudi", replace(SPEC, screw_count=6), P)


@pytest.mark.parametrize("style", ["parametric", "hitech"])
@pytest.mark.parametrize("down", ["-y", "-x"])
def test_lattice_clear_of_keyholes(style, down):
    """No lattice cell comes within bar_min (min_wall) of a keyhole's outline in the elevation."""
    g = CANTILEVER._frame(SPEC, P, get_dialect(style), down)
    keys = CANTILEVER._keyholes(g)
    keepouts = [CANTILEVER.poly(CANTILEVER._keyhole_footprint(g, k, P.min_wall_mm)) for k in keys]
    cut = CANTILEVER._lattice_cut(g, CANTILEVER._BUILDERS[style](g), keepouts, down, g.edge)
    assert cut is not None and cut.tool is not None and cut.kept > 10
    for k in keys:
        foot = np.array(CANTILEVER._keyhole_footprint(g, k, 0.0))
        fa, fb = foot, np.roll(foot, -1, axis=0)
        for face in cut.tool.faces():
            hole = np.array([((e @ 0).X, (e @ 0).Z) for e in face.outer_wire().edges()])  # in wire order
            assert not _inside(hole, fa, fb).any()
            assert _point_seg_dist(hole, fa, fb).min() >= P.min_wall_mm - 1e-6
            assert _point_seg_dist(foot, hole, np.roll(hole, -1, axis=0)).min() >= P.min_wall_mm - 1e-6
