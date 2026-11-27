# Style Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `cadlib.style` package that gives parts an architectural form language (gothic, gaudi, hitech, parametric), a graded hex/tri lattice, and two archetypes (cantilever bracket, hanger kit), all printable by construction.

**Architecture:** Styling happens in 2D: elevations, openings and lattices are build123d `Face`s in a local (u, v) plane, composed with 2D booleans, then extruded to depth and finished. Planar archetypes print lying on their elevation side by default, so every cut is vertical. Openings on walls that stand upright in print are clipped to 45° roofs. A small style log carries "cosmetics dropped or shrunk" notes into the build report.

**Tech Stack:** Python 3.12, build123d 0.13, trimesh 5.2, numpy, scipy, pytest. New dev-only dependency: `rtree` (ray casting in the strict thickness test).

**Spec:** `docs/superpowers/specs/2026-11-27-style-module-design.md`

## Global Constraints

- Everything through `uv`: `uv run pytest`, `uv run cad.py ...`. Install nothing globally. Network only for `uv add`.
- Numbers come from the profile `p` (`printer.toml` via `cadlib.config`). Dimensionless style ratios live in the dialect.
- Holes for screws only through `cadlib.fasteners`.
- Overhang limit is `cadlib.checks.OVERHANG_DEG` (45°). Walls and bars ≥ `p.min_wall_mm`.
- New `printer.toml` key: `[printer] max_bridge_mm = 10`, exposed as `Profile.max_bridge_mm: float = 10.0`.
- Results stay B-rep (`build()` returns a build123d solid) so STEP is exported.
- Code, comments, docs, CLI output in English. `pathlib` only, no OS-specific code, no network.
- **No commits or pushes unless the owner asks in the conversation.** Every "Checkpoint" step means: run the listed checks, then stop and report; commit only on the owner's explicit request.
- The owner's local parts (untracked folders under `parts/`, and `parts/lamp-hanger*`) are not edited.
- Build budget: a styled example builds in < 30 s on the PC.

## Review Focus

1. A panel too small for one lattice cell: expect the panel left solid and a "Style" note, never an exception or an empty cut.
2. A larger nozzle (`--nozzle 0.8`, `min_wall_mm` 2.4): lattices, ribs and openings re-derive from `p`. A span too small for the rules gives a `ValueError` in words.
3. A typo in `--set STYLE=gotic`: expect a clear error listing the four dialects.
4. `print_down` outside an archetype's `allowed_print_down`: expect a `ValueError` naming the allowed values.
5. OCCT refusing a fillet on a fused archetype: expect a single valid solid, the edge dropped or halved, and a "Style" note in the report.

Each line has a test in the owning task (Tasks 1, 4, 6, 7).

---

## File Structure

| File | Responsibility |
|---|---|
| `cadlib/style/__init__.py` | Public re-exports. |
| `cadlib/style/log.py` | Style notes collected during `build()` and drained into the report. |
| `cadlib/style/plane.py` | Print orientation in a sketch plane: in-plane "up" or none. |
| `cadlib/style/outline.py` | 2D outlines: arches, 45° roof clipping, polygons to `Face`. |
| `cadlib/style/lattice.py` | Hex/tri lattice cutters in 2D, graded, with keep-outs. |
| `cadlib/style/members.py` | 2D members: tapered beam, curved beam, catenary, truss, raised rib. |
| `cadlib/style/dialects.py` | The four dialects: their choices and edge finish. |
| `cadlib/style/joints.py` | Dovetail with a detent. |
| `cadlib/style/archetypes/types.py` | `Tunable`, `Load`, `Support`, `Archetype`, `Piece`, `Kit`. |
| `cadlib/style/archetypes/cantilever.py` | Cantilever bracket in four dialects. |
| `cadlib/style/archetypes/hanger.py` | Hanger kit: mount, arms with cradles, split segments. |
| `cadlib/finish.py` | Modified: report halved/skipped edges to the style log. |
| `cadlib/config.py`, `printer.toml` | Modified: `max_bridge_mm`. |
| `cad.py` | Modified: drain style notes into the report in `build` and `kit`. |
| `tests/style_checks.py` | Strict printability helpers, tests only. |
| `parts/example-styles/` | Cantilever example, `STYLE` parameter. |
| `parts/example-hanger-kit*/` | Hanger kit example: params, mount, arm A, arm B, `kit.py`. |

---

### Task 1: Style log, finish notes, report line, `max_bridge_mm`

**Files:**
- Create: `cadlib/style/__init__.py`, `cadlib/style/log.py`
- Modify: `cadlib/finish.py`, `cadlib/config.py`, `printer.toml`, `cad.py` (`_build` after `check_mesh`, ~line 304; `cmd_kit.part()` after `check_mesh`, ~line 621)
- Test: `tests/test_style_log.py`, `tests/test_finish.py` (add)

