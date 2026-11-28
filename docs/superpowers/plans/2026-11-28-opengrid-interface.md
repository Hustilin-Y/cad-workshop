# openGrid and Multiconnect interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `cadlib.opengrid` gives any part a Multiconnect slot or an openGrid snap on its back.

**Architecture:** one module of build123d tools (back face at Z = 0, part below, wall above, +Y up;
slots subtracted downward like `cadlib.fasteners`, snaps added upward), constants measured from the official modeling files with their source per value, a test
file that checks sections and, when the official files are on disk, the volume difference against
them. A calibration test block uses both tools.

**Tech Stack:** Python 3.12, build123d, trimesh, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-28-opengrid-interface-design.md`

## Global Constraints

- No numbers for tolerances from code: the interface sizes are the openGrid standard (with its own
  built-in clearance) and live as named constants in `cadlib/opengrid.py`, each with the source file.
- Attribution text: "openGrid - Wall/Desk mounting framework/ecosystem" by David D,
  https://makerworld.com/en/models/1179191-opengrid-wall-desk-mounting-framework-ecosystem , CC BY,
  dimensions derived from its modeling files. In the module docstring and `README.md` "Licence".
- The official files are never copied into the repo. Comparison tests read the folder in the
  environment variable `CAD_OPENGRID_SOURCE` and are skipped when it is unset.
- `tests/test_no_network.py` stays green. Everything in English. No commits until the owner says so.
- Do not touch `cadlib/style/`, `parts/` of the owner, `remix/*/source/`.

## Review Focus

- A slot whose `length` is shorter than the closed end radius (< 10.15): raise `ValueError` naming
  the minimum, not a broken solid. (Task 1)
- `detent=True` on a slot too short to hold the detent (length < 8.76): raise `ValueError`. (Task 1)
- `grid_positions` for a width smaller than one cell (< 28): returns an empty list, and
  `require_back`-style callers get a clear message rather than a silent part with no interface. (Task 3)
- A snap added to a back thinner than nothing (part with no flat back): out of scope, but the snap
  must be a single closed body so a union never yields extra bodies. (Task 2, `len(solids()) == 1`)
- Lite and full snaps must not be swapped: the full snap is 6.8 deep, Lite 3.4. (Task 2)

---

### Task 1: Multiconnect slot

**Files:**
- Create: `cadlib/opengrid.py`
- Create: `tests/test_opengrid.py`

**Interfaces:**
- Produces: `PITCH = 28.0`, `SLOT_DEPTH = 4.15`, `multiconnect_slot(length: float, *, detent: bool = False, flare: bool = True) -> Part`.
  Closed end up, connector centre at (0, 0), open end down at Y = −length, top at Z = 0.

- [ ] **Step 1: Write the failing tests** (block 40 × 60 × 10 with its top at Z = 0, minus the slot
  at the origin, length 30):
  - `test_slot_profile`: section at Y = 15: the cavity is 15.3 wide at Z = −0.2, 20.3 at Z = −3.5,
    depth 4.15 (all ±0.02).
  - `test_slot_closed_end`: section at Z = −3.5 reaches Y = −10.15 (±0.03).
  - `test_slot_detent`: with `detent=True`, cavity width at Z = −3.5, Y = 3.55 is 19.518 (±0.03),
    and at Y = 12 it is 20.3.
  - `test_slot_flare`: with `flare=True` the width at Y = length, Z = −0.05 is about 22.0 (±0.1);
    with `flare=False` it is 15.3.
  - `test_slot_too_short`: `length=8` raises `ValueError`, `detent=True, length=9` passes,
    `detent=True, length=8.5` raises.
  - `test_slot_matches_official` (skip without `CAD_OPENGRID_SOURCE`): the plain slot of length 28
    vs `Multiconnect modeling files/slot-negative.step` aligned by bounds: symmetric difference below
    3% of the official volume. Same for `snap-in-slot-negative.step` vs `detent=True`.
- [ ] **Step 2: Run** `uv run pytest tests/test_opengrid.py -q`: FAIL (module missing).
- [ ] **Step 3: Implement** the slot as an extruded dovetail polygon along Y, a revolved copy of the
  profile for the closed end, the detent as a subtracted bump in the wide zone, the flare as a cone
  (R 10.15 at Z = −4.15 to R 11.0 at Z = 0) at the open end. Tool sticks out by `EPS` above Z = 0.
- [ ] **Step 4: Run** the tests: PASS.

### Task 2: openGrid snap

**Files:**
- Modify: `cadlib/opengrid.py`
- Modify: `tests/test_opengrid.py`

**Interfaces:**
- Produces: `snap(*, lite: bool = False) -> Part`, front face at Z = 0, wall side at Z = 6.8
  (Lite 3.4), centred on the origin.

- [ ] **Step 1: Write the failing tests:**
  - `test_snap_size`: bounding box 25.6 × 25.6 (bumps included) × 6.8, Lite × 3.4.
  - `test_snap_octagon`: section at 1 mm below the front plate: across flats 24.8, corner leg 4.818.
  - `test_snap_slits`: section at Z = −3 (wall side well below the plate) shows four slits 0.6 wide,
    12.4 long, at 11.1 to 11.7 from the centre.
  - `test_snap_single_body`: `len(snap().solids()) == 1` for both variants.
  - `test_snap_matches_official` (skip without the source): symmetric difference with
    `Snap modeling files/openGrid Bare Snap.step` (flipped so its front is at Z = 0) below 3%, and the
    Lite one.
- [ ] **Step 2: Run:** FAIL.
- [ ] **Step 3: Implement** from the measured sections: octagon prism, front plate, four slits, tabs
  with a 0.4 gap under the plate, trapezoid bumps, the corner details read off the official sections.
- [ ] **Step 4: Run:** PASS.

### Task 3: placement helpers and the back check

**Files:**
- Modify: `cadlib/opengrid.py`, `tests/test_opengrid.py`

**Interfaces:**
- Consumes: `Profile` from `cadlib.config` (`min_wall_mm`).
- Produces: `grid_positions(width: float, height: float | None = None) -> list[tuple[float, float]]`
  (cell centres on a 28 grid that fit, centred on 0, Y = 0 when `height` is None);
  `BACK_MM = 6.4`; `require_back(thickness: float, p: Profile) -> None` raising `ValueError`.

- [ ] **Step 1: Tests:** `grid_positions(84)` → x = −28, 0, 28. `grid_positions(56)` → −14, 14.
  `grid_positions(20)` → []. `grid_positions(56, 56)` → 4 points. `require_back(4.15 + p.min_wall_mm, p)`
  passes, 0.01 less raises with "6.4" in the message.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.

### Task 4: test block, docs

**Files:**
- Create: `calibration/opengrid/model.py`, `calibration/opengrid/README.md`
- Modify: `README.md` (Layout, Licence, a short "openGrid" section), `CLAUDE.md` (rule: openGrid and
  Multiconnect backs only through `cadlib.opengrid`), `.claude/skills/cad/SKILL.md` (one import line,
  one example), `calibration/README.md` (one line).

- [ ] **Step 1:** two test pieces in one model (`EXPECTED_BODIES = 2`), laid out as printed: a
  28 × 40 slot piece `BACK_MM` thick, front on the bed, back up, with a Multiconnect slot
  (`detent=True`) opening upward, and an octagonal 2 mm tile on a `snap()`, the snap's wall side on
  the bed. `_validate` calls `require_back`. `PRINT_HINTS`
  `{"goal": ["fit", "cheap"], "goal_reason": "test pieces for the openGrid and Multiconnect fits"}`.
- [ ] **Step 2:** `uv run cad.py build calibration/opengrid`: no FAIL, show the PNG.
- [ ] **Step 3:** `test_parts.py` picks it up (check it does), docs written.

### Task 5: verification

- [ ] `uv run pytest -q` with and without `CAD_OPENGRID_SOURCE`: all green.
- [ ] `uv run cad.py build --all`: no FAIL.
- [ ] A fresh reviewer reads the diff against the spec.
