"""{{name}}: <что это и куда ставится>.

Сборка: uv run cad.py build parts/{{name}}
"""

from build123d import Box, Pos

from cadlib import fasteners as f  # noqa: F401  отверстия под винты, гайки, вставки

# --- параметры, мм ---
WIDTH = 40.0        # X
DEPTH = 20.0        # Y
HEIGHT = 10.0       # Z

NAME = "{{name}}"
EXPECTED_BODIES = 1
SECTION = None      # "x" / "y" / "z" или ("y", 12.5) — разрез в превью


def build(p):
    """p — профиль принтера: p.hole_clearance_mm, p.slide_fit_mm, p.press_fit_mm, p.min_wall_mm, p.layer_mm."""
    body = Pos(0, 0, HEIGHT / 2) * Box(WIDTH, DEPTH, HEIGHT)
    return body
