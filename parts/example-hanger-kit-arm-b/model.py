"""example-hanger-kit-arm-b: arm B of the hanger kit archetype, its cradle round the +X end (32 x 7.2 mm).

The parameters are in parts/example-hanger-kit/hanger_params.py. The arm's tenon slides into the
mount's socket from +Y until it snaps; the object's end lies in the cradle, open on top and on +Y.

Build: uv run cad.py build parts/example-hanger-kit-arm-b --set STYLE='gaudi'
"""

from pathlib import Path

from cadlib.shared import load_module
from cadlib.style.archetypes.hanger import hanger_kit

params = load_module(Path(__file__).resolve().parent.parent / "example-hanger-kit" / "hanger_params.py")

STYLE = params.STYLE    # gothic, gaudi, hitech, parametric or biomech
NAME = "example-hanger-kit-arm-b"
EXPECTED_BODIES = 1
PRINT_DOWN = "-y"       # lying on its side: every opening is a vertical through-cut, the tenon stands up


def build(p):
    pieces = hanger_kit(STYLE, params.SPEC, p).pieces
    if "arm-b" not in pieces:
        raise ValueError("arm B is split into segments for this span: give each segment a folder of its own")
    return pieces["arm-b"].solid
