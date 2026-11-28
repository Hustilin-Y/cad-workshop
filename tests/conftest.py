"""Shared test setup: builds of the repo's examples run on copies in a temporary folder.

So the tests never write into the project's own out/, and two runs at once (say on the PC and
by the assistant on the server in one clone) don't get in each other's way.
"""

import os
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


@pytest.fixture
def within_budget():
    """within_budget(elapsed_s, budget_s): assert a wall-clock budget tuned on the PC.

    The budget is multiplied by CAD_PERF_FACTOR (default 1.0) for slower machines, and the assert
    is skipped altogether with CAD_SKIP_PERF=1; the rest of the test still runs.
    """
    skip = os.environ.get("CAD_SKIP_PERF") == "1"
    factor = float(os.environ.get("CAD_PERF_FACTOR", "1.0"))

    def check(elapsed: float, budget: float) -> None:
        if not skip:
            assert elapsed < budget * factor, f"took {elapsed:.1f} s, budget {budget * factor:.1f} s (CAD_PERF_FACTOR={factor:g})"

    return check
