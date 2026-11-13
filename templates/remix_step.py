"""{{name}}: a remix of {{file}} (STEP: exact edits, as with your own part).

Build: uv run cad.py build remix/{{name}}
The original in source/ is read-only; everything is written to out/.
"""

from pathlib import Path

from build123d import Box, Cylinder, Pos, Rot, import_step  # noqa: F401

from cadlib import fasteners as f  # noqa: F401

HERE = Path(__file__).resolve().parent
SOURCE = "source/{{file}}"

# --- plan of edits (after `cad.py inspect`, 2–4 points) ---
# 1.
# 2.

# --- parameters, mm ---

NAME = "{{name}}"
EXPECTED_BODIES = 1
EXPECTED_VOLUME_DELTA = None    # mm³, if the change can be worked out in advance (checked to ±1%)
SECTION = None


def build(p):
    body = import_step(HERE / SOURCE)
    # Examples:
    # body -= Pos(x, y, z_top) * f.clearance_hole("M3", 10, p)
    # body += Pos(x, y, z) * Box(10, 10, 2)
    return body
