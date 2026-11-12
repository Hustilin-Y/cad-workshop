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
PRINT_DOWN = None   # сторона на стол при печати, если не низ модели: "-y", "+z"… (проверки опоры и нависаний)


def _validate(p) -> None:
    """Печатаемость до построения: понятная ValueError вместо странной геометрии."""
    for name, size in (("WIDTH", WIDTH), ("DEPTH", DEPTH), ("HEIGHT", HEIGHT)):
        if size < p.min_wall_mm:
            raise ValueError(f"{name} = {size} мм тоньше минимальной стенки {p.min_wall_mm} мм")
    # дальше: стенка вокруг каждого отверстия ≥ p.min_wall_mm, винту хватает длины и т. п.


def build(p):
    """p — профиль принтера: p.hole_clearance_mm, p.slide_fit_mm, p.press_fit_mm, p.min_wall_mm, p.layer_mm."""
    _validate(p)
    body = Pos(0, 0, HEIGHT / 2) * Box(WIDTH, DEPTH, HEIGHT)
    return body
