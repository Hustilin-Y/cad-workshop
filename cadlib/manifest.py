"""Print manifest (``out/<name>.print.json``, schema 1) for the slicing connector.

CAD Workshop never slices and never talks to the printer: it only writes down what was built
(file hash, checks, weight estimate, the author's print hints) so a separate tool can pick the
file up. The shape is pinned by the consumer's fixtures; its reader is strict on hint values.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Callable, Final

from .checks import Report
from .config import PRINTER_TOML, ROOT, Profile

SCHEMA: Final = 1
INFILL_PATTERNS: Final = (
    "grid", "gyroid", "honeycomb", "cubic", "line",
    "rectilinear", "zig-zag", "adaptivecubic", "lightning",
)
MAX_REASON_CHARS: Final = 200
# Print goals for PRINT_HINTS["goal"]: one key or [primary, secondary]; bambu-mcp defines their settings.
GOAL_KEYS: Final = ("balanced", "speed", "strength", "quality", "cheap", "light", "fit", "watertight")


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _one_of(*allowed: str) -> tuple[Callable[[object], bool], str]:
    return (lambda v: isinstance(v, str) and v in allowed), "one of " + ", ".join(allowed)


def _is_goal(v: object) -> bool:
    if isinstance(v, str):
        return v in GOAL_KEYS
    return (
        isinstance(v, list)
        and 1 <= len(v) <= 2
        and all(isinstance(k, str) and k in GOAL_KEYS for k in v)
        and len(set(v)) == len(v)
    )


# key -> (validator, human description of the allowed values). `material` is checked separately
# against printer.toml (the consumer only requires a non-empty string).
HINT_KEYS: Final[dict[str, tuple[Callable[[object], bool], str]]] = {
    "walls": (lambda v: _is_int(v) and 1 <= v <= 10, "an integer 1..10"),
    "infill_pct": (lambda v: _is_int(v) and 0 <= v <= 100, "an integer 0..100"),
    "infill_pattern": _one_of(*INFILL_PATTERNS),
    "supports": _one_of("none", "auto", "tree", "normal"),
    "brim": _one_of("none", "auto", "outer"),
    "material": (lambda v: isinstance(v, str) and bool(v.strip()), "a key of [materials.*] in printer.toml"),
    "material_reason": (
        lambda v: isinstance(v, str) and len(v) <= MAX_REASON_CHARS,
        f"a string of at most {MAX_REASON_CHARS} characters",
    ),
    "goal": (_is_goal, "one of " + ", ".join(GOAL_KEYS) + ", or a list of two different ones"),
    "goal_reason": (
        lambda v: isinstance(v, str) and len(v) <= MAX_REASON_CHARS,
        f"a string of at most {MAX_REASON_CHARS} characters",
    ),
}


def _material_names(printer_toml: Path) -> list[str]:
    data = tomllib.loads(printer_toml.read_text(encoding="utf-8"))
    return list(data.get("materials", {}))


def validate_hints(hints: object, profile: Profile, printer_toml: Path = PRINTER_TOML) -> dict:
    """Check a part's PRINT_HINTS and return a cleaned copy; ValueError names the bad key and the allowed values.

    `profile` is accepted for symmetry with the other cadlib entry points: the list of plastics
    comes from printer.toml (a Profile only knows the selected one).
    """
    if hints is None:
        return {}
    if not isinstance(hints, dict):
        raise ValueError(f"PRINT_HINTS must be a dict, got {type(hints).__name__}")
    for key, value in hints.items():
        if key not in HINT_KEYS:
            raise ValueError(f"PRINT_HINTS: unknown key {key!r} (allowed: {', '.join(HINT_KEYS)})")
        ok, allowed = HINT_KEYS[key]
        if not ok(value):
            raise ValueError(f"PRINT_HINTS: {key} must be {allowed}, got {value!r}")
        if key == "material":
            names = _material_names(printer_toml)
            if value not in names:
                raise ValueError(
                    f"PRINT_HINTS: material {value!r} isn't described in printer.toml, there are: {', '.join(names)}"
                )
    return dict(hints)


_ISLANDS_RE = re.compile(r"in the air: (\d+)")
_BODIES_RE = re.compile(r"^(\d+) of the bodies")


def _count(report: Report, name: str, pattern: re.Pattern[str]) -> int:
    for c in report.checks:
        if c.name == name and c.level == "warn":
            m = pattern.search(c.message)
            if not m:
                raise ValueError(f"cannot read the count from check {name!r}: {c.message!r}")
            return int(m.group(1))
    return 0


def _warns(report: Report, name: str) -> bool:
    return any(c.name == name and c.level == "warn" for c in report.checks)


def checks_summary(report: Report) -> dict:
    """The few check results the slicing connector needs (a missing check counts as 0 / False)."""
    islands = _count(report, "5. Islands", _ISLANDS_RE)
    bodies = _count(report, "5. Bodies above the bed", _BODIES_RE)
    overhang = _warns(report, "6. Overhangs")
    return {
        "failed": report.failed,
        "islands": islands,
        "bodies_above_bed": bodies,
        "overhang_warn": overhang,
        "base_warn": _warns(report, "5. Base"),
        "supports_suggested": islands > 0 or bodies > 0 or overhang,
    }


_CHECK_INTS: Final = ("islands", "bodies_above_bed")
_CHECK_BOOLS: Final = ("failed", "overhang_warn", "base_warn")


def merge_checks(summaries: list[dict], how: str) -> dict:
    """Combine checks_summary() dicts: flags are OR-ed, counts take the worst ("max") or add up ("sum")."""
    if how not in ("max", "sum"):
        raise ValueError(f"how must be 'max' or 'sum', got {how!r}")
    pick = max if how == "max" else sum
    merged: dict = {k: any(s[k] for s in summaries) for k in _CHECK_BOOLS}
    merged.update({k: pick([s[k] for s in summaries] or [0]) for k in _CHECK_INTS})
    merged["supports_suggested"] = any(s["supports_suggested"] for s in summaries)
    return merged


def plate_hints(hints: list[dict]) -> tuple[dict, list[str]]:
    """Hints of the parts on one plate: the common hints when all parts agree, else ({}, sorted conflicting keys).

    A key one part sets and another leaves out is a conflict too: the plate would print one of them
    with settings it never asked for."""
    keys = sorted({k for h in hints for k in h})
    conflicts = [
        k for k in keys
        if len({json.dumps(h[k], sort_keys=True) if k in h else None for h in hints}) > 1
    ]
    if conflicts:
        return {}, conflicts
    return (dict(hints[0]) if hints else {}), []


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = out.stdout.strip()
    return commit if out.returncode == 0 and commit else None


def build_manifest(
    *,
    kind: str,
    name: str,
    file: Path,
    print_ready: bool,
    model_path: Path,
    overrides: dict[str, str],
    profile: Profile,
    plates: list[dict],
    checks: dict,
    estimate_g: float,
    hints: dict,
    original_sha256: str | None,
) -> dict:
    model_sha = _sha256(model_path)
    commit = _git_commit()
    return {
        "schema": SCHEMA,
        "kind": kind,
        "name": name,
        "file": Path(file).name,
        "file_sha256": _sha256(file),
        "model_sha256": model_sha,
        "git_commit": commit,
        "print_ready": print_ready,
        "profile": {
            "material": profile.material,
            "nozzle_mm": profile.nozzle_mm,
            "tolerances": {
                "hole_mm": profile.hole_clearance_mm,
                "press_mm": profile.press_fit_mm,
                "slide_mm": profile.slide_fit_mm,
                "thread_mm": profile.thread_clearance_mm,
            },
        },
        "estimate": {"grams": estimate_g},
        "checks": checks,
        "hints": hints,
        "plates": plates,
        "source": {
            "git_commit": commit,
            "model_sha256": model_sha,
            "original_sha256": original_sha256,
            "overrides": dict(overrides),
        },
    }


def write_manifest(manifest: dict, path: Path) -> None:
    """UTF-8, LF, indent 1, keys sorted, trailing newline."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def remove_stale(path: Path) -> None:
    """A stale manifest must never describe a file that is not print-ready."""
    Path(path).unlink(missing_ok=True)
