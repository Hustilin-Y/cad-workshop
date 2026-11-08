"""lamp-hanger-arm-right: правое плечо подвеса (с пазом под штекер Ø14), деталь 2 из 3.

Геометрия и параметры — в parts/lamp-hanger/hanger.py.
Печать: лёжа на задней плоскости (Y = −18), все части плеча стоят на ней.

Сборка: uv run cad.py build parts/lamp-hanger-arm-right
"""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("hanger", Path(__file__).resolve().parent.parent / "lamp-hanger" / "hanger.py")
hanger = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hanger)

NAME = "lamp-hanger-arm-right"
EXPECTED_BODIES = 1
SECTION = ("y", 0.0)    # разрез по центру колыбельки: виден паз под штекер


def build(p):
    return hanger.arm(p, "right")
