"""Code shared by several parts: a .py module from a sibling folder (for example parts/lamp-hanger/hanger.py).

Part folders have hyphens in their names, so a plain import can't reach them. load_module loads the file
by path once per process: both parts that use it get the very same module.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_module(path: str | Path) -> ModuleType:
    """A module from a file path, for example load_module(Path(__file__).parent.parent / "lamp-hanger" / "hanger.py")."""
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f"shared module not found: {path}")
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
