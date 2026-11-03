"""{{name}}: ремикс {{file}}.

Сборка: uv run cad.py build remix/{{name}}
Оригинал в source/ только для чтения; всё пишется в out/.
"""

from pathlib import Path

from build123d import Box, Cylinder, Pos, Rot  # noqa: F401  инструменты для вычитания/добавления

from cadlib import fasteners as f  # noqa: F401
from cadlib import mesh as m

HERE = Path(__file__).resolve().parent
SOURCE = "source/{{file}}"

# --- план правок (после `cad.py inspect`, 2–4 пункта) ---
# 1.
# 2.

# --- параметры, мм ---

NAME = "{{name}}"
FORMATS = ("stl", "3mf")        # из сетки STEP не получить
EXPECTED_BODIES = 1
EXPECTED_VOLUME_DELTA = None    # мм³, если изменение можно посчитать заранее (проверка ±1%)
SECTION = None                  # "x" / "y" / "z" или ("y", 12.5)


def build(p):
    src = m.load_source(HERE / SOURCE)
    for note in src.notes:
        print(f"  починка оригинала: {note}")
    body = src.mesh
    # Примеры:
    # body = m.subtract(body, Pos(x, y, z_top) * f.clearance_hole("M3", 10, p))
    # body = m.add(body, Pos(x, y, z) * Box(10, 10, 2))
    # body = m.scale(body, (1, 1, 1.2))
    # body = m.cut(body, normal=(0, 0, -1), origin=(0, 0, 30))   # оставить всё ниже Z=30
    return body
