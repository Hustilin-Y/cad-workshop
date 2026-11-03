"""Калибровка допусков: ряд отверстий D+c и штырей D−c, плюс ключ с точным D.

Ключом пробуют каждое отверстие (его штырь) и каждый штырь (его кольцо).
Значение c, при котором посадка нужного типа, переносится в printer.toml.
"""

from build123d import Align, Box, Cylinder, Pos, Text, extrude

# --- параметры, мм ---
NOMINAL_D = 8.0                                     # номинальный диаметр штыря/отверстия ключа
CLEARANCES = [round(i * 0.05, 2) for i in range(11)]  # 0.00 … 0.50 с шагом 0.05, зазор на диаметр
PITCH = 13.0                                        # шаг между отверстиями по X
MARGIN_X = 9.0                                      # от края пластины до центра первого отверстия
PLATE_DEPTH = 36.0                                  # пластина по Y
PLATE_T = 3.0                                       # толщина пластины = глубина отверстий
PIN_ROW_Y = 8.0                                     # ряд штырей
LABEL_ROW_Y = 18.0                                  # ряд подписей
HOLE_ROW_Y = 28.0                                   # ряд отверстий
PIN_H = 8.0                                         # высота штырей над пластиной
LABEL_SIZE = 4.0                                    # высота шрифта подписей
LABEL_RELIEF = 0.6                                  # высота рельефа подписей (3 слоя по 0.2)
KEY_GAP = 8.0                                       # зазор между пластиной и ключом на столе
KEY_RING_WALL = 3.0                                 # стенка кольца ключа
KEY_BAR_W = 10.0                                    # ширина перемычки ключа
KEY_LEN = 50.0                                      # расстояние между центрами кольца и штыря ключа

NAME = "tolerance-gauge"
EXPECTED_BODIES = 2                                 # пластина + ключ
SECTION = ("y", HOLE_ROW_Y)                         # разрез через ряд отверстий в превью


def _label(c: float) -> str:
    return f"{c:.2f}".lstrip("0")                   # ".05", ".50"; ноль как ".00"


def plate():
    length = 2 * MARGIN_X + PITCH * (len(CLEARANCES) - 1)
    xs = [MARGIN_X + i * PITCH for i in range(len(CLEARANCES))]
    body = Pos(length / 2, PLATE_DEPTH / 2, PLATE_T / 2) * Box(length, PLATE_DEPTH, PLATE_T)
    # Булевы операции списком, а не по одной: OCCT делает их за один проход, в разы быстрее.
    body -= [Pos(x, HOLE_ROW_Y, PLATE_T / 2) * Cylinder((NOMINAL_D + c) / 2, PLATE_T) for x, c in zip(xs, CLEARANCES)]
    pins = [Pos(x, PIN_ROW_Y, PLATE_T + PIN_H / 2) * Cylinder((NOMINAL_D - c) / 2, PIN_H) for x, c in zip(xs, CLEARANCES)]
    labels = [
        extrude(Pos(x, LABEL_ROW_Y, PLATE_T) * Text(_label(c), font_size=LABEL_SIZE, align=(Align.CENTER, Align.CENTER)), amount=LABEL_RELIEF)
        for x, c in zip(xs, CLEARANCES)
    ]
    return body + pins + labels


def key():
    """Кольцо с отверстием ровно D и штырь ровно D на одной перемычке."""
    ring_r = NOMINAL_D / 2 + KEY_RING_WALL
    y = -KEY_GAP - ring_r
    x0 = MARGIN_X
    x1 = x0 + KEY_LEN
    body = Pos(x0, y, PLATE_T / 2) * Cylinder(ring_r, PLATE_T)
    body += Pos((x0 + x1) / 2, y, PLATE_T / 2) * Box(KEY_LEN, KEY_BAR_W, PLATE_T)
    body += Pos(x1, y, PLATE_T / 2) * Cylinder(ring_r, PLATE_T)
    body -= Pos(x0, y, PLATE_T / 2) * Cylinder(NOMINAL_D / 2, PLATE_T)
    body += Pos(x1, y, PLATE_T + PIN_H / 2) * Cylinder(NOMINAL_D / 2, PIN_H)
    text = Text(f"D{NOMINAL_D:g}", font_size=LABEL_SIZE, align=(Align.CENTER, Align.CENTER))
    body += extrude(Pos((x0 + x1) / 2, y, PLATE_T) * text, amount=LABEL_RELIEF)
    return body


def build(p):
    # Профиль не влияет на геометрию: образец как раз измеряет допуски, а не использует их.
    return plate() + key()
