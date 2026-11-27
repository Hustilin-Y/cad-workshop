"""example-hanger-kit-arm-a: arm A of the hanger kit archetype, its cradle round the -X end (32 x 16 mm).

The parameters are in parts/example-hanger-kit/hanger_params.py. The arm's tenon slides into the
mount's socket from +Y until it snaps; the object's end lies in the cradle, open on top and on +Y.

Build: uv run cad.py build parts/example-hanger-kit-arm-a --set STYLE='gaudi'
"""

from pathlib import Path

from cadlib.shared import load_module
from cadlib.style.archetypes.hanger import hanger_piece

params = load_module(Path(__file__).resolve().parent.parent / "example-hanger-kit" / "hanger_params.py")

STYLE = params.STYLE    # gothic, gaudi, hitech, parametric or biomech
NAME = "example-hanger-kit-arm-a"
EXPECTED_BODIES = 1
PRINT_DOWN = "-y"       # lying on its side: every opening is a vertical through-cut, the tenon stands up


def build(p):
    # A span too long for the bed splits the arm into arm-a-1, arm-a-2, ...: then the piece
    # is not found, and each segment needs a folder of its own.
    return hanger_piece(STYLE, params.SPEC, p, "arm-a").solid
