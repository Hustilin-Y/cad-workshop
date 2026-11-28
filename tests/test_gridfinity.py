"""Gridfinity: standard sizes, drawer layout, split into bed-sized pieces, plates and bins."""

import pytest
from build123d import Pos

from cadlib import gridfinity as gf
from cadlib.config import load_profile

P = load_profile()


def _vol(shape):
    """Volume of a boolean result; an empty intersection comes back as None."""
    return 0.0 if shape is None else shape.volume


def profile(**kw):
    return load_profile(**kw) if kw else P


# --- layout and split ---------------------------------------------------------


def test_joint_fit_from_profile():
    assert P.gridfinity_joint_mm == pytest.approx(0.1)
    assert load_profile(material="PETG").gridfinity_joint_mm == pytest.approx(0.15)


def test_drawer_525x296_pla():
    lay = gf.baseplate_layout(525, 296, P)
    assert (lay.cells_x, lay.cells_y) == (12, 7)
    assert lay.rim[0] == pytest.approx(lay.rim[1])
    assert lay.rim[0] + lay.rim[1] == pytest.approx(525 - 504 - 2 * lay.gap_x)
    assert lay.rim[2:] == (0, 0)          # 2 mm left across: below min_wall, stays gap
    assert lay.gap_y == pytest.approx(1.0)
    assert lay.gap_x >= P.slide_fit_mm


def test_drawer_525x296_petg_still_7():
    assert gf.baseplate_layout(525, 296, profile(material="PETG")).cells_y == 7


def test_tight_width_drops_a_cell():
    lay = gf.baseplate_layout(525, 294.5, P)
    assert lay.cells_y == 6 and sum(lay.rim[2:]) > 40


def test_align_minus_y_puts_rim_on_plus_y():
    lay = gf.baseplate_layout(300, 525, P, align="-y")
    assert lay.rim[2] == 0 and lay.rim[3] > 0
    assert lay.rim[0] == pytest.approx(lay.rim[1])     # the other axis stays centred


def test_bad_align():
    with pytest.raises(ValueError, match="align"):
        gf.baseplate_layout(300, 300, P, align="left")


def test_too_small_drawer():
    with pytest.raises(ValueError, match="one cell"):
        gf.baseplate_layout(40, 200, P)


def test_max_piece_cells_p2s():
    assert gf.max_piece_cells(P) == 5


@pytest.mark.parametrize("n,lim,out", [(12, 5, [4, 4, 4]), (7, 5, [4, 3]), (6, 5, [3, 3]), (5, 5, [5]), (1, 5, [1])])
def test_split_counts(n, lim, out):
    assert gf.split_counts(n, lim) == out


def _fits_bed(pieces, p):
    ux, uy, _ = p.usable_volume_mm
    for pc in pieces:
        assert pc.cells_x * gf.PITCH + pc.rim[0] + pc.rim[1] <= ux + 1e-9
        assert pc.cells_y * gf.PITCH + pc.rim[2] + pc.rim[3] <= uy + 1e-9


def test_split_12x7_fits_bed_and_counts():
    lay = gf.baseplate_layout(525, 296, P)
    pieces = gf.split(lay, P)
    assert sum(pc.count for pc in pieces) == 6
    assert sum(pc.count * pc.cells_x * pc.cells_y for pc in pieces) == 84
    _fits_bed(pieces, P)


def test_split_6x6_fits_bed():
    pieces = gf.split(gf.baseplate_layout(6 * 42 + 3, 6 * 42 + 3, P), P)
    assert sum(pc.count * pc.cells_x * pc.cells_y for pc in pieces) == 36
    _fits_bed(pieces, P)


def test_wide_rim_pushes_a_cell_off_the_edge_piece():
    # 5 cells and a 40 mm rim on one side: 5 × 42 + 40 = 250 is over 246, so the axis splits in two
    lay = gf.baseplate_layout(5 * 42 + 41, 100, P, align="-x")
    pieces = gf.split(lay, P)
    _fits_bed(pieces, P)
    assert sum(pc.count * pc.cells_x for pc in pieces if pc.cells_y == lay.cells_y) == 5