**Interfaces:**
- Produces:
  - `StyleNote(tool: str, level: Literal["info", "warn"], message: str)` frozen dataclass
  - `note(tool: str, message: str, level: Literal["info", "warn"] = "warn") -> None`
  - `drain() -> list[StyleNote]` returns and clears the notes
  - `Profile.max_bridge_mm: float` (default 10.0)
  - `soften` / `bevel` keep their signatures and also call `note("finish", ...)` when any edge was halved or skipped

- [ ] **Step 0: Baseline.** Run `uv run cad.py build --all` and save the list of FAIL lines to the scratchpad. Task 11 compares against it.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_style_log.py
from cadlib.style import log

def test_drain_returns_and_clears():
    log.drain()
    log.note("lattice", "3 cells dropped")
    log.note("finish", "ok", level="info")
    notes = log.drain()
    assert [(n.tool, n.level) for n in notes] == [("lattice", "warn"), ("finish", "info")]
    assert log.drain() == []

def test_profile_has_max_bridge():
    from cadlib.config import load_profile
    assert load_profile().max_bridge_mm == 10.0

def test_build_report_shows_style_line(repo_copy, capsys, tmp_path):
    # a throwaway model whose build() logs a note
    folder = tmp_path / "parts" / "noted"
    folder.mkdir(parents=True)
    (folder / "model.py").write_text(
        "from build123d import Box\nfrom cadlib.style.log import note\nNAME='noted'\n"
        "def build(p):\n    note('lattice', '2 cells dropped')\n    return Box(10, 10, 10)\n",
        encoding="utf-8")
    from cad import main
    assert main(["build", str(folder)]) == 0
    assert "[WARN] Style: lattice: 2 cells dropped" in capsys.readouterr().out
```

```python
# tests/test_finish.py, add (Review Focus 5)
def test_soften_notes_dropped_edges():
    from cadlib.style import log
    log.drain()
    body, done = soften(block(), vertical_edges(block()), 50.0)  # far too big for a 20 mm block
    assert body.is_valid and len(body.solids()) == 1
    notes = log.drain()
    assert notes and notes[0].tool == "finish" and "skipped" in notes[0].message
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_style_log.py tests/test_finish.py -v`
Expected: FAIL (`ModuleNotFoundError: cadlib.style`, missing `max_bridge_mm`).

- [ ] **Step 3: Implement**

`log.py`: a module-level list. `finish._apply` counts edges done at full size, at half size and skipped, and when halved + skipped > 0 calls `note("finish", f"{op} {size:g} mm: {halved} of {n} edges at half size, {skipped} skipped")` (`op` is "rounding" or "chamfer"). `config.py`: new field and `float(printer.get("max_bridge_mm", 10))`. `printer.toml`: `max_bridge_mm = 10  # longest bridge the style tools rely on`. `cad.py`: call `drain()` right before `run_model` (clears leftovers) and after `check_mesh` add each note as `report.add("Style", n.level, f"{n.tool}: {n.message}")`. Same in `cmd_kit.part()`.

- [ ] **Step 4: Run the tests and the whole suite**

Run: `uv run pytest -q`
Expected: all pass. Existing parts only gain INFO/WARN lines, no FAIL.

- [ ] **Step 5: Checkpoint** (no commit unless the owner asks)

---

### Task 2: Strict printability helpers for tests

**Files:**
- Create: `tests/style_checks.py`, `tests/test_style_checks.py`
- Modify: `pyproject.toml` (`uv add --group dev rtree`)

**Interfaces:**
- Produces (tests only):
  - `steep_overhang_area(mesh: trimesh.Trimesh, print_down, max_bridge_mm: float, bed_band_mm: float = 1.0) -> float` in mm²
  - `thinnest_wall(mesh: trimesh.Trimesh, samples: int = 4000, seed: int = 0) -> float` in mm
  - `assert_printable(mesh, print_down, p) -> None`: `steep_overhang_area(...) <= 1.0` and `thinnest_wall(...) >= 0.95 * p.min_wall_mm`

Rules pinned by the spec:
- Turn the mesh with `checks.orient_for_print(mesh, print_down)`. A face is steep when its normal's z < −cos(45°) (same criterion as `checks.overhang_fraction`).
- Exempt faces within `bed_band_mm` of the bed (bed chamfers).
- Exempt horizontal down-facing patches (normal within 2° of −z): group them into coplanar connected patches (`mesh.facets`, plus single triangles), project to XY, and exempt the patch when the shorter side of `trimesh.bounds.oriented_bounds_2D` ≤ `max_bridge_mm`.
- `thinnest_wall`: sample points on the surface, cast a ray inward along −normal (`mesh.ray.intersects_location`, start offset 1e-3 mm), thickness = distance to the first hit. Report the 1st percentile, not the minimum, so sharp corners do not count as thin.

