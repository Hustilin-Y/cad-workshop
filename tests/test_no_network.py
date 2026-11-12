"""В коде проекта нет сетевых вызовов и обращений к принтеру (критерий приёмки ТЗ)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ("cadlib", "parts", "remix", "calibration", "templates", "tools", "tests")
FORBIDDEN = re.compile(
    r"^\s*(import|from)\s+(socket|requests|urllib|http|httpx|aiohttp|ftplib|paho|websockets|bambulabs?)\b",
    re.MULTILINE,
)


def _sources():
    files = [ROOT / "cad.py"] if (ROOT / "cad.py").exists() else []
    for d in SCAN_DIRS:
        files += (ROOT / d).rglob("*.py")
    return [f for f in files if "source" not in f.parts]


def test_no_network_imports():
    offenders = [str(f.relative_to(ROOT)) for f in _sources() if FORBIDDEN.search(f.read_text(encoding="utf-8"))]
    assert not offenders, f"сетевые импорты в: {offenders}"
