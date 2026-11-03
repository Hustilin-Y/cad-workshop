"""example-stub: ремикс stub-block.stl — сквозное отверстие и паз в готовом STL.

Пример пути «чужой STL → правка булевыми операциями → сравнение с оригиналом».
Сборка: uv run cad.py build remix/example-stub
"""

import math
from pathlib import Path

from build123d import Cylinder, Pos, SlotCenterToCenter, extrude

from cadlib import mesh as m

HERE = Path(__file__).resolve().parent
SOURCE = "source/stub-block.stl"

# --- план правок (после `cad.py inspect`: блок 60 × 40 × 20, X −30…30, Y −20…20, Z 0…20) ---
# 1. Сквозное вертикальное отверстие Ø8 в левой половине.
# 2. Сквозной вертикальный паз 6 × 20 вдоль X в правой половине.
# 3. Габариты не меняются, объём уменьшается ровно на объём отверстия и паза.

# --- параметры, мм ---
BLOCK_H = 20.0          # высота оригинала (из inspect)
HOLE_D = 8.0            # диаметр отверстия
HOLE_X = -15.0          # центр отверстия по X
SLOT_W = 6.0            # ширина паза
SLOT_LEN = 20.0         # полная длина паза по X
SLOT_X = 12.0           # центр паза по X
OVERSHOOT = 1.0         # инструмент выходит за модель сверху и снизу, чтобы не осталось плёнки

NAME = "example-stub"
FORMATS = ("stl", "3mf")
EXPECTED_BODIES = 1
# Отверстие + паз (стадион: прямоугольник между центрами + круг), на всю высоту блока.
EXPECTED_VOLUME_DELTA = -BLOCK_H * (math.pi * HOLE_D**2 / 4 + (SLOT_LEN - SLOT_W) * SLOT_W + math.pi * SLOT_W**2 / 4)
SECTION = ("y", 0.0)    # разрез через отверстие и паз


def build(p):
    src = m.load_source(HERE / SOURCE)
    for note in src.notes:
        print(f"  починка оригинала: {note}")

    tool_h = BLOCK_H + 2 * OVERSHOOT
    hole = Pos(HOLE_X, 0, BLOCK_H / 2) * Cylinder(HOLE_D / 2, tool_h)
    slot = Pos(SLOT_X, 0, -OVERSHOOT) * extrude(SlotCenterToCenter(SLOT_LEN - SLOT_W, SLOT_W), amount=tool_h)
    return m.subtract(src.mesh, hole, slot)
