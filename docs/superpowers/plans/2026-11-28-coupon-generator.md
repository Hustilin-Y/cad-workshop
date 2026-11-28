# Coupon generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `uv run cad.py coupon <feature>` builds a labelled step series for any fit.

**Architecture:** `cadlib/coupon.py` holds a registry of features. Each one turns a list of values
and its options into one or more bodies plus metadata (name, body count, the `printer.toml` key, how
to read it). `cad.py coupon` wraps that in an in-memory model module and runs the existing `_build`.

**Tech Stack:** Python 3.12, build123d, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-28-coupon-generator-design.md`

## Global Constraints

- Tolerances in use come from `Profile`; the coupon itself steps raw values on the diameter and
  states which key its result goes to. No network. Everything in English. No commits until the
  owner says so. Do not touch `cadlib/style/`.
- New `printer.toml` key `magnet_fit_mm = 0.1` (starting guess) in `[tolerances]`, `Profile.magnet_fit_mm`
  added after the existing fields, plus the plastic's `clearance_add_mm`.

## Review Focus

- A range where `--to` < `--from` or `--step` ≤ 0: `ValueError` naming the options. (Task 1)
- Float steps: 0.15 to 0.5 by 0.05 gives exactly 8 values, rounded to 3 decimals. (Task 1)
- `magnet` without `--d`/`--h`: an error that asks for a caliper measurement. (Task 2)
- More samples than the bed holds even after wrapping: `ValueError` with the maximum. (Task 1)
- Unknown thread size: the error lists the known sizes. (Task 3)

---

### Task 1: registry, values, layout, `hole`

**Files:** create `cadlib/coupon.py`, `tests/test_coupon.py`.

**Interfaces (produces):**
- `values(start: float, stop: float, step: float) -> list[float]`
- `@dataclass Coupon: name: str, body: Part, bodies: int, key: str, how_to: str`
- `FEATURES: dict[str, Feature]`, `Feature` with `defaults: tuple[float, float, float]`, `key`
- `make(feature: str, p: Profile, *, start=None, stop=None, step=None, **opts) -> Coupon`
- `label_text(c: float) -> str` (".05", ".50", ".00")

- [ ] Tests: `values` cases above; `make("hole", P)` has 6 holes of Ø 8.0 to 8.5 (section at mid
  plate), 1 body, key `hole_clearance_mm`; 30 samples wrap into several rows inside
  `P.usable_volume_mm`; 200 samples raise; unknown feature lists the known ones.
- [ ] Run: fail. Implement. Run: pass.

### Task 2: `press`, `slide`, `magnet`, profile key

**Files:** modify `cadlib/coupon.py`, `cadlib/config.py`, `printer.toml`, `tests/test_coupon.py`.

- [ ] Tests: `press` has holes 8 + c and pins 8 − c for c in 0.0 to 0.25 and 2 bodies (plate + key),
  the key's hole and pin are exactly 8; `slide` defaults to 0.15 to 0.5. `magnet` with `d=6, h=2`:
  pockets 6 + c, depth a multiple of `P.layer_mm` ≥ 2, floor ≥ `P.min_wall_mm`, a push-out hole;
  without `d` raises with "caliper". `load_profile().magnet_fit_mm == 0.1` for PLA, 0.15 for PETG.
- [ ] Run: fail. Implement. Run: pass.

### Task 3: `thread`

**Files:** modify `cadlib/coupon.py`, `cadlib/threads.py` (`ISO_COARSE_PITCH`, ISO 261), tests.

- [ ] Tests: `make("thread", P)` gives 7 bodies (0.2 to 0.5), the name `coupon-thread-M8`; a ring's
  inner minimum Ø equals `minor_diameter(8 + c, 1.25)` within 0.05; `size="M7"` raises listing sizes.
- [ ] Run: fail. Implement. Run: pass.

### Task 4: CLI and docs

**Files:** modify `cad.py` (`coupon` subcommand), create `calibration/coupons/README.md`, modify
`calibration/README.md`, `README.md` (Commands), `.claude/skills/cad/SKILL.md`, `CLAUDE.md` (fits
come from a coupon), `tests/test_coupon.py`.

- [ ] Tests: `main(["coupon", f, ...])` with `cad.ROOT` patched to a temp copy builds every feature
  with exit 0, no FAIL or WARN, files under `calibration/coupons/out/`, and prints the key and how to
  read it. `--print-ready` writes the manifest. `build --all` does not pick up `calibration/coupons`.
- [ ] Run: fail. Implement. Run: pass.

### Task 5: verification

- [ ] `uv run pytest -q`, `uv run cad.py build --all`, a PNG of each coupon looked at, a fresh review.
