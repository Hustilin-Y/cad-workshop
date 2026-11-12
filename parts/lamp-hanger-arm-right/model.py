"""lamp-hanger-arm-right: правое плечо подвеса (с пазом под штекер Ø14), деталь 2 из 3.

Геометрия и параметры — в parts/lamp-hanger/hanger.py.
Печать: лёжа на задней плоскости (Y = −18), все части плеча стоят на ней.

Сборка: uv run cad.py build parts/lamp-hanger-arm-right
"""

from pathlib import Path

from cadlib.shared import load_module

hanger = load_module(Path(__file__).resolve().parent.parent / "lamp-hanger" / "hanger.py")

NAME = "lamp-hanger-arm-right"
EXPECTED_BODIES = 1
SECTION = ("y", 0.0)    # разрез по центру колыбельки: виден паз под штекер
PRINT_DOWN = "-y"       # печать лёжа на задней плоскости


def build(p):
    return hanger.arm(p, "right")
