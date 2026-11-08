"""rod-cap-thread-test: тестовое кольцо с резьбой заглушки rod-cap.

Печатается за ~20 минут. Накрутить на шпильку: если идёт рукой без люфта — печатать
заглушку целиком. Туго — увеличить зазор, болтается — уменьшить (см. README rod-cap).
Все параметры резьбы берутся из parts/rod-cap/model.py, здесь только высота кольца.

Сборка: uv run cad.py build parts/rod-cap-thread-test
"""

import importlib.util
from pathlib import Path

RING_H = 10.0           # высота кольца: 2.5 витка при шаге 4

NAME = "rod-cap-thread-test"
EXPECTED_BODIES = 1
SECTION = ("y", 0.0)

_spec = importlib.util.spec_from_file_location("rod_cap", Path(__file__).resolve().parent.parent / "rod-cap" / "model.py")
cap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cap)


def build(p):
    return cap.threaded_part(p, RING_H)
