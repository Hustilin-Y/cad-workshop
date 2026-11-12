"""lamp-hanger-arm-left: левое плечо подвеса (колыбелька под плоский торец), деталь 3 из 3.

Геометрия и параметры — в parts/lamp-hanger/hanger.py.
Печать: лёжа на задней плоскости (Y = −18), все части плеча стоят на ней.

Сборка: uv run cad.py build parts/lamp-hanger-arm-left
"""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("hanger", Path(__file__).resolve().parent.parent / "lamp-hanger" / "hanger.py")
hanger = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hanger)

NAME = "lamp-hanger-arm-left"
EXPECTED_BODIES = 1
SECTION = ("y", 0.0)
PRINT_DOWN = "-y"       # печать лёжа на задней плоскости


def build(p):
    return hanger.arm(p, "left")
