# Gridfinity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `cadlib.gridfinity`: a drawer-fitted Gridfinity base split into bed-sized pieces, and parametric bins with compartments, label shelf and simple tool pockets.

**Architecture:** One module with the standard's numbers, a layout step (cells, rims, gaps from the drawer's inside size and the profile), a split step (pieces under the bed limit), and build123d builders for plate pieces and bins. `cad.py build` learns to take a model that returns several pieces and writes one multi-plate 3MF for them, reusing what `kit` does.

**Tech Stack:** Python, build123d, trimesh, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-28-gridfinity-design.md`

## Global Constraints

- Standard sizes from kennetek/gridfinity-rebuilt-openscad (MIT), read from `src/core/standard.scad` and the baseplate and bin sources, not from memory. Source and licence in the module docstring and README "Licence".
- The standard's own sizes and clearances are not taken from `printer.toml`. Everything else (walls, fits, bed) comes from the profile `p`.
- New `[tolerances]` key `gridfinity_joint_mm = 0.1` (per joint between plate pieces), plus the plastic's `clearance_add_mm` like the other fits.
- Max cells per piece computed from `p.build_volume_mm` and `p.bed_margin_mm` (P2S: 246 mm usable → 5).
- Magnet pockets only through `cadlib.magnets.pocket`, lettering only through `cadlib.text.label`.
- Model code has no numbers for fits: they come from `p`.
- English in code, docs and CLI output. No network from scripts.
- No commits per task: the phase is committed as one commit on the owner's word. The owner's drawer part in `parts/` is local and never committed.

## Review Focus

- A drawer smaller than one cell plus gaps: a clear `ValueError`, not an empty plate.
- A leftover between 0 and `p.min_wall_mm` per side: no rim, the space stays as gap (525 × 296 across).
- A rim that would push an edge piece over the bed: the split takes one cell off that piece.
- PETG or ABS (bigger fits): the cell count is recomputed with the bigger gaps, and 525 × 296 still gives 12 × 7 in PETG.
- Pockets and compartments that do not fit the bin (wider than the inside, deeper than the floor allows, magnet too thick for the base): a clear `ValueError` naming the value.

---

### Task 1: Standard constants, layout and split

**Files:**
- Create: `cadlib/gridfinity.py`
- Modify: `printer.toml` (`gridfinity_joint_mm`), `cadlib/config.py` (Profile field `gridfinity_joint_mm: float = 0.1`, loaded with `+ add`)
- Test: `tests/test_gridfinity.py`

**Interfaces:**
- Produces:
  - Constants: `PITCH = 42.0`, `UNIT_H = 7.0`, `BIN_SIZE = 41.5`, `BASE_PROFILE`, `BASE_HEIGHT`, `BIN_RADIUS`, `PLATE_PROFILE`, `PLATE_HEIGHT`, `PLATE_RADIUS`, `LIP_PROFILE`, `LIP_SUPPORT_H`, `WALL`, `DIVIDER`, `MAGNET_FROM_SIDE` (values from the source).
  - `max_piece_cells(p) -> int`
  - `split_counts(n: int, limit: int) -> list[int]`
  - `@dataclass(frozen=True) Layout`: `cells_x, cells_y: int`, `rim: tuple[float, float, float, float]` (−X, +X, −Y, +Y), `gap_x, gap_y: float` (per side), `inside: tuple[float, float]`.
  - `baseplate_layout(inside_x: float, inside_y: float, p, align: str = "center") -> Layout`. `align` is `"center"` or one of `"-x" "+x" "-y" "+y"` (the rim all on the opposite side, grid against that wall). Same alignment per axis only when it names that axis.
  - `@dataclass(frozen=True) Piece`: `name: str`, `cells_x, cells_y: int`, `rim: tuple[float, float, float, float]`, `count: int`.
  - `split(layout: Layout, p) -> list[Piece]`: identical pieces grouped with `count`, names like `"a"`, `"b"`.

- [ ] **Step 1: Fetch the standard numbers.** Read `standard.scad`, the baseplate and bin `.scad` files in kennetek/gridfinity-rebuilt-openscad on the web. Note the values with their variable names in the constants' comments.
- [ ] **Step 2: Write the failing tests**

```python
def test_drawer_525x296_pla():
    lay = gf.baseplate_layout(525, 296, profile())
    assert (lay.cells_x, lay.cells_y) == (12, 7)
    assert lay.rim[0] == pytest.approx(lay.rim[1]) and lay.rim[0] + lay.rim[1] == pytest.approx(525 - 504 - 2 * lay.gap_x)
    assert lay.rim[2:] == (0, 0)          # 2 mm left across: below min_wall, stays gap
    assert lay.gap_y == pytest.approx(1.0)

