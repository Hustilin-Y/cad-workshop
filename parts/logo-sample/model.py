"""logo-sample: пробная пластина с лого — барельеф и контурный стиль, 40 и 20 мм.

Печатается за ~40 минут и показывает, как оба стиля выходят на вашем принтере
и читаются ли глаза, нос и пасть на 20 мм.

Раскладка: [барельеф 40] [контурный 40] [барельеф 20 над контурным 20].

Сборка: uv run cad.py build parts/logo-sample
"""

import manifold3d as mf

from cadlib.logo import aspect, logo_outline, logo_relief
from cadlib.mesh import from_manifold

# --- лого, мм ---
BIG = 40.0              # высота больших
SMALL = 20.0            # высота маленьких
GAP = 6.0               # промежутки и поля
EMBED = 0.1             # лого утоплены в пластину: слияние по объёму

# --- пластина, мм ---
PLATE_T = 1.6
CORNER_R = 4.0

NAME = "logo-sample"
FORMATS = ("stl", "3mf")
EXPECTED_BODIES = 1
SECTION = ("x", 0.0)


def _plate(w: float, h: float) -> mf.Manifold:
    hw, hh = w / 2 - CORNER_R, h / 2 - CORNER_R
    corners = [mf.Manifold.cylinder(PLATE_T, CORNER_R, CORNER_R, 48).translate((sx * hw, sy * hh, 0))
               for sx in (-1, 1) for sy in (-1, 1)]
    return mf.Manifold.batch_hull(corners)


def build(p):
    a = aspect()
    big_w, small_w = BIG * a, SMALL * a
    plate_w = 2 * big_w + small_w + 4 * GAP
    plate_h = BIG + 2 * GAP
    x0 = -plate_w / 2 + GAP
    z = PLATE_T - EMBED

    def place(m: mf.Manifold, x_center: float, y_center: float) -> mf.Manifold:
        return m.translate((x_center, y_center, z))

    parts = [
        _plate(plate_w, plate_h),
        place(logo_relief(BIG), x0 + big_w / 2, 0),
        place(logo_outline(BIG), x0 + big_w + GAP + big_w / 2, 0),
        place(logo_relief(SMALL), x0 + 2 * (big_w + GAP) + small_w / 2, BIG / 4 + 0.5),
        place(logo_outline(SMALL), x0 + 2 * (big_w + GAP) + small_w / 2, -BIG / 4 - 0.5),
    ]
    body = mf.Manifold.batch_boolean(parts, mf.OpType.Add)
    if len(body.decompose()) != 1:
        raise RuntimeError("лого не срослись с пластиной")
    return from_manifold(body)
