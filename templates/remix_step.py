"""{{name}}: ремикс {{file}} (STEP — правки точные, как у своей детали).

Сборка: uv run cad.py build remix/{{name}}
Оригинал в source/ только для чтения; всё пишется в out/.
"""

from pathlib import Path

from build123d import Box, Cylinder, Pos, Rot, import_step  # noqa: F401

from cadlib import fasteners as f  # noqa: F401

HERE = Path(__file__).resolve().parent
SOURCE = "source/{{file}}"

# --- план правок (после `cad.py inspect`, 2–4 пункта) ---
# 1.
# 2.

# --- параметры, мм ---

NAME = "{{name}}"
EXPECTED_BODIES = 1
EXPECTED_VOLUME_DELTA = None    # мм³, если изменение можно посчитать заранее (проверка ±1%)
SECTION = None


def build(p):
    body = import_step(HERE / SOURCE)
    # Примеры:
    # body -= Pos(x, y, z_top) * f.clearance_hole("M3", 10, p)
    # body += Pos(x, y, z) * Box(10, 10, 2)
    return body