- [ ] **Step 1: Write the failing tests**

```python
from build123d import Box, Pos, Cylinder, Rot
from cadlib.export import shape_to_mesh
from cadlib.config import load_profile
from style_checks import steep_overhang_area, thinnest_wall

P = load_profile()

def test_box_has_no_steep_area():
    assert steep_overhang_area(shape_to_mesh(Box(20, 20, 20)), None, P.max_bridge_mm) <= 1.0

def test_wide_shelf_is_steep():
    t = Pos(0, 0, 10) * Box(10, 10, 20) + Pos(15, 0, 18) * Box(30, 10, 4)  # 20 mm unsupported shelf
    assert steep_overhang_area(shape_to_mesh(t), None, P.max_bridge_mm) > 100

def test_short_bridge_is_exempt():
    # two pillars 8 mm apart joined at the top: an 8 mm bridge
    t = Pos(-6, 0, 5) * Box(4, 10, 10) + Pos(6, 0, 5) * Box(4, 10, 10) + Pos(0, 0, 11) * Box(16, 10, 2)
    assert steep_overhang_area(shape_to_mesh(t), None, P.max_bridge_mm) <= 1.0

def test_thin_fin_is_found():
    t = Box(20, 20, 4) + Pos(0, 0, 7) * Box(20, 0.8, 10)
    assert thinnest_wall(shape_to_mesh(t)) < 1.0
```

- [ ] **Step 2: Run to verify they fail.** Run: `uv run pytest tests/test_style_checks.py -v`. Expected: FAIL (no module `style_checks`).
- [ ] **Step 3: Add `rtree` to the dev group and implement the helpers** per the rules above. `tests/` has no `__init__.py`, so pytest's default import mode puts it on `sys.path`: import as `from style_checks import ...`.
- [ ] **Step 4: Run.** Run: `uv run pytest tests/test_style_checks.py -v`. Expected: PASS.
- [ ] **Step 5: Checkpoint**

---

### Task 3: Sketch plane, outlines, arches and 45° roof clipping

**Files:**
- Create: `cadlib/style/plane.py`, `cadlib/style/outline.py`
- Test: `tests/test_style_outline.py`

**Interfaces:**
- Produces:
  - `in_plane_up(plane: build123d.Plane, print_down) -> tuple[float, float] | None`: the print "up" (−down, default +Z) projected into the plane's (u, v) axes and normalised, or `None` when its in-plane length < 0.1 (the plane lies flat in print).
  - `ArchKind = Literal["pointed", "catenary", "round", "oval"]`
  - `arch(kind: ArchKind, span: float, rise: float, n: int = 64) -> list[tuple[float, float]]`: closed convex outline in (u, v), base on v = 0 from −span/2 to +span/2, apex towards +v. `pointed` with rise < span·√3/2 is allowed (drop arch); `oval` is an ellipse with width = span, height = rise.
  - `clip_roof(points, up: tuple[float, float] | None, max_deg: float = 45.0) -> list[tuple[float, float]]`
  - `to_face(points, plane: Plane = Plane.XZ) -> Face`
  - `opening(kind: ArchKind, span: float, rise: float, up, *, plane: Plane = Plane.XZ, at: tuple[float, float] = (0, 0)) -> Face`: `arch` → rotate so its apex points to `up` (no rotation when `up` is None) → `clip_roof` → translate → `to_face`.

`clip_roof` algorithm (pin it): with `up` = None return the points unchanged. Otherwise rotate points so `up` is +v. The outline must be convex (`ValueError("clip_roof needs a convex outline")` otherwise). Walk the upper chain. Find the leftmost point where the chain's slope falls to ≤ tan(max_deg) and the rightmost where it rises to ≥ −tan(max_deg). Replace the chain between them with the two lines of slope ±tan(max_deg) through those points, meeting at their intersection. Rotate back.

- [ ] **Step 1: Write the failing tests**

