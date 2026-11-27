"""example-styles: the cantilever bracket archetype of cadlib.style in one of four dialects.

A wall plate with two screws, an arm along +X with an eye at the tip and the bracing between them.
The plate's back (x = -PLATE_T) goes against the wall, the arm's top is at z = HEIGHT, the depth
runs along Y. Try the dialects with --set:

Build: uv run cad.py build parts/example-styles --set STYLE='gaudi'
"""

from cadlib.style.archetypes import CantileverSpec, cantilever

# --- parameters, mm ---
STYLE = "gothic"        # gothic, gaudi, hitech or parametric
REACH = 120.0           # arm length from the plate's front face to the tip
HEIGHT = 90.0           # plate height; the arm's top is at this height
DEPTH = 20.0            # thickness of the bracket along Y (the extrusion)
ROOT_T = 10.0           # arm thickness at the plate
PLATE_T = 6.0           # wall plate thickness

NAME = "example-styles"
EXPECTED_BODIES = 1
PRINT_DOWN = "-y"       # lying on its side: every opening is a vertical through-cut, the load acts along the layers


def build(p):
    spec = CantileverSpec(reach=REACH, height=HEIGHT, depth=DEPTH, root_t=ROOT_T, plate_t=PLATE_T)
    return cantilever(STYLE, spec, p, PRINT_DOWN).solid