def test_drawer_525x296_petg_still_7():
    assert gf.baseplate_layout(525, 296, profile(material="PETG")).cells_y == 7

def test_tight_width_drops_a_cell():
    lay = gf.baseplate_layout(525, 294.5, profile())
    assert lay.cells_y == 6 and sum(lay.rim[2:]) > 40

def test_align_minus_y_puts_rim_on_plus_y():
    lay = gf.baseplate_layout(300, 525, profile(), align="-y")
    assert lay.rim[2] == 0 and lay.rim[3] > 0

def test_too_small_drawer():
    with pytest.raises(ValueError, match="one cell"):
        gf.baseplate_layout(40, 200, profile())

def test_max_piece_cells_p2s():
    assert gf.max_piece_cells(profile()) == 5

@pytest.mark.parametrize("n,lim,out", [(12, 5, [4, 4, 4]), (7, 5, [4, 3]), (6, 5, [3, 3]), (5, 5, [5]), (1, 5, [1])])
def test_split_counts(n, lim, out):
    assert gf.split_counts(n, lim) == out

def test_split_12x7_fits_bed_and_counts():
    pieces = gf.split(gf.baseplate_layout(525, 296, profile()), profile())
    assert sum(pc.count for pc in pieces) == 6
    usable = 256 - 2 * 5
    for pc in pieces:
        assert pc.cells_x * 42 + pc.rim[0] + pc.rim[1] <= usable
        assert pc.cells_y * 42 + pc.rim[2] + pc.rim[3] <= usable

def test_split_6x6_fits_bed():
    pieces = gf.split(gf.baseplate_layout(6 * 42 + 3, 6 * 42 + 3, profile()), profile())
    assert sum(pc.count * pc.cells_x * pc.cells_y for pc in pieces) == 36
```

- [ ] **Step 3: Run** `uv run pytest tests/test_gridfinity.py -v`. Expected: FAIL, no module `cadlib.gridfinity`.
- [ ] **Step 4: Implement.** Layout: for each axis take the largest `n` with `n * PITCH + 2 * p.slide_fit_mm + (len(split_counts(n, max_piece_cells(p))) - 1) * p.gridfinity_joint_mm <= inside`. Leftover minus the minimum gap is the rim. A rim side under `p.min_wall_mm` becomes 0 and goes to the gap. Split: per axis `split_counts`, edge pieces take their rim. If an edge piece with its rim is over the usable bed, move one cell from it to its neighbour (or add a piece). Group identical pieces.
- [ ] **Step 5: Run the tests.** Expected: PASS.

### Task 2: Plate pieces

**Files:**
- Modify: `cadlib/gridfinity.py`
- Test: `tests/test_gridfinity.py`

**Interfaces:**
- Consumes: `Piece`, constants (Task 1).
- Produces: `baseplate(cells_x: int, cells_y: int, p, *, rim=(0, 0, 0, 0), magnets: str | None = None) -> Part`. Open-frame plate with the standard profile, solid rim at full plate height, bottom at Z=0, the cell grid's corner at the origin side given by the rim. `magnets` is a `cadlib.magnets` size name (`"6x2"`) or None.
- `piece_body(piece: Piece, p, magnets=None) -> Part` is a thin wrapper.

- [ ] **Step 1: Write the failing tests**

```python
def test_plate_2x2_size_and_height():
    bb = gf.baseplate(2, 2, profile()).bounding_box()
    assert bb.size.X == pytest.approx(84) and bb.size.Y == pytest.approx(84)
    assert bb.size.Z == pytest.approx(gf.PLATE_HEIGHT)

