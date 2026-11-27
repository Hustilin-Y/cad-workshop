from build123d import Box, Pos

from cadlib.config import load_profile
from cadlib.export import shape_to_mesh
from style_checks import steep_overhang_area, thinnest_wall

P = load_profile()


def test_box_has_no_steep_area():
    assert steep_overhang_area(shape_to_mesh(Box(20, 20, 20)), None, P.max_bridge_mm) <= 1.0


def test_wide_shelf_is_steep():
    t = Pos(0, 0, 10) * Box(10, 10, 20) + Pos(15, 0, 18) * Box(30, 12, 4)  # 25 x 12 mm unsupported underside
    assert steep_overhang_area(shape_to_mesh(t), None, P.max_bridge_mm) > 100


def test_short_bridge_is_exempt():
    # two pillars 8 mm apart joined at the top: an 8 mm bridge
    t = Pos(-6, 0, 5) * Box(4, 10, 10) + Pos(6, 0, 5) * Box(4, 10, 10) + Pos(0, 0, 11) * Box(16, 10, 2)
    assert steep_overhang_area(shape_to_mesh(t), None, P.max_bridge_mm) <= 1.0


def test_one_end_ledge_is_not_a_bridge():
    # a 6 mm ledge, 2.4 mm wide, sticking out of a wall: held on one side only
    t = Pos(0, 0, 10) * Box(10, 10, 20) + Pos(8, 0, 15) * Box(6, 2.4, 2)
    assert steep_overhang_area(shape_to_mesh(t), None, P.max_bridge_mm) > 10


def test_thin_fin_is_found():
    t = Box(20, 20, 4) + Pos(0, 0, 7) * Box(20, 0.8, 10)
    assert thinnest_wall(shape_to_mesh(t)) < 1.0
