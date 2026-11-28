"""openGrid test pieces: a back with a Multiconnect slot and a tile on an openGrid snap.

Print both, then lower the slot piece onto an official Multiconnect snap in a board, open end
first (it should click into the detent and hold), and push the tile into a full board cell (it
should click in and need a firm pull to come out). Sizes come from cadlib.opengrid (the openGrid standard), not from
printer.toml: if a fit is off, the printer needs calibrating, not the interface.

openGrid/Multiconnect interface: dimensions from openGrid by David D, CC BY
(https://makerworld.com/en/models/1179191-opengrid-wall-desk-mounting-framework-ecosystem).

Build: uv run cad.py build calibration/opengrid
"""

from build123d import Box, Polygon, Pos, Rot, extrude

from cadlib import opengrid as og

# --- parameters, mm ---
BACK = og.BACK_MM        # thickness of the slot piece (the official backs are 6.4)
SLOT_PIECE_W = og.PITCH  # slot piece along X: one grid cell
SLOT_LEN = 26.0          # connector centre down to the open end of the slot (the piece's lower edge)
END_MARGIN = 14.0        # connector centre up to the piece's upper edge (half a cell)
TILE_T = 2.0             # tile on the snap, stands in for a part
GAP = 12.0               # between the two pieces on the bed

NAME = "opengrid-test"
EXPECTED_BODIES = 2
SECTION = ("y", SLOT_LEN - 3.55)     # through the detent, just below the connector
PRINT_HINTS = {"goal": ["fit", "cheap"], "goal_reason": "test pieces for the openGrid and Multiconnect fits"}


def _validate(p) -> None:
    og.require_back(BACK, p)
    og.require_cells(SLOT_PIECE_W)


def slot_piece():
    """Front on the bed, back up: the slot opens upward, so the dovetail needs no support.

    +Y is up on the wall: the slot's open end is the piece's lower edge (Y = 0).
    """
    length = END_MARGIN + SLOT_LEN
    body = Pos(0, length / 2, BACK / 2) * Box(SLOT_PIECE_W, length, BACK)
    return body - Pos(0, SLOT_LEN, BACK) * og.multiconnect_slot(SLOT_LEN, detent=True)


def snap_tile():
    """Wall side of the snap on the bed, the tile on top, as the official snaps are printed."""
    half = og.SNAP_FLATS / 2
    c = og.SNAP_WEDGE[2] - half   # the tile's corners follow the snap's front face, so nothing overhangs
    outline = [(c, -half), (half, -c), (half, c), (c, half), (-c, half), (-half, c), (-half, -c), (-c, -half)]
    h = og.SNAP_HEIGHT
    tile = Pos(0, 0, h) * extrude(Polygon(*outline, align=None), amount=TILE_T)
    return tile + Pos(0, 0, h) * Rot(180, 0, 0) * og.snap()


def build(p):
    _validate(p)
    x = SLOT_PIECE_W / 2 + GAP + og.SNAP_FLATS / 2 + og.SNAP_BUMP
    return slot_piece() + Pos(x, (END_MARGIN + SLOT_LEN) / 2, 0) * snap_tile()