def test_identical_pieces_are_grouped():
    pieces = gf.split(gf.baseplate_layout(8 * 42 + 1, 42 + 1, P), P)   # 4 + 4, no rim
    assert [(pc.cells_x, pc.cells_y, pc.count) for pc in pieces] == [(4, 1, 2)]


# --- plate pieces -------------------------------------------------------------


def test_plate_2x2_size_and_height():
    plate = gf.baseplate(2, 2, P)
    bb = plate.bounding_box()
    assert bb.size.X == pytest.approx(84) and bb.size.Y == pytest.approx(84)
    assert bb.size.Z == pytest.approx(gf.PLATE_HEIGHT)
    assert bb.min.Z == pytest.approx(0, abs=1e-6)
    assert plate.is_valid


def test_plate_cells_are_open_through():
    from build123d import Box, Pos
    # the cell centre is empty all the way down: a thin probe through it hits nothing
    probe = Pos(21, 21, gf.PLATE_HEIGHT / 2) * Box(1, 1, gf.PLATE_HEIGHT * 2)
    assert _vol(gf.baseplate(2, 2, P) & probe) == pytest.approx(0, abs=1e-6)


def test_plate_cell_top_opening_is_the_pitch():
    from build123d import Box, Pos
    # at the very top the frame between two cells is a knife edge: a probe 0.2 below the top,
    # 0.5 off the cell boundary, sits inside the cell's chamfer (empty)
    probe = Pos(42 - 0.5, 21, gf.PLATE_HEIGHT - 0.1) * Box(0.1, 0.1, 0.1)
    assert _vol(gf.baseplate(2, 2, P) & probe) == pytest.approx(0, abs=1e-9)


def test_plate_rim_adds_width_and_is_solid():
    from build123d import Box, Pos
    plate = gf.baseplate(2, 1, P, rim=(10, 0, 0, 0))
    bb = plate.bounding_box()
    assert bb.size.X == pytest.approx(94)
    assert plate.is_valid
    rim_probe = Pos(bb.min.X + 5, bb.center().Y, gf.PLATE_HEIGHT / 2) * Box(8, 30, gf.PLATE_HEIGHT - 0.2)
    assert (plate & rim_probe).volume == pytest.approx(rim_probe.volume, rel=1e-6)


def test_plate_magnet_pockets_remove_volume():
    a = gf.baseplate(1, 1, P, magnets="6x2")
    b = gf.baseplate(1, 1, P, magnets="5x2")
    assert a.is_valid and a.bounding_box().size.Z > gf.PLATE_HEIGHT   # a floor for the pockets
    assert a.volume < b.volume                                            # bigger pockets, less plastic


def test_plate_magnet_too_big():
    with pytest.raises(ValueError, match="magnet"):
        gf.baseplate(1, 1, P, magnets="10x3")


def test_piece_body_matches_piece():
    pc = gf.Piece("a", 2, 1, (5, 0, 0, 3), 1)
    bb = gf.piece_body(pc, P).bounding_box()
    assert (bb.size.X, bb.size.Y) == (pytest.approx(89), pytest.approx(45))


# --- bins ---------------------------------------------------------------------


def test_bin_1x1_footprint_and_height():
    b = gf.bin_body(1, 1, 3, P, lip=False)
    bb = b.bounding_box()
    assert bb.size.X == pytest.approx(gf.BIN_SIZE) and bb.size.Y == pytest.approx(gf.BIN_SIZE)
    assert bb.size.Z == pytest.approx(3 * gf.UNIT_H)
    assert bb.min.Z == pytest.approx(0, abs=1e-6)
    assert b.is_valid


def test_bin_lip_on_top():
    assert gf.bin_body(1, 1, 3, P).bounding_box().size.Z == pytest.approx(3 * gf.UNIT_H + gf.LIP_HEIGHT)


def test_bin_2x1_footprint():
    assert gf.bin_body(2, 1, 3, P).bounding_box().size.X == pytest.approx(2 * gf.PITCH - (gf.PITCH - gf.BIN_SIZE))