def test_plate_rim_adds_width_and_is_solid():
    plate = gf.baseplate(2, 1, profile(), rim=(10, 0, 0, 0))
    assert plate.bounding_box().size.X == pytest.approx(94)
    assert plate.is_valid()

def test_plate_magnet_pockets_remove_volume():
    a = gf.baseplate(1, 1, profile()).volume
    b = gf.baseplate(1, 1, profile(), magnets="6x2").volume
    assert b < a
```

- [ ] **Step 2: Run.** Expected: FAIL, no `baseplate`.
- [ ] **Step 3: Implement** with build123d: the cell cutter is `PLATE_PROFILE` swept round a rounded square of `PITCH`, corner `PLATE_RADIUS`, subtracted from a block. Magnet pockets at the source's positions, cut with `cadlib.magnets.pocket` from the bottom (a plate with magnets needs a floor: add one of the pocket's depth plus `p.min_wall_mm` and say so in the docstring).
- [ ] **Step 4: Run.** Expected: PASS.

### Task 3: Bins

**Files:**
- Modify: `cadlib/gridfinity.py`
- Test: `tests/test_gridfinity.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) Pocket`: `shape: str` (`"rect"`, `"circle"`, `"slot"`), `size: tuple[float, ...]` (rect: w, l; circle: d; slot: w, l), `depth: float`, `at: tuple[float, float]` (from the bin centre), `angle: float = 0`, `notch: bool = False`. Sizes are the object's measured sizes, the builder adds `p.slide_fit_mm`.
  - `bin_body(cells_x: int, cells_y: int, units: int, p, *, lip: bool = True, divisions: tuple[int, int] = (1, 1), widths: list[float] | None = None, label: str | None = None, shelf: bool = False, magnets: str | None = None, pockets: list[Pocket] = (), solid: bool = False) -> Part`. `solid=True` fills the bin to the top for a tool insert, pockets cut down from the top.

- [ ] **Step 1: Write the failing tests**

```python
def test_bin_1x1_footprint_and_height():
    bb = gf.bin_body(1, 1, 3, profile(), lip=False).bounding_box()
    assert bb.size.X == pytest.approx(gf.BIN_SIZE) and bb.size.Y == pytest.approx(gf.BIN_SIZE)
    assert bb.size.Z == pytest.approx(3 * gf.UNIT_H)   # check against the source's height rule

def test_bin_2x1_footprint():
    assert gf.bin_body(2, 1, 3, profile()).bounding_box().size.X == pytest.approx(2 * gf.PITCH - (gf.PITCH - gf.BIN_SIZE))

def test_bin_divisions_add_walls():
    assert gf.bin_body(2, 1, 3, profile(), divisions=(2, 1)).volume > gf.bin_body(2, 1, 3, profile()).volume

def test_bin_label_shelf_builds():
    assert gf.bin_body(1, 1, 3, profile(), shelf=True, label="M3").is_valid()

def test_tool_pockets_cut_volume():
    full = gf.bin_body(2, 1, 4, profile(), solid=True)
    cut = gf.bin_body(2, 1, 4, profile(), solid=True, pockets=[gf.Pocket("circle", (12,), 15, (0, 0))])
    assert cut.volume < full.volume

def test_pocket_too_wide():
    with pytest.raises(ValueError, match="pocket"):
        gf.bin_body(1, 1, 3, profile(), solid=True, pockets=[gf.Pocket("rect", (50, 10), 5, (0, 0))])

def test_pocket_too_deep():
    with pytest.raises(ValueError, match="deep"):
        gf.bin_body(1, 1, 3, profile(), solid=True, pockets=[gf.Pocket("circle", (10,), 30, (0, 0))])

def test_compartment_too_narrow():
    with pytest.raises(ValueError, match="compartment"):
        gf.bin_body(1, 1, 3, profile(), divisions=(30, 1))

