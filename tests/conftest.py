"""Общее для тестов: сборки примеров из репозитория идут в копии во временной папке.

Так тесты не пишут в out/ самого проекта, и два прогона одновременно (например, на ПК и
у ассистента на сервере в одном клоне) не мешают друг другу.
"""

import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def repo_copy(tmp_path):
    """repo_copy("calibration") → копия папки проекта без out/ во временной папке."""

    def copy(rel: str) -> Path:
        dst = tmp_path / rel
        shutil.copytree(ROOT / rel, dst, ignore=shutil.ignore_patterns("out", "__pycache__"))
        return dst

    return copy
