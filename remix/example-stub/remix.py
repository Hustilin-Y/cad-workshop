"""example-stub: a remix of stub-block.stl — a through hole and a slot in a finished STL.

An example of the path "someone else's STL → edits by booleans → comparison with the original".
Build: uv run cad.py build remix/example-stub
"""

import math
from pathlib import Path

from build123d import Cylinder, Pos, SlotCenterToCenter, extrude

from cadlib import mesh as m

HERE = Path(__file__).resolve().parent
SOURCE = "source/stub-block.stl"

# --- plan of edits (after `cad.py inspect`: a 60 × 40 × 20 block, X −30…30, Y −20…20, Z 0…20) ---
# 1. A vertical through hole Ø8 in the left half.
# 2. A vertical through slot 6 × 20 along X in the right half.
# 3. The size stays; the volume drops by exactly the hole and the slot.

# --- parameters, mm ---
BLOCK_H = 20.0          # the original's height (from inspect)
HOLE_D = 8.0            # hole diameter
HOLE_X = -15.0          # hole centre in X
SLOT_W = 6.0            # slot width
SLOT_LEN = 20.0         # slot's full length along X
SLOT_X = 12.0           # slot centre in X
OVERSHOOT = 1.0         # the tool sticks out of the model above and below so no skin is left

NAME = "example-stub"
FORMATS = ("stl", "3mf")
EXPECTED_BODIES = 1
# Hole + slot (a stadium: the rectangle between the centres + a circle), over the block's full height.
EXPECTED_VOLUME_DELTA = -BLOCK_H * (math.pi * HOLE_D**2 / 4 + (SLOT_LEN - SLOT_W) * SLOT_W + math.pi * SLOT_W**2 / 4)
SECTION = ("y", 0.0)    # a section through the hole and the slot


def build(p):
    src = m.load_source(HERE / SOURCE)
    for note in src.notes:
        print(f"  original repaired: {note}")

    tool_h = BLOCK_H + 2 * OVERSHOOT
    hole = Pos(HOLE_X, 0, BLOCK_H / 2) * Cylinder(HOLE_D / 2, tool_h)
    slot = Pos(SLOT_X, 0, -OVERSHOOT) * extrude(SlotCenterToCenter(SLOT_LEN - SLOT_W, SLOT_W), amount=tool_h)
    return m.subtract(src.mesh, hole, slot)
