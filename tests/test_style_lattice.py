import math
import time

import pytest
from build123d import Box, Circle, Plane, Pos, Rectangle, extrude

from cadlib.config import load_profile
from cadlib.export import shape_to_mesh
from cadlib.style import log
from cadlib.style.lattice import lattice
from cadlib.style.plane import in_plane_up
from style_checks import assert_printable

P = load_profile()


def test_uniform_hex_fills_panel():
    cut = lattice(Rectangle(80, 50), P)
    assert cut.kept > 20 and cut.tool is not None
    assert cut.tool.area < Rectangle(80, 50).area


def test_tiny_panel_stays_solid():
    log.drain()
    cut = lattice(Rectangle(5, 5), P)
    assert cut.tool is None and cut.kept == 0
    assert any("left solid" in n.message for n in log.drain())


def test_keepout_respected():
    hole = Pos(0, 0) * Circle(8)
    cut = lattice(Rectangle(80, 50), P, keepout=[hole])
    assert (cut.tool & hole).area == 0
    assert cut.dropped > 0


def test_keepout_grown_by_bar_min():
    hole = Pos(0, 0) * Circle(8)
    grown = Pos(0, 0) * Circle(8 + P.min_wall_mm - 0.01)
    cut = lattice(Rectangle(80, 50), P, keepout=[hole])
    assert (cut.tool & grown).area == 0


def test_border_margin_is_bar_min():
    cut = lattice(Rectangle(80, 50), P)
    bb = cut.tool.bounding_box()
    assert bb.max.X <= 40 - P.min_wall_mm + 1e-6 and bb.min.X >= -40 + P.min_wall_mm - 1e-6
    assert bb.max.Y <= 25 - P.min_wall_mm + 1e-6 and bb.min.Y >= -25 + P.min_wall_mm - 1e-6


def test_graded_bars_remove_less_where_field_is_high():
    left = lattice(Rectangle(80, 50), P, bar_max=3 * P.min_wall_mm, field=lambda u, v: 1.0)
    right = lattice(Rectangle(80, 50), P, bar_max=3 * P.min_wall_mm, field=lambda u, v: 0.0)
    assert left.tool.area < right.tool.area


def test_big_nozzle_rederives():
    p8 = load_profile(nozzle=0.8)
    cut = lattice(Rectangle(80, 50), p8)
    assert 0 < cut.kept < lattice(Rectangle(80, 50), P).kept


def test_cell_below_floor_rejected():
    with pytest.raises(ValueError, match="min"):
        lattice(Rectangle(80, 50), P, cell=2.0)


def test_bar_below_floor_rejected():
    with pytest.raises(ValueError, match="min_wall"):
        lattice(Rectangle(80, 50), P, bar_min=0.5)


def test_tri_fills_panel_and_respects_keepout():
    hole = Pos(10, 0) * Circle(6)
    cut = lattice(Rectangle(80, 50), P, kind="tri", keepout=[hole])
    assert cut.kept > 20
    assert (cut.tool & hole).area == 0


def test_up_flat_top_bridge_limit():
    ok = lattice(Rectangle(80, 50), P, up=(0.0, 1.0))
    assert ok.kept > 20
    with pytest.raises(ValueError, match="max_bridge"):
        lattice(Rectangle(120, 80), P, cell=40.0, up=(0.0, 1.0))
    # Pointy-top (no up) has no top edge to limit.
    assert lattice(Rectangle(120, 80), P, cell=40.0).kept > 0


def test_tri_up_bridge_limit():
    with pytest.raises(ValueError, match="max_bridge"):
        lattice(Rectangle(120, 80), P, kind="tri", cell=20.0, up=(0.0, 1.0))


def test_circle_region():
    cut = lattice(Circle(30), P)
    assert cut.kept > 20
    assert (cut.tool - Circle(30 - P.min_wall_mm + 0.02).faces()[0]).area < 0.05


def test_log_info_for_dropped():
    log.drain()
    lattice(Rectangle(80, 50), P)
    assert any(n.level == "info" and "dropped" in n.message for n in log.drain())


def test_large_panel_is_fast():
    t = time.perf_counter()
    cut = lattice(Rectangle(200, 140), P)
    assert time.perf_counter() - t < 10
    assert cut.kept > 500


# --- organic ---------------------------------------------------------------------------------------

def _corner_field(u, v):
    return max(0.0, 1.0 - math.hypot(u + 50, v - 35) / 110)


def test_organic_is_deterministic_per_seed():
    a = lattice(Rectangle(100, 70), P, kind="organic", cell=7.2, bar_max=3.6, field=_corner_field)
    b = lattice(Rectangle(100, 70), P, kind="organic", cell=7.2, bar_max=3.6, field=_corner_field)
    c = lattice(Rectangle(100, 70), P, kind="organic", cell=7.2, bar_max=3.6, field=_corner_field, seed=1)
    assert a.kept == b.kept and abs(a.tool.area - b.tool.area) < 1e-6
    assert abs(a.tool.area - c.tool.area) > 1.0


def test_organic_cells_follow_the_field():
    dense = lattice(Rectangle(100, 70), P, kind="organic", cell=7.2, field=lambda u, v: 1.0)
    sparse = lattice(Rectangle(100, 70), P, kind="organic", cell=7.2, field=lambda u, v: 0.0)
    assert dense.kept > 2 * sparse.kept
    sizes = [f.area for f in lattice(Rectangle(100, 70), P, kind="organic", cell=7.2, field=_corner_field).tool.faces()]
    assert max(sizes) > 3 * min(sizes)  # cell sizes visibly vary


def test_organic_keepout_respected():
    hole = Pos(0, 0) * Circle(8)
    cut = lattice(Rectangle(100, 70), P, kind="organic", cell=7.2, keepout=[hole])
    assert cut.tool is not None and (cut.tool & hole).area == 0


def test_organic_floors():
    with pytest.raises(ValueError, match="below the floor"):
        lattice(Rectangle(100, 70), P, kind="organic", cell=3.0)
    with pytest.raises(ValueError, match="bar_min"):
        lattice(Rectangle(100, 70), P, kind="organic", bar_min=0.5)
    with pytest.raises(ValueError, match="leaves no hole"):
        lattice(Rectangle(100, 70), P, kind="organic", cell=6.0, bar_max=6.0)


def test_organic_upright_prints():
    region = Plane.XZ * Rectangle(100, 70)
    cut = lattice(region, P, kind="organic", cell=7.2, bar_max=3.6, field=_corner_field,
                  up=in_plane_up(Plane(region.faces()[0]), "-z"))
    body = Box(100, 20, 70) - extrude(cut.tool, amount=11, both=True)
    assert len(body.solids()) == 1
    assert_printable(shape_to_mesh(body), None, P)
