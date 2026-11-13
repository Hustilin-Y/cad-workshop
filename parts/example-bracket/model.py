"""example-bracket: an L-shaped bracket with two M4 holes and a rounded inner corner.

The shelf runs along +X, the post rises along +Z, the width is along Y. The shelf's screw enters
from above, the post's screw from the inside (the shelf's side).

Build: uv run cad.py build parts/example-bracket
"""

from build123d import Axis, Box, Pos, Rot, fillet

from cadlib import fasteners as f

# --- parameters, mm ---
LEG_X = 40.0            # shelf length along X (from the post's outer side)
LEG_Z = 40.0            # post height along Z (from the bottom of the shelf)
WIDTH = 25.0            # bracket width along Y
THICKNESS = 5.0         # thickness of the shelf and the post
INNER_FILLET = 6.0      # inner corner radius: relieves the stress concentration
OUTER_FILLET = INNER_FILLET + THICKNESS  # outer corner: with this radius the corner wall is the same thickness all round
SCREW = "M4"            # fastener for both holes
ENTRY_CHAMFER = 0.6     # chamfer at the holes' entry (countersink)

NAME = "example-bracket"
EXPECTED_BODIES = 1
SECTION = ("y", 0.0)    # a section through both holes


def _hole_center(leg: float) -> float:
    """The middle of a leg's straight part: between the end of the rounding and the edge."""
    start = THICKNESS + INNER_FILLET
    return start + (leg - start) / 2


def _validate(p) -> None:
    hole_d = f.metric(SCREW).clear_fine + p.hole_clearance_mm
    if THICKNESS < p.min_wall_mm:
        raise ValueError(f"THICKNESS {THICKNESS} is below the minimum wall {p.min_wall_mm} for the {p.nozzle_mm} nozzle")
    for name, leg in (("LEG_X", LEG_X), ("LEG_Z", LEG_Z)):
        straight = leg - THICKNESS - INNER_FILLET
        if straight < hole_d + 2 * p.min_wall_mm:
            raise ValueError(f"{name} {leg}: the straight part {straight:.1f} mm is too short for a {hole_d:.1f} mm hole")
    if WIDTH < hole_d + 2 * p.min_wall_mm:
        raise ValueError(f"WIDTH {WIDTH} is too narrow for a {hole_d:.1f} mm hole")


def build(p):
    _validate(p)
    shelf = Pos(LEG_X / 2, 0, THICKNESS / 2) * Box(LEG_X, WIDTH, THICKNESS)
    post = Pos(THICKNESS / 2, 0, LEG_Z / 2) * Box(THICKNESS, WIDTH, LEG_Z)
    body = shelf + post

    along_y = body.edges().filter_by(Axis.Y)
    inner = along_y.filter_by(lambda e: abs(e.center().X - THICKNESS) < 1e-6 and abs(e.center().Z - THICKNESS) < 1e-6)
    body = fillet(inner, INNER_FILLET)
    outer = body.edges().filter_by(Axis.Y).filter_by(lambda e: abs(e.center().X) < 1e-6 and abs(e.center().Z) < 1e-6)
    body = fillet(outer, OUTER_FILLET)

    hole_d = f.metric(SCREW).clear_fine + p.hole_clearance_mm
    tool = f.clearance_hole(SCREW, THICKNESS, p) + f.chamfer_ring(hole_d, ENTRY_CHAMFER)
    body -= Pos(_hole_center(LEG_X), 0, THICKNESS) * tool                  # shelf: entry from above
    body -= Pos(THICKNESS, 0, _hole_center(LEG_Z)) * Rot(0, 90, 0) * tool  # post: entry from the inside
    return body
