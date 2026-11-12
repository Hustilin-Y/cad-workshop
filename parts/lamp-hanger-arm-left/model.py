"""lamp-hanger-arm-left: левое плечо подвеса (колыбелька под плоский торец), деталь 3 из 3.

Геометрия и параметры — в parts/lamp-hanger/hanger.py.
Печать: лёжа на задней плоскости (Y = −18), все части плеча стоят на ней.

Сборка: uv run cad.py build parts/lamp-hanger-arm-left
"""

from pathlib import Path

from cadlib.shared import load_module

hanger = load_module(Path(__file__).resolve().parent.parent / "lamp-hanger" / "hanger.py")

NAME = "lamp-hanger-arm-left"
EXPECTED_BODIES = 1
SECTION = ("y", 0.0)
PRINT_DOWN = "-y"       # печать лёжа на задней плоскости


def build(p):
    return hanger.arm(p, "left")
