"""logo-plaque: табличка с лого мастерской — барельеф сибы на квадратной плитке.

Квадрат со скруглёнными углами и скосом верхней кромки, на нём лого в стиле «барельеф»
(cadlib.logo). Сетка собирается в manifold3d.

Сборка: uv run cad.py build parts/logo-plaque
"""

import manifold3d as mf

from cadlib.logo import logo_relief
from cadlib.mesh import from_manifold

# --- табличка, мм ---
SIZE = 64.0             # сторона квадрата
THICK = 4.0             # толщина
CORNER_R = 7.0          # скругление углов в плане
EDGE_BEVEL = 0.8        # скос верхней кромки (низ — на столе, без скоса)
SEGMENTS = 64

# --- лого, мм ---
LOGO_H = 52.0           # высота: от кончиков ушей до низа бабочки
BASE = 1.2              # основа лого над табличкой
STEP = 0.6              # шаг уровней барельефа
EMBED = 0.1             # лого утоплено в табличку: слияние по объёму

NAME = "logo-plaque"
FORMATS = ("stl", "3mf")
EXPECTED_BODIES = 1
SECTION = ("x", 0.0)


def _rounded_square(size: float, r: float, h: float, top_inset: float = 0.0) -> mf.Manifold:
    """Квадрат со скруглёнными углами в плане; top_inset > 0 — скос верхней кромки."""
    half = size / 2 - r
    corners = [mf.Manifold.cylinder(h, r, r - top_inset, SEGMENTS).translate((sx * half, sy * half, 0))
               for sx in (-1, 1) for sy in (-1, 1)]
    return mf.Manifold.batch_hull(corners)


def build(p):
    plate = _rounded_square(SIZE, CORNER_R, THICK - EDGE_BEVEL)
    plate += _rounded_square(SIZE, CORNER_R, EDGE_BEVEL, top_inset=EDGE_BEVEL).translate((0, 0, THICK - EDGE_BEVEL))
    logo = logo_relief(LOGO_H, BASE + EMBED, STEP).translate((0, 0, THICK - EMBED))
    body = plate + logo
    if len(body.decompose()) != 1:
        raise RuntimeError("табличка и лого не срослись")
    return from_manifold(body)