```python
import math
import pytest
from cadlib.style.outline import arch, clip_roof, opening

def _max_roof_overhang_deg(pts):
    """Largest overhang (degrees from vertical) of the hole's roof, up = +v.

    A roof edge is one whose outward normal (pointing away from the hole's centroid) has v > 0;
    its overhang from vertical is the angle between that normal and the horizontal."""
    cu = sum(u for u, _ in pts) / len(pts)
    cv = sum(v for _, v in pts) / len(pts)
    worst = 0.0
    for (u0, v0), (u1, v1) in zip(pts, pts[1:] + pts[:1]):
        du, dv = u1 - u0, v1 - v0
        length = math.hypot(du, dv)
        if length < 1e-9:
            continue
        nu, nv = dv / length, -du / length
        if nu * ((u0 + u1) / 2 - cu) + nv * ((v0 + v1) / 2 - cv) < 0:
            nu, nv = -nu, -nv
        if nv > 0:
            worst = max(worst, math.degrees(math.asin(min(1.0, nv))))
    return worst

def test_equilateral_pointed_needs_no_clip():
    pts = arch("pointed", 20, 20 * math.sqrt(3) / 2)
    assert clip_roof(pts, (0, 1)) == pts

def test_catenary_gets_45_cap():
    clipped = clip_roof(arch("catenary", 30, 15), (0, 1))
    assert _max_roof_overhang_deg(clipped) <= 45.0 + 1e-6

def test_circle_becomes_teardrop_when_up_sideways():
    clipped = clip_roof(arch("oval", 10, 10), (1, 0))
    assert max(u for u, _ in clipped) > 5.0  # tip grows towards +u

def test_flat_plane_leaves_outline():
    pts = arch("round", 10, 5)
    assert clip_roof(pts, None) == pts

def test_opening_face_area():
    f = opening("round", 10, 5, None)
    assert f.area == pytest.approx(math.pi * 25 / 2, rel=0.01)
```

- [ ] **Step 2: Run to verify they fail.** Run: `uv run pytest tests/test_style_outline.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** per the interfaces. `catenary`: v = rise − a·(cosh(u/a) − 1) with `a` solved (scipy `brentq`) so v(±span/2) = 0.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Checkpoint**

---

### Task 4: Lattice

**Files:**
- Create: `cadlib/style/lattice.py`
- Test: `tests/test_style_lattice.py`

**Interfaces:**
- Consumes: `in_plane_up`, `to_face` (Task 3), `note` (Task 1).
- Produces:
  - `LatticeKind = Literal["hex", "tri"]`
  - `Field = Callable[[float, float], float]` returning 0..1 at (u, v); 0 is the thinnest bar.
  - `LatticeCut(tool: Face | None, kept: int, dropped: int)` dataclass
  - `lattice(region: Face, p, *, kind: LatticeKind = "hex", cell: float | None = None, bar_min: float | None = None, bar_max: float | None = None, field: Field | None = None, keepout: list[Face] = (), up: tuple[float, float] | None = None) -> LatticeCut`

Rules pinned by the spec:
- Defaults: `cell` (across-flats pitch for hex, side for tri) = 4 × `p.min_wall_mm`. `bar_min` = `p.min_wall_mm`. `bar_max` = `bar_min` (uniform) unless given. Any value below these floors gives `ValueError` naming the floor.
- The pitch is fixed. The bar per cell = `bar_min + (bar_max − bar_min) · field(centre)`. The hole is the cell shrunk by the bar.
- Hex orientation: `up` None → pointy-top. `up` given → flat-top relative to `up`, and the hole's top edge must be ≤ `p.max_bridge_mm` (else `ValueError`).
- Tri: alternating up/down triangles. With `up` given, down-pointing triangles' top edges must be ≤ `p.max_bridge_mm`.
- A cell is kept only when its hole lies inside `region` shrunk inward by `bar_min` and clear of every keep-out grown by `bar_min`. Cells clipped by the border or a keep-out are dropped and counted.
- `kept == 0` → `tool = None` and `note("lattice", "panel too small for one cell: left solid")` (Review Focus 1). `dropped > 0` → `note("lattice", f"{dropped} cells dropped at edges and keep-outs", level="info")`.

- [ ] **Step 1: Write the failing tests**

```python
from build123d import Rectangle, Circle, Pos, Plane
from cadlib.config import load_profile
from cadlib.style import log
from cadlib.style.lattice import lattice

P = load_profile()

def test_uniform_hex_fills_panel():
    cut = lattice(Rectangle(80, 50), P)
    assert cut.kept > 20 and cut.tool is not None
    assert cut.tool.area < Rectangle(80, 50).area

def test_tiny_panel_stays_solid():
    log.drain()
    cut = lattice(Rectangle(5, 5), P)
    assert cut.tool is None and cut.kept == 0
    assert any("left solid" in n.message for n in log.drain())

def test_keepout_respected():
    hole = Pos(0, 0) * Circle(8)
    cut = lattice(Rectangle(80, 50), P, keepout=[hole])
    assert (cut.tool & hole).area == 0

def test_graded_bars_remove_less_where_field_is_high():
    left = lattice(Rectangle(80, 50), P, bar_max=3 * P.min_wall_mm, field=lambda u, v: 1.0)
    right = lattice(Rectangle(80, 50), P, bar_max=3 * P.min_wall_mm, field=lambda u, v: 0.0)
    assert left.tool.area < right.tool.area

def test_big_nozzle_rederives():                      # Review Focus 2
    p8 = load_profile(nozzle=0.8)
    cut = lattice(Rectangle(80, 50), p8)
    assert 0 < cut.kept < lattice(Rectangle(80, 50), P).kept

