"""example-bracket: Г-образный кронштейн с двумя отверстиями под M4 и скруглением внутреннего угла.

Полка лежит вдоль +X, стойка поднимается по +Z, ширина по Y. Винт полки входит сверху,
винт стойки — с внутренней стороны (со стороны полки).

Сборка: uv run cad.py build parts/example-bracket
"""

from build123d import Axis, Box, Pos, Rot, fillet

from cadlib import fasteners as f

# --- параметры, мм ---
LEG_X = 40.0            # длина полки по X (от наружной стороны стойки)
LEG_Z = 40.0            # высота стойки по Z (от низа полки)
WIDTH = 25.0            # ширина кронштейна по Y
THICKNESS = 5.0         # толщина полки и стойки
INNER_FILLET = 6.0      # радиус скругления внутреннего угла: снимает концентрацию напряжений
OUTER_FILLET = INNER_FILLET + THICKNESS  # наружный угол: с этим радиусом стенка в углу везде одной толщины
SCREW = "M4"            # крепёж обоих отверстий
ENTRY_CHAMFER = 0.6     # фаска на входе отверстий (зенковка)

NAME = "example-bracket"
EXPECTED_BODIES = 1
SECTION = ("y", 0.0)    # разрез через оба отверстия


def _hole_center(leg: float) -> float:
    """Середина прямого участка ножки: между концом скругления и краем."""
    start = THICKNESS + INNER_FILLET
    return start + (leg - start) / 2


def _validate(p) -> None:
    hole_d = f.metric(SCREW).clear_fine + p.hole_clearance_mm
    if THICKNESS < p.min_wall_mm:
        raise ValueError(f"THICKNESS {THICKNESS} меньше минимальной стенки {p.min_wall_mm} для сопла {p.nozzle_mm}")
    for name, leg in (("LEG_X", LEG_X), ("LEG_Z", LEG_Z)):
        straight = leg - THICKNESS - INNER_FILLET
        if straight < hole_d + 2 * p.min_wall_mm:
            raise ValueError(f"{name} {leg}: прямой участок {straight:.1f} мм мал для отверстия {hole_d:.1f} мм")
    if WIDTH < hole_d + 2 * p.min_wall_mm:
        raise ValueError(f"WIDTH {WIDTH} мала для отверстия {hole_d:.1f} мм")


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
    body -= Pos(_hole_center(LEG_X), 0, THICKNESS) * tool                  # полка: вход сверху
    body -= Pos(THICKNESS, 0, _hole_center(LEG_Z)) * Rot(0, 90, 0) * tool  # стойка: вход с внутренней стороны
    return body
