"""example-hanger-kit: the ceiling mount of the hanger kit archetype (piece 1 of 3).

The parameters are in hanger_params.py next to this file; the arms are in
parts/example-hanger-kit-arm-a and -arm-b. The mount is screwed up into the ceiling with two
countersunk 3 mm wood screws, the arms slide into its dovetail sockets from +Y.

Build: uv run cad.py build parts/example-hanger-kit --set STYLE='gaudi'
All pieces on plates: uv run cad.py kit parts/example-hanger-kit
"""

from pathlib import Path

from cadlib.shared import load_module
from cadlib.style.archetypes.hanger import hanger_kit

params = load_module(Path(__file__).resolve().parent / "hanger_params.py")

STYLE = params.STYLE    # gothic, gaudi, hitech, parametric or biomech
NAME = "example-hanger-kit-mount"
EXPECTED_BODIES = 1
PRINT_DOWN = "-y"       # on its side: the sockets' closed ends on the bed, the screws lie across


def build(p):
    return hanger_kit(STYLE, params.SPEC, p).pieces["mount"].solid