def test_cell_below_floor_rejected():
    with pytest.raises(ValueError, match="min"):
        lattice(Rectangle(80, 50), P, cell=2.0)
```

- [ ] **Step 2: Run to verify they fail.** Expected: FAIL.
- [ ] **Step 3: Implement.** Cell centres from build123d `HexLocations` (hex) or a computed triangular grid (tri). Build the hole polygons in numpy, test containment with 2D booleans on the region, fuse kept holes into one `Face`.
- [ ] **Step 4: Run.** Expected: PASS. Also time `lattice(Rectangle(200, 140), P)`: must finish under 10 s on the PC.
- [ ] **Step 5: Checkpoint**

---

### Task 5: Members

**Files:**
- Create: `cadlib/style/members.py`
- Test: `tests/test_style_members.py`

**Interfaces:**
- Consumes: `to_face` (Task 3).
- Produces (all in (u, v) of `Plane.XZ` unless a `plane` is given, returning `Face` unless stated):
  - `taper_beam(p0: tuple[float, float], p1: tuple[float, float], w0: float, w1: float, *, p) -> Face`: straight, width linear from `w0` at `p0` to `w1` at `p1`, flat ends.
  - `curved_beam(centre: list[tuple[float, float]], widths: list[float], *, p) -> Face`: spline centreline, width interpolated per point, both sides as splines.
  - `catenary(p0, p1, sag: float, n: int = 32) -> list[tuple[float, float]]`: points of a catenary hanging `sag` below the chord.
  - `truss(nodes: list[tuple[float, float]], members: list[tuple[int, int]], bar: float, node_d: float, *, p) -> Face`
  - `rib(path: list[tuple[float, float]], width: float, height: float, plane: Plane, *, p) -> Solid`: a raised rib on the plane's face, extruded `height` along the plane normal.
- Every function that takes `p` raises `ValueError` mentioning `min_wall` when a width, bar or node is below `p.min_wall_mm`.

- [ ] **Step 1: Write the failing tests**

```python
def test_taper_area():
    f = taper_beam((0, 0), (100, 0), 10, 4, p=P)
    assert f.area == pytest.approx(100 * 7, rel=1e-3)

def test_catenary_sag():
    pts = catenary((0, 0), (100, 0), 20)
    assert min(v for _, v in pts) == pytest.approx(-20, abs=0.05)

def test_truss_is_one_face():
    f = truss([(0, 0), (60, 0), (30, 30)], [(0, 1), (1, 2), (2, 0)], 3, 6, p=P)
    assert len(f.faces()) == 1

def test_thin_member_rejected():
    with pytest.raises(ValueError, match="min_wall"):
        taper_beam((0, 0), (50, 0), 0.5, 0.5, p=P)
