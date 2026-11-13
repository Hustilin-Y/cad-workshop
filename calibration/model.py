"""Tolerance calibration: a row of D+c holes and D−c pins, plus a key with an exact D.

The key tries every hole (with its pin) and every pin (with its ring).
The value of c giving the wanted kind of fit goes into printer.toml.
"""

from build123d import Box, Cylinder, Pos, extrude

from cadlib.text import label

# --- parameters, mm ---
NOMINAL_D = 8.0                                     # nominal diameter of the key's pin/hole
CLEARANCES = [round(i * 0.05, 2) for i in range(11)]  # 0.00 … 0.50 in steps of 0.05, clearance on the diameter
PITCH = 13.0                                        # pitch between holes along X
MARGIN_X = 9.0                                      # from the plate's edge to the first hole's centre
PLATE_DEPTH = 36.0                                  # plate along Y
PLATE_T = 3.0                                       # plate thickness = hole depth
PIN_ROW_Y = 8.0                                     # row of pins
LABEL_ROW_Y = 18.0                                  # row of labels
HOLE_ROW_Y = 28.0                                   # row of holes
PIN_H = 8.0                                         # pin height above the plate
LABEL_SIZE = 4.0                                    # label font height
LABEL_RELIEF = 0.6                                  # label relief height (3 layers of 0.2)
KEY_GAP = 8.0                                       # gap between the plate and the key on the bed
KEY_RING_WALL = 3.0                                 # wall of the key's ring
KEY_BAR_W = 10.0                                    # width of the key's bar
KEY_LEN = 50.0                                      # distance between the key's ring and pin centres

NAME = "tolerance-gauge"
EXPECTED_BODIES = 2                                 # plate + key
SECTION = ("y", HOLE_ROW_Y)                         # a section through the row of holes in the preview


def _label(c: float) -> str:
    return f"{c:.2f}".lstrip("0")                   # ".05", ".50"; zero as ".00"


def plate():
    length = 2 * MARGIN_X + PITCH * (len(CLEARANCES) - 1)
    xs = [MARGIN_X + i * PITCH for i in range(len(CLEARANCES))]
    body = Pos(length / 2, PLATE_DEPTH / 2, PLATE_T / 2) * Box(length, PLATE_DEPTH, PLATE_T)
    # Booleans as a list, not one by one: OCCT does them in one pass, several times faster.
    body -= [Pos(x, HOLE_ROW_Y, PLATE_T / 2) * Cylinder((NOMINAL_D + c) / 2, PLATE_T) for x, c in zip(xs, CLEARANCES)]
    pins = [Pos(x, PIN_ROW_Y, PLATE_T + PIN_H / 2) * Cylinder((NOMINAL_D - c) / 2, PIN_H) for x, c in zip(xs, CLEARANCES)]
    labels = [
        extrude(Pos(x, LABEL_ROW_Y, PLATE_T) * label(_label(c), LABEL_SIZE), amount=LABEL_RELIEF)
        for x, c in zip(xs, CLEARANCES)
    ]
    return body + pins + labels


def key():
    """A ring with a hole of exactly D and a pin of exactly D on one bar."""
    ring_r = NOMINAL_D / 2 + KEY_RING_WALL
    y = -KEY_GAP - ring_r
    x0 = MARGIN_X
    x1 = x0 + KEY_LEN
    body = Pos(x0, y, PLATE_T / 2) * Cylinder(ring_r, PLATE_T)
    body += Pos((x0 + x1) / 2, y, PLATE_T / 2) * Box(KEY_LEN, KEY_BAR_W, PLATE_T)
    body += Pos(x1, y, PLATE_T / 2) * Cylinder(ring_r, PLATE_T)
    body -= Pos(x0, y, PLATE_T / 2) * Cylinder(NOMINAL_D / 2, PLATE_T)
    body += Pos(x1, y, PLATE_T + PIN_H / 2) * Cylinder(NOMINAL_D / 2, PIN_H)
    text = label(f"D{NOMINAL_D:g}", LABEL_SIZE)
    body += extrude(Pos((x0 + x1) / 2, y, PLATE_T) * text, amount=LABEL_RELIEF)
    return body


def build(p):
    # The profile doesn't affect the geometry: the sample measures tolerances, it doesn't use them.
    return plate() + key()
