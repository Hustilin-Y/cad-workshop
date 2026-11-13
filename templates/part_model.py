"""{{name}}: <what it is and where it goes>.

Build: uv run cad.py build parts/{{name}}
"""

from build123d import Box, Pos

from cadlib import fasteners as f  # noqa: F401  holes for screws, nuts, inserts

# --- parameters, mm ---
WIDTH = 40.0        # X
DEPTH = 20.0        # Y
HEIGHT = 10.0       # Z

NAME = "{{name}}"
EXPECTED_BODIES = 1
SECTION = None      # "x" / "y" / "z" or ("y", 12.5): a section in the preview
PRINT_DOWN = None   # the side on the bed when printed, if not the model's bottom: "-y", "+z"… (support and overhang checks)


def _validate(p) -> None:
    """Printability before building: a clear ValueError instead of strange geometry."""
    for name, size in (("WIDTH", WIDTH), ("DEPTH", DEPTH), ("HEIGHT", HEIGHT)):
        if size < p.min_wall_mm:
            raise ValueError(f"{name} = {size} mm is thinner than the minimum wall {p.min_wall_mm} mm")
    # next: the wall around each hole ≥ p.min_wall_mm, the screw is long enough, and so on


def build(p):
    """p — the printer profile: p.hole_clearance_mm, p.slide_fit_mm, p.press_fit_mm, p.min_wall_mm, p.layer_mm."""
    _validate(p)
    body = Pos(0, 0, HEIGHT / 2) * Box(WIDTH, DEPTH, HEIGHT)
    return body