def test_magnet_too_thick_for_base():
    with pytest.raises(ValueError, match="magnet"):
        gf.bin_body(1, 1, 3, profile(), magnets="10x5")
```

- [ ] **Step 2: Run.** Expected: FAIL, no `bin_body`.
- [ ] **Step 3: Implement.** Base per cell with `BASE_PROFILE`, body with outer radius `BIN_RADIUS`, walls `max(WALL, p.min_wall_mm)`, dividers `max(DIVIDER, p.min_wall_mm)`, the lip from `LIP_PROFILE` and `LIP_SUPPORT_H`. Label shelf per the source's tab (36°, so no supports), text through `label()` debossed on it. Validation errors name the value and the limit.
- [ ] **Step 4: Run.** Expected: PASS.

### Task 4: Several pieces from one model

**Files:**
- Modify: `cad.py` (`run_model`, `_build`, a shared helper with `cmd_kit` for plates and manifest), `cadlib/gridfinity.py` (`drawer_base`)
- Test: `tests/test_build_pieces.py`

**Interfaces:**
- Consumes: `split`, `piece_body` (Tasks 1, 2), `write_plates_3mf`, `plate_origin`, manifest helpers (existing).
- Produces:
  - `cadlib.export.Pieces`: `list[tuple[str, Shape | Trimesh, int]]` alias (name, body, count), and `run_model` accepts it.
  - `gridfinity.drawer_base(inside_x, inside_y, p, *, align="center", magnets=None) -> list[tuple[str, Part, int]]`.
  - `cad.py build` on such a model: each piece built and checked as its own part (files `out/<name>-<piece>.*`, own PNG and report), then `out/<name>.3mf` with one plate per copy and, with `--print-ready`, a kit-style manifest `out/<name>.print.json`. A piece failing its checks fails the build and writes no manifest.

- [ ] **Step 1: Write the failing tests** (a tmp model folder with a tiny `build(p)` returning two small boxes, one with count 2, run through `cad.main(["build", str(folder), "--print-ready"])`):

```python
def test_pieces_write_each_piece_and_a_plate_per_copy(tmp_path): ...
    # assert out/<name>-a.stl, out/<name>-b.stl exist, out/<name>.3mf has 3 plates,
    # manifest["plates"] has 3 entries, exit code 0

def test_piece_over_bed_fails_and_writes_no_manifest(tmp_path): ...
    # one piece 300 mm wide: exit code 1, no out/<name>.print.json

def test_drawer_base_525x296():
    pieces = gf.drawer_base(525, 296, profile())
    assert sum(c for _, _, c in pieces) == 6
```

- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Factor the single-body part of `_build` into a function called once per piece. Factor the plate and manifest code of `cmd_kit` into a helper used by both. The build of a single body stays byte-for-byte the same.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass (the existing build and kit tests included).

### Task 5: Docs and full verification

**Files:**
- Modify: `README.md` (module table, Licence: kennetek MIT), `CLAUDE.md` (rule: Gridfinity only through `cadlib.gridfinity`), `.claude/skills/cad/SKILL.md` (snippet: a drawer base model and a bin), `docs/superpowers/plans/2026-11-28-feature-roadmap.md` (phase 3 status, test pieces dropped by the owner), `templates/` only if the part template needs a pieces example.

- [ ] **Step 1: Update the docs** above.
- [ ] **Step 2: Build the owner's drawer locally (not committed):** `uv run cad.py new part drawer-base`, a model calling `drawer_base(525, 296, p)`, `uv run cad.py build parts/drawer-base`. Expected: 6 pieces, no FAIL, PNG shown to the owner.
- [ ] **Step 3: Verify:** `uv run pytest -q` all pass, `uv run cad.py build --all` no FAIL.
- [ ] **Step 4: Review** by a fresh reviewer on the whole phase diff, fix what it finds, re-run Step 3.
- [ ] **Step 5: Report to the owner** and commit on their word (check the index: no `parts/`, `out/`, `remix/*/source/`).
