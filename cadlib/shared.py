"""Общий код нескольких деталей: модуль .py из соседней папки (например, parts/lamp-hanger/hanger.py).

Папки деталей названы через дефис, обычным import их не взять. load_module грузит файл по пути
один раз за процесс: обе детали, которые его подключают, получают один и тот же модуль.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_module(path: str | Path) -> ModuleType:
    """Модуль из файла по пути, например load_module(Path(__file__).parent.parent / "lamp-hanger" / "hanger.py")."""
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f"общий модуль не найден: {path}")
    key = f"cadshared_{path.stem}_{hashlib.sha1(str(path).encode()).hexdigest()[:8]}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[key]
        raise
    return module
