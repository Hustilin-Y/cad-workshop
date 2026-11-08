"""lamp-hanger: потолочная планка подвеса лампы (деталь 1 из 3).

Вся геометрия и параметры — в hanger.py рядом; плечи — в lamp-hanger-arm-right/-left.
Печать: потолочной стороной на стол, потаи саморезов смотрят вверх.

Сборка: uv run cad.py build parts/lamp-hanger
"""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("hanger", Path(__file__).resolve().parent / "hanger.py")
hanger = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hanger)

NAME = "lamp-hanger-mount"
EXPECTED_BODIES = 1
SECTION = ("y", 0.0)    # разрез через саморезы и гнёзда


def build(p):
    return hanger.mount(p)
