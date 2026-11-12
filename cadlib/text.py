"""Надписи на деталях: один и тот же шрифт на любой ОС.

build123d по умолчанию просит системный Arial. На Linux его нет, и OCCT молча берёт однолинейный
шрифт, из которого выходит незамкнутая сетка. Поэтому шрифт берём из matplotlib: DejaVu Sans Bold
(свободная лицензия, кириллица), он ставится вместе с зависимостями проекта. Жирное начертание
печатается чище: у тонких штрихов обычного на сопле 0.4 стенки в одну линию.
"""

from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path

from build123d import Align, Sketch, Text

FONT_FILE = "DejaVuSans-Bold.ttf"


def font_path() -> Path:
    """Путь к TTF внутри пакета matplotlib (без импорта самого matplotlib)."""
    spec = find_spec("matplotlib")
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError("matplotlib не установлен: uv sync")
    path = Path(spec.submodule_search_locations[0]) / "mpl-data" / "fonts" / "ttf" / FONT_FILE
    if not path.is_file():
        raise RuntimeError(f"нет шрифта {path}")
    return path


def label(txt: str, size_mm: float, align: tuple[Align, Align] = (Align.CENTER, Align.CENTER)) -> Sketch:
    """Плоская надпись высотой size_mm; дальше extrude на нужную высоту рельефа или вычитание."""
    return Text(txt, font_size=size_mm, font_path=str(font_path()), align=align)