```

- [ ] **Step 2–4:** run (FAIL), implement, run (PASS).
- [ ] **Step 5: Checkpoint**

---

### Task 6: Dialects

**Files:**
- Create: `cadlib/style/dialects.py`
- Test: `tests/test_style_dialects.py`

**Interfaces:**
- Consumes: `soften`, `bevel` (Task 1).
- Produces:
  - `Dialect` frozen dataclass: `name: str`, `opening: ArchKind`, `lattice: Literal["none", "hex", "tri"]`, `edge: Literal["chamfer", "fillet"]`, `edge_ratio: float`, `relief_ribs: bool`, `taper: float` (tip width / root width)
  - `DIALECTS: dict[str, Dialect]` with exactly:

| name | opening | lattice | edge | edge_ratio | relief_ribs | taper |
|---|---|---|---|---|---|---|
| gothic | pointed | none | chamfer | 0.08 | True | 0.6 |
| gaudi | catenary | none | fillet | 0.25 | False | 0.45 |
| hitech | round | tri | fillet | 0.05 | False | 1.0 |
| parametric | oval | hex | fillet | 0.15 | False | 0.5 |

  - `get_dialect(name: str) -> Dialect`: `ValueError(f"unknown style {name!r}, there are: gothic, gaudi, hitech, parametric")` (Review Focus 3)
  - `finish_extrusion(body: Solid, dialect: Dialect, depth: float, print_down, p) -> Solid`: edge size = clamp(`edge_ratio` · depth, `p.layer_mm`, depth / 3). Edges on the bed in print: `bevel` at 45° with `max(p.layer_mm * 2, 0.4)`. Edges vertical in print: the dialect edge. Top edges in print: the dialect edge. Uses `checks.down_vector`.

- [ ] **Step 1: Tests:** unknown name message lists all four. `finish_extrusion` on an extruded L returns one valid solid for every dialect, and for gaudi with depth 10 the volume drops by more than for hitech.
- [ ] **Step 2–4:** run (FAIL), implement, run (PASS).
- [ ] **Step 5: Checkpoint**

---

### Task 7: Archetype types and the cantilever, example part

**Files:**
- Create: `cadlib/style/archetypes/__init__.py`, `cadlib/style/archetypes/types.py`, `cadlib/style/archetypes/cantilever.py`, `parts/example-styles/model.py`, `parts/example-styles/README.md`
- Test: `tests/test_style_cantilever.py`

**Interfaces:**
- Consumes: Tasks 1–6.
- Produces:
  - `Tunable(name: str, value: float, lo: float, hi: float, unit: str = "mm")` frozen
  - `Load(point: tuple[float, float, float], force_n: tuple[float, float, float])` frozen
  - `Support(point: tuple[float, float, float], normal: tuple[float, float, float])` frozen: a planar face held fixed, found by a point on it and its outward normal
  - `Archetype(solid: Solid, print_down: str, allowed_print_down: tuple[str, ...], supports: list[Support], loads: list[Load], tunables: dict[str, Tunable])`
  - `Piece(solid: Solid, print_down: str, allowed_print_down: tuple[str, ...])` and `Kit(pieces: dict[str, Piece], supports: list[Support], loads: list[Load], tunables: dict[str, Tunable])` (used in Task 9)
  - `CantileverSpec` frozen: `reach: float`, `height: float`, `depth: float`, `root_t: float`, `plate_t: float`, `screw: str = "M4"`, `screw_count: int = 2`, `tip_hole: str | None = "M4"`, `load_n: float = 20.0`
  - `cantilever(style: str, spec: CantileverSpec, p, print_down: str = "-y") -> Archetype`

Geometry pinned by the spec:
- Frame: wall face is the plane x = 0, the plate occupies −`plate_t` ≤ x ≤ 0, the arm runs along +X at the top, z from 0 to `height`, depth along Y centred on y = 0. The elevation lives in `Plane.XZ`.
- `allowed_print_down = ("-y", "-x")`. Anything else → `ValueError` naming them (Review Focus 4). `-y`: lying on its side, `in_plane_up` gives None. `-x`: plate on the bed, `up` = (1, 0) in (u, v).
- Arm root thickness `root_t`, tip thickness `root_t · dialect.taper`, floored at `2 · p.min_wall_mm` plus the tip hole's room.
- Bracing between plate and arm, per dialect:
  - gothic: a solid web with a pointed-arch opening, plus a small pointed-arch rosette above it when room allows. Relief ribs (height `6 · p.layer_mm`, width `p.min_wall_mm`) follow the arch on the +Y face.
  - gaudi: a `curved_beam` along a `catenary` from the plate's lower end to the arm at 0.8 · `reach`, width from 1.6 · `root_t` to `root_t`. No web. The arm itself is a `curved_beam` too.
  - hitech: a `truss` (plate bottom, arm root, arm at 0.5 and 0.9 · reach) with node discs Ø `2.5 · bar`. The wall plate between the screws gets a uniform `tri` `lattice`.
  - parametric: a web whose outline is a spline (`curved_beam` underside), its region filled with a graded `hex` `lattice`, `field` = 1 − distance from the plate–arm corner / diagonal length, `bar_max = 3 · p.min_wall_mm`.
- Screws through the plate along X via `fasteners.clearance_hole`, keep-out discs (Ø = hole + 4 · `p.min_wall_mm`) passed to every lattice and opening.
- `supports`: one `Support` on the plate's wall face. `loads`: one `Load` at the tip hole, `(0, 0, -spec.load_n)`.
- `tunables`: `root_t` (lo `2·min_wall`, hi `height/3`), `plate_t` (lo `2·min_wall`, hi 12), `depth` (lo 10, hi 60).

Example part `parts/example-styles/model.py`: parameters `STYLE = "gothic"`, `REACH = 120.0`, `HEIGHT = 90.0`, `DEPTH = 20.0`, `ROOT_T = 10.0`, `PLATE_T = 6.0`, `PRINT_DOWN = "-y"`, `EXPECTED_BODIES = 1`, `NAME = "example-styles"`. `build(p)` returns `cantilever(STYLE, spec, p, PRINT_DOWN).solid`.

- [ ] **Step 1: Write the failing tests**

```python
import time, pytest
from cad import main
from cadlib.export import shape_to_mesh
from style_checks import assert_printable

STYLES = ["gothic", "gaudi", "hitech", "parametric"]
SPEC = CantileverSpec(reach=120, height=90, depth=20, root_t=10, plate_t=6)

@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("down", ["-y", "-x"])
def test_cantilever_printable(style, down):
    a = cantilever(style, SPEC, P, down)
    assert a.solid.is_valid and len(a.solid.solids()) == 1
    assert_printable(shape_to_mesh(a.solid), down, P)

def test_bad_print_down():
    with pytest.raises(ValueError, match="-y.*-x"):
        cantilever("gothic", SPEC, P, "z")

def test_hooks_declared():
    a = cantilever("gaudi", SPEC, P)
    assert a.loads[0].force_n == (0, 0, -20.0) and a.supports and "root_t" in a.tunables

