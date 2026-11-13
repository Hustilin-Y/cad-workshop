"""{{name}}: a remix of {{file}}.

Build: uv run cad.py build remix/{{name}}
The original in source/ is read-only; everything is written to out/.
"""

from pathlib import Path

from build123d import Box, Cylinder, Pos, Rot  # noqa: F401  tools to subtract/add

from cadlib import fasteners as f  # noqa: F401
from cadlib import mesh as m

HERE = Path(__file__).resolve().parent
SOURCE = "source/{{file}}"

# --- plan of edits (after `cad.py inspect`, 2–4 points) ---
# 1.
# 2.

# --- parameters, mm ---

NAME = "{{name}}"
FORMATS = ("stl", "3mf")        # STEP can't come from a mesh
EXPECTED_BODIES = 1
EXPECTED_VOLUME_DELTA = None    # mm³, if the change can be worked out in advance (checked to ±1%)
SECTION = None                  # "x" / "y" / "z" or ("y", 12.5)


def build(p):
    src = m.load_source(HERE / SOURCE)
    for note in src.notes:
        print(f"  original repaired: {note}")
    body = src.mesh
    # Examples:
    # body = m.subtract(body, Pos(x, y, z_top) * f.clearance_hole("M3", 10, p))
    # body = m.add(body, Pos(x, y, z) * Box(10, 10, 2))
    # body = m.scale(body, (1, 1, 1.2))
    # body = m.cut(body, normal=(0, 0, -1), origin=(0, 0, 30))   # keep everything below Z=30
    # body = m.drop_to_bed(m.rotate(body, (90, 0, 0)))          # lay it on its side
    return body