def test_bin_is_hollow():
    from build123d import Box, Pos
    probe = Pos(0, 0, 3 * gf.UNIT_H - 2) * Box(5, 5, 2)
    assert _vol(gf.bin_body(1, 1, 3, P) & probe) == pytest.approx(0, abs=1e-6)


def test_bin_drops_into_plate():
    # the bin's foot sits inside the plate's cell with the standard clearance: no overlap
    plate = gf.baseplate(1, 1, P)
    b = Pos(21, 21, 0) * gf.bin_body(1, 1, 2, P, lip=False)
    assert _vol(plate & b) < 1e-3


def test_bin_divisions_add_walls():
    assert gf.bin_body(2, 1, 3, P, divisions=(2, 1)).volume > gf.bin_body(2, 1, 3, P).volume


def test_bin_widths_compartments():
    a = gf.bin_body(2, 1, 3, P, widths=[30, 40])
    assert a.volume > gf.bin_body(2, 1, 3, P).volume
    with pytest.raises(ValueError, match="widths"):
        gf.bin_body(1, 1, 3, P, widths=[30, 30])


def test_bin_label_shelf_builds():
    plain = gf.bin_body(1, 1, 3, P)
    shelf = gf.bin_body(1, 1, 3, P, shelf=True)
    lab = gf.bin_body(1, 1, 3, P, shelf=True, label="M3")
    assert shelf.is_valid and lab.is_valid
    assert plain.volume < lab.volume < shelf.volume       # the text is debossed into the shelf


def test_label_needs_shelf():
    with pytest.raises(ValueError, match="shelf"):
        gf.bin_body(1, 1, 3, P, label="M3")


def test_tool_pockets_cut_volume():
    full = gf.bin_body(2, 1, 4, P, solid=True)
    cut = gf.bin_body(2, 1, 4, P, solid=True, pockets=[gf.Pocket("circle", (12,), 15, (0, 0))])
    slot = gf.bin_body(2, 1, 4, P, solid=True, pockets=[gf.Pocket("slot", (8, 40), 10, (0, 0), angle=30, notch=True)])
    assert cut.volume < full.volume and slot.volume < full.volume
    assert slot.is_valid


def test_pocket_too_wide():
    with pytest.raises(ValueError, match="pocket"):
        gf.bin_body(1, 1, 3, P, solid=True, pockets=[gf.Pocket("rect", (50, 10), 5, (0, 0))])


def test_pocket_too_deep():
    with pytest.raises(ValueError, match="deep"):
        gf.bin_body(1, 1, 3, P, solid=True, pockets=[gf.Pocket("circle", (10,), 30, (0, 0))])


def test_pockets_need_solid():
    with pytest.raises(ValueError, match="solid"):
        gf.bin_body(1, 1, 3, P, pockets=[gf.Pocket("circle", (10,), 5, (0, 0))])


def test_compartment_too_narrow():
    with pytest.raises(ValueError, match="compartment"):
        gf.bin_body(1, 1, 3, P, divisions=(30, 1))


def test_magnet_too_thick_for_base():
    with pytest.raises(ValueError, match="magnet"):
        gf.bin_body(1, 1, 3, P, magnets="6x7")


def test_bin_magnets_cut_the_feet():
    assert gf.bin_body(1, 1, 3, P, magnets="6x2").volume < gf.bin_body(1, 1, 3, P).volume


def test_bin_units_at_least_one():
    with pytest.raises(ValueError, match="units"):
        gf.bin_body(1, 1, 0, P)


def test_multi_cell_bin_rests_on_the_plate_ridges():
    # The standard's numbers (BASE_HEIGHT − BASE_PROFILE_HEIGHT = 2.25 bridge, plate 5.0 high) leave
    # the knife ridges between plate cells 0.25 above the bin's bridge: a 2 × 1 bin sits on them,
    # 0.25 up, as in kennetek's model. Pinned so a change to that is a decision, not an accident.
    plate = gf.baseplate(2, 1, P)
    b = gf.bin_body(2, 1, 2, P, lip=False)
    assert _vol(plate & Pos(42, 21, 0) * b) > 1.0
    assert _vol(plate & Pos(42, 21, 0.25 + 1e-3) * b) < 1e-3