@pytest.mark.parametrize("style", STYLES)
def test_example_builds_fast(style, repo_copy, capsys):
    folder = repo_copy("parts/example-styles")
    t0 = time.perf_counter()
    assert main(["build", str(folder), "--set", f"STYLE={style!r}"]) == 0
    assert time.perf_counter() - t0 < 30
    assert "FAIL" not in capsys.readouterr().out

def test_unknown_style_via_set(repo_copy, capsys):
    assert main(["build", str(repo_copy("parts/example-styles")), "--set", "STYLE='gotic'"]) != 0
    assert "gothic, gaudi, hitech, parametric" in capsys.readouterr().out
```

- [ ] **Step 2: Run to verify they fail.** Run: `uv run pytest tests/test_style_cantilever.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** types, cantilever and the example part (README with a short "what and why" and history line).
- [ ] **Step 4: Run** the file, then `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Build the four previews.** Run: `uv run cad.py build parts/example-styles --set STYLE='<style>'` for each style, copying each `out/example-styles.png` to `out/example-styles-<style>.png`.
- [ ] **Step 6: Checkpoint**

---

### Task 8: OWNER REVIEW STOP

- [ ] **Step 1:** Show the owner the four PNGs and how to open each in OCP Viewer (`uv run --group viewer python -m ocp_viewer`, then a `show()` script).
- [ ] **Step 2:** Collect feedback on proportions, edge sizes and dialect choices. Change only the `DIALECTS` table values and cantilever ratios, rerun Task 7's tests.
- [ ] **Step 3:** Do not start Task 9 until the owner says the dialects are right.

---

### Task 9: Dovetail joint

**Files:**
- Create: `cadlib/style/joints.py`
- Test: `tests/test_style_joints.py`

**Interfaces:**
- Produces:
  - `DovetailSpec` frozen: `neck: float = 8.0`, `wide: float = 12.0`, `depth: float = 8.0`, `stop: float = 3.0`, `detent: float = 0.4`, `detent_r: float = 1.4`, `length: float` (along the slide)
  - `dovetail(spec: DovetailSpec, p) -> tuple[Solid, Solid]`: `(tenon, socket_tool)` in a local frame: the tenon grows from x = 0 towards +x, slides along +Y, the trapezoid is in XZ centred on z = 0. The socket tool is the tenon grown by `p.slide_fit_mm` on every flank, open at y = 0 and closed by `stop` at y = `length`. The detent is a half-sphere bump of radius `detent_r` protruding `detent` from the wide flank at mid-length.
- Validation (`ValueError` in words): `depth ≥ (wide − neck) / 2 / tan(45°)` so flanks are ≤ 45°, `neck ≥ 2 · p.min_wall_mm`, `stop ≥ p.min_wall_mm`.

- [ ] **Step 1: Tests:** tenon minus socket tool (without the detent) is empty. The gap between them is `p.slide_fit_mm` ± 0.01 at the neck (measured by section widths). Steep flanks are rejected. With `--nozzle 0.8`, a neck of 4 mm is rejected.
- [ ] **Step 2–4:** run (FAIL), implement, run (PASS).
- [ ] **Step 5: Checkpoint**

---

### Task 10: Hanger kit and its example

**Files:**
- Create: `cadlib/style/archetypes/hanger.py`, `parts/example-hanger-kit/hanger_params.py`, `parts/example-hanger-kit/model.py` (the mount), `parts/example-hanger-kit/kit.py`, `parts/example-hanger-kit/README.md`, `parts/example-hanger-kit-arm-a/model.py`, `parts/example-hanger-kit-arm-b/model.py`
- Test: `tests/test_style_hanger.py`

**Interfaces:**
- Consumes: Tasks 3–7, 9. `Kit`, `Piece` from Task 7.
- Produces:
  - `EndProfile(kind: Literal["rect", "trapezoid"], width: float, height: float, narrow: float | None = None)` frozen
  - `HangerSpec` frozen: `span: float`, `end_a: EndProfile`, `end_b: EndProfile`, `drop: float`, `mount_len: float = 70.0`, `mount_h: float = 18.0`, `depth: float = 38.0`, `arm_t: float = 8.0`, `cradle_len: float = 20.0`, `screw: str = "3"` (wood screw Ø for `fasteners.wood_screw_countersunk_hole`), `screw_count: int = 2`, `joint: DovetailSpec | None = None` (None → defaults with `length = depth`), `load_n: float = 15.0`
  - `hanger_kit(style: str, spec: HangerSpec, p) -> Kit`, cached with `functools.lru_cache` (all inputs are frozen and hashable), so each piece's `model.py` can call it without rebuilding the others.

Geometry pinned by the spec:
- The mount bar is centred on x = 0 at the ceiling (z from −`mount_h` to 0), screws vertical. Arm A goes to −X, arm B to +X. Each arm runs from a dovetail socket in the mount end down to a cradle whose pocket fits its `EndProfile` plus `p.slide_fit_mm` per side, open on top and on the −Y side for inserting the object. Object bottom at z = −`drop`, end faces at x = ±`span`/2.
- Every arm is an elevation in `Plane.XZ` styled by the dialect (tapered or curved member, lattice or openings in the web), extruded to `depth`, `print_down = "-y"`, `allowed_print_down = ("-y",)`.
- Splitting: when an arm's elevation bounding box exceeds `p.usable_volume_mm[0] − 10` in either direction, cut it along its centreline into the fewest equal-length segments that fit, each cut a dovetail perpendicular to the centreline. Segments are named `arm-a-1`, `arm-a-2`, … (the first one holds the mount joint).
- `loads`: two `Load`s at the cradle floors, `(0, 0, −load_n / 2)` each. `supports`: the mount's ceiling face. `tunables`: `arm_t`, `depth`, `mount_h`.
- Example: `hanger_params.py` holds `STYLE = "gothic"` and `SPEC = HangerSpec(span=400, end_a=EndProfile("rect", 32, 16), end_b=EndProfile("rect", 32, 7.2), drop=200)`. Each `model.py` loads it with `cadlib.shared.load_module` and returns its piece's solid. `kit.py`: `KITS = {"example-hanger-kit": [[(".", 1)], [("../example-hanger-kit-arm-a", 1)], [("../example-hanger-kit-arm-b", 1)]]}`.

- [ ] **Step 1: Write the failing tests**

```python
STYLES = ["gothic", "gaudi", "hitech", "parametric"]
SPEC = HangerSpec(span=400, end_a=EndProfile("rect", 32, 16), end_b=EndProfile("rect", 32, 7.2), drop=200)

