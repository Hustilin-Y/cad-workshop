"""plant-lamp-bracket: Г-кронштейн для подвеса лёгкой лампы для растений на карабин.

Полка (210 мм) лежит на подоконнике и уходит вглубь, у её дальнего конца один потайной
саморез 6 мм вниз в подоконник. Стойка (150 мм) поднимается вверх от ближнего края,
наверху горизонтальное отверстие под карабин. Две косынки в углу по краям ширины
передают нагрузку со стойки на полку.

Система координат: низ полки на Z = 0 (лежит на подоконнике), стойка у X = 0,
полка уходит в +X (вглубь подоконника), ширина по Y.

Сборка: uv run cad.py build parts/plant-lamp-bracket
"""

from build123d import Axis, Box, Cylinder, Plane, Polygon, Pos, Rot, extrude, fillet

from cadlib import fasteners as f

# --- размеры от пользователя, мм ---
BASE_LEN = 210.0        # полка с креплением: длина вглубь подоконника
POST_LEN = 150.0        # стойка с карабином: высота
WIDTH = 50.0            # ширина кронштейна
SCREW_D = 6.0           # один саморез 6 мм, потай, у дальнего конца полки
CARABINER_D = 12.0      # отверстие под карабин
LAMP_MASS_G = 350       # нагрузка: лёгкая лампа (для справки, на геометрию не влияет)

# --- выбранные по умолчанию (уточнить), мм ---
THICKNESS = 5.0         # толщина полки и стойки: нагрузка 350 г, сверхжёсткость не нужна
SCREW_HEAD_D = None     # диаметр потайной головки; None = 12 по DIN 7997, лучше замерить
SCREW_FROM_END = 15.0   # от дальнего конца полки до центра самореза
SCREW_FROM_OUTSIDE = True  # потай на внешней стороне полки (Z = 0, без стойки); False — на внутренней
CARABINER_FROM_END = 15.0  # от верха стойки до центра отверстия под карабин
RIB_ALONG_BASE = 20.0   # косынки: катет по полке (было 60, уменьшено втрое по просьбе)
RIB_ALONG_POST = 33.0   # косынки: катет по стойке, вытянуты вверх (было 100, уменьшено втрое)
RIB_T = 4.0             # толщина каждой косынки
INNER_FILLET = 8.0      # скругление внутреннего угла
OUTER_FILLET = INNER_FILLET + THICKNESS  # наружный угол: стенка в углу везде одной толщины
CORNER_R = 6.0          # скругление углов на концах полки и стойки (косметика)
EDGE_CHAMFER = 0.8      # фаска на кромках отверстия под карабин

NAME = "plant-lamp-bracket"
EXPECTED_BODIES = 1
SECTION = ("y", 0.0)    # разрез по центру: саморез и отверстие под карабин


def _validate(p) -> None:
    if THICKNESS < p.min_wall_mm or RIB_T < p.min_wall_mm:
        raise ValueError(f"THICKNESS/RIB_T меньше минимальной стенки {p.min_wall_mm} для сопла {p.nozzle_mm}")
    head_d = SCREW_HEAD_D or f.WOOD_SCREW_HEAD[SCREW_D]
    if (head_d - SCREW_D) / 2 > THICKNESS - 1.0:
        raise ValueError(f"потай головки Ø{head_d} не помещается в THICKNESS {THICKNESS}: под головкой останется < 1 мм")
    if SCREW_FROM_END - head_d / 2 < 2 * p.min_wall_mm:
        raise ValueError(f"от головки самореза до конца полки {SCREW_FROM_END - head_d / 2:.1f} мм — мало")
    if BASE_LEN - SCREW_FROM_END - head_d / 2 < THICKNESS + RIB_ALONG_BASE:
        raise ValueError("саморез заходит на косынки: уменьшите RIB_ALONG_BASE")
    if CARABINER_FROM_END - CARABINER_D / 2 < 2 * p.min_wall_mm:
        raise ValueError(f"от отверстия под карабин до верха {CARABINER_FROM_END - CARABINER_D / 2:.1f} мм — слишком тонко")
    if POST_LEN - CARABINER_FROM_END - CARABINER_D / 2 < THICKNESS + RIB_ALONG_POST:
        raise ValueError("отверстие под карабин заходит на косынки: уменьшите RIB_ALONG_POST")
    if WIDTH - 2 * RIB_T < CARABINER_D + 2 * p.min_wall_mm:
        raise ValueError("ширина мала для отверстия под карабин")


def _rib(y0: float):
    """Треугольная косынка во внутреннем углу, толщина RIB_T от y0 по +Y."""
    pts = [(THICKNESS, THICKNESS), (THICKNESS + RIB_ALONG_BASE, THICKNESS), (THICKNESS, THICKNESS + RIB_ALONG_POST)]
    rib = extrude(Plane.XZ * Polygon(*pts, align=None), amount=RIB_T)
    bb = rib.bounding_box()
    assert abs(bb.min.Z - THICKNESS) < 1e-6 and abs(bb.min.X - THICKNESS) < 1e-6, "Plane.XZ повёрнута не так, как ожидалось"
    return Pos(0, y0 - bb.min.Y, 0) * rib


def build(p):
    _validate(p)
    base = Pos(BASE_LEN / 2, 0, THICKNESS / 2) * Box(BASE_LEN, WIDTH, THICKNESS)
    post = Pos(THICKNESS / 2, 0, POST_LEN / 2) * Box(THICKNESS, WIDTH, POST_LEN)
    body = base + post

    def y_edge_at(x, z):
        return body.edges().filter_by(Axis.Y).filter_by(lambda e: abs(e.center().X - x) < 1e-6 and abs(e.center().Z - z) < 1e-6)

    body = fillet(y_edge_at(THICKNESS, THICKNESS), INNER_FILLET)
    body = fillet(y_edge_at(0, 0), OUTER_FILLET)
    # Углы на конце полки (рёбра вдоль Z) и наверху стойки (рёбра вдоль X).
    body = fillet(body.edges().filter_by(Axis.Z).filter_by(lambda e: abs(e.center().X - BASE_LEN) < 1e-6), CORNER_R)
    body = fillet(body.edges().filter_by(Axis.X).filter_by(lambda e: abs(e.center().Z - POST_LEN) < 1e-6), CORNER_R)

    body += [_rib(-WIDTH / 2), _rib(WIDTH / 2 - RIB_T)]

    # Саморез: потай на внешней стороне полки (вход снизу, Rot(180) разворачивает инструмент в +Z)
    # или на внутренней (вход сверху).
    screw = f.wood_screw_countersunk_hole(SCREW_D, THICKNESS, p, SCREW_HEAD_D)
    x = BASE_LEN - SCREW_FROM_END
    if SCREW_FROM_OUTSIDE:
        body -= Pos(x, 0, 0) * Rot(180, 0, 0) * screw
    else:
        body -= Pos(x, 0, THICKNESS) * screw

    # Карабин: горизонтальное отверстие сквозь стойку (ось X), фаски с обеих сторон.
    z = POST_LEN - CARABINER_FROM_END
    body -= Pos(THICKNESS / 2, 0, z) * Rot(0, 90, 0) * Cylinder(CARABINER_D / 2, THICKNESS + 1)
    body -= Pos(THICKNESS, 0, z) * Rot(0, 90, 0) * f.chamfer_ring(CARABINER_D, EDGE_CHAMFER)
    body -= Pos(0, 0, z) * Rot(0, -90, 0) * f.chamfer_ring(CARABINER_D, EDGE_CHAMFER)
    return body
