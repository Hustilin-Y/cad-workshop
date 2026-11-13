"""Lettering on parts: the same font on any OS.

build123d asks for the system Arial by default. Linux has none, and OCCT silently takes a single-line
font that gives an open mesh. So the font comes from matplotlib: DejaVu Sans Bold
(free licence, Cyrillic included), installed with the project's dependencies. The bold weight
prints cleaner: the regular weight's thin strokes are one line wide with a 0.4 nozzle.
"""

from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path

from build123d import Align, Sketch, Text

FONT_FILE = "DejaVuSans-Bold.ttf"


def font_path() -> Path:
    """Path to the TTF inside the matplotlib package (without importing matplotlib itself)."""
    spec = find_spec("matplotlib")
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError("matplotlib is not installed: uv sync")
    path = Path(spec.submodule_search_locations[0]) / "mpl-data" / "fonts" / "ttf" / FONT_FILE
    if not path.is_file():
        raise RuntimeError(f"no font at {path}")
    return path


def label(txt: str, size_mm: float, align: tuple[Align, Align] = (Align.CENTER, Align.CENTER)) -> Sketch:
    """Flat lettering size_mm high; then extrude it to the relief height, or subtract it."""
    return Text(txt, font_size=size_mm, font_path=str(font_path()), align=align)