@pytest.mark.parametrize("style", STYLES)
def test_pieces_fit_and_print(style):
    kit = hanger_kit(style, SPEC, P)
    assert set(kit.pieces) == {"mount", "arm-a", "arm-b"}
    for piece in kit.pieces.values():
        mesh = shape_to_mesh(piece.solid)
        assert_printable(mesh, piece.print_down, P)
        assert max(orient_for_print(mesh, piece.print_down).extents[:2]) <= P.usable_volume_mm[0]

def test_long_span_splits_arms():
    long = dataclasses.replace(SPEC, span=900)
    names = set(hanger_kit("gaudi", long, P).pieces)
    assert {"arm-a-1", "arm-a-2", "arm-b-1", "arm-b-2"} <= names

def test_cradle_fits_profile():
    arm = hanger_kit("gothic", SPEC, P).pieces["arm-a"].solid
    x0 = -SPEC.span / 2
    block = Pos(x0 + SPEC.cradle_len / 2, 0, -SPEC.drop + 8) * Box(SPEC.cradle_len, 32, 16)
    assert (arm & block).volume == pytest.approx(0, abs=1e-3)

def test_kit_command(repo_copy, capsys):
    mount = repo_copy("parts/example-hanger-kit")
    repo_copy("parts/example-hanger-kit-arm-a")
    repo_copy("parts/example-hanger-kit-arm-b")
    assert main(["kit", str(mount)]) == 0
    assert "FAIL" not in capsys.readouterr().out
    assert (mount / "out" / "example-hanger-kit.3mf").exists()
```

- [ ] **Step 2: Run to verify they fail.** Expected: FAIL.
- [ ] **Step 3: Implement** the archetype and the example folders.
- [ ] **Step 4: Run** the file, then `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Checkpoint**

---

### Task 11: Docs and the full rebuild

**Files:**
- Modify: `README.md` (a "Style" section: dialects, `STYLE`, toolkit, archetypes, the example commands), `.claude/skills/cad/SKILL.md` (when to use `cadlib.style`, the import line, that cosmetics notes appear under "Style"), `CLAUDE.md` (one line under "How to work": prefer `cadlib.style` tools for visible parts, choose a dialect with the owner)

- [ ] **Step 1:** Write the docs.
- [ ] **Step 2:** Run `uv run pytest -q`. Expected: all pass.
- [ ] **Step 3:** Run `uv run cad.py build --all`. Expected: no new FAIL compared with the run before Task 1 (record that run's FAIL list at the start of Task 1). New WARN lines from "Style" are listed for the owner.
- [ ] **Step 4:** Memory on workshop (optional, read-only build in the server's clone after the owner pulls the branch): `multiclaude/cad` build of `parts/example-styles` with `STYLE='parametric'` and `kit parts/example-hanger-kit` stay under the 1400 MB cap. Check that the assistant is asleep first. Report the peak.
- [ ] **Step 5: Checkpoint:** report to the owner. Commit and push only if asked.
