"""Shared test setup: builds of the repo's examples run on copies in a temporary folder.

So the tests never write into the project's own out/, and two runs at once (say on the PC and
by the assistant on the server in one clone) don't get in each other's way.
"""

import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def repo_copy(tmp_path):
    """repo_copy("calibration") → a copy of that project folder, without out/, in a temporary folder."""

    def copy(rel: str) -> Path:
        dst = tmp_path / rel
        shutil.copytree(ROOT / rel, dst, ignore=shutil.ignore_patterns("out", "__pycache__"))
        return dst

    return copy
