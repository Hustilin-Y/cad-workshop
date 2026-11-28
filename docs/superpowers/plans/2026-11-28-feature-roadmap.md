# CAD workshop feature roadmap

Date: 2026-11-28. Status: approved order from the owner (openGrid first, bearings last).

Sources: the bearing seats spec (`docs/superpowers/specs/2026-11-27-bearing-seats-design.md`, its
appendix is the backlog) and the ideas session's merged order of foundation steps.

## Rules for every phase

- One phase is about one working day and ends green: `uv run pytest` passes, `uv run cad.py build --all`
  has no FAIL, docs (`README.md`, `CLAUDE.md`, the `cad` skill) describe what the phase added.
- A phase is self-contained: nothing half-built is left for the next one. Where a value waits for a
  coupon, the code ships with the starting guess and the coupon, and only `printer.toml` changes later.
- Foundation, not models. The owner asked for modules, checks and coupons, not finished parts. The one
  exception is `parts/example-bearing-hub/` from the bearing spec, kept at the owner's word. Module
  tools are tested on plain blocks, as `tests/test_fasteners.py` does.
- Every fit has a calibration coupon in `calibration/`. Dimensions from outside (bearing tables,
  Gridfinity, openGrid) carry their source in a comment, and no guessed numbers go into a table.
- Each phase starts only when the owner asks. Each phase gets its own short plan
  (`docs/superpowers/plans/`) written from this roadmap and its spec before code.
- `cadlib/style/` and the branch `worktree-style-module` belong to another session. Nothing here
  touches them. Phases that need style come after that branch is merged.
- Shared files the style branch also changes: `cadlib/config.py` (adds `Profile.max_bridge_mm`),
  `cad.py` (a "Style" report line), `printer.toml`. New `Profile` fields are added after the existing
  ones and new `printer.toml` keys in their own lines, so the merge stays a trivial conflict. A new
  report line reuses the style log if that branch is merged by then, otherwise a minimal one is added
  and unified at the merge.

## Order and why

The ideas session's order of foundation steps:
1 bearings, 2 temperature and materials, 3 `vessel`, 4 coupon generator, 5 Gridfinity,
6 openGrid and Multiconnect, 7 mounts, joints and beam estimate, 8 shafts and snap-fits, 9 hose,
10 style vessel archetype.

Changes made here:
- **The owner's call (2026-11-28): openGrid and Multiconnect first, bearings at the very end of
  everything.** The bearing spec is kept unchanged and becomes the last three phases (19 to 21), after everything else in the backlog.
- **Bearings take three days, not one.** The spec estimates four days of work. It is split into
  catalogue and seat, coupon with inner-ring tools and checks, and a close-out.
- **The coupon generator goes before `vessel`.** `vessel` then gets its leak coupon from the
  generator on the same day instead of a hand-made one that is rewritten later. With bearings at
  the end, the generator is built on its own, and the bearing coupon is later made through it.
- **Mounts, joints and the beam estimate move into week 1** to fill the days the bearings left.
- **The owner's calls (2026-11-28, after phase 1): the coupon generator right after openGrid, then
  Gridfinity.** All coupons come from the generator from the start, so Gridfinity takes its magnet
  pocket value from the generator's `magnet` coupon and needs no one-off strip.

## Week 1

### Phase 1. openGrid and Multiconnect interface

- **Goal:** the back of any of our parts can carry an openGrid snap interface or a Multiconnect slot,
  so it hangs on an openGrid board.
- **Scope:** `cadlib/opengrid.py`: the interface geometry only, as tools in the `cadlib.fasteners`
  style (subtracted from or added to a flat back face). No boards and no snaps of our own: those are
  printed from the official files. Dimensions taken with `inspect` and sections of the official
  STEP or STL, each with its source in a comment. A placement helper on a body face and a check that
  the back wall is thick enough around the slot. CC BY attribution (author, title, link, licence,
  "dimensions derived") in the module docstring, `README.md` "Licence", and one line in the README of
  every part that uses it. The official files stay local in `remix/*/source/` (ignored), as the
  project rules say.
- **Files:** `cadlib/opengrid.py` (new), `tests/test_opengrid.py` (new), `README.md`, `CLAUDE.md`,
  `.claude/skills/cad/SKILL.md`.
- **Depends on:** the official files on disk.
- **Done when:** tests on the slot and snap profile against the inspected sizes, a test block with
  each interface builds with no FAIL (overhangs and islands in the print orientation), full suite and
  `build --all` green.
- **Owner:** download the official openGrid snap and Multiconnect files (STEP if offered, else STL)
  and give the paths and the pages. Print one test block (about 10 g) and check it on a board.

### Phase 2. Coupon generator

- **Goal:** `uv run cad.py coupon <feature>` makes a labelled step series of any fit.
- **Scope:** `cadlib/coupon.py`: N samples with one parameter stepped, labels through `cadlib.text`,
  the plate kept on the bed. Features at start: `hole`, `press`, `slide`, `magnet` (pocket for a disc
  magnet, for Gridfinity), `thread`. CLI command, a
  `calibration/README.md` section. The design leaves room for a `bearing` feature in the bearing
  phases.
- **Files:** `cadlib/coupon.py` (new), `cad.py`, tests, docs.
- **Depends on:** nothing.
- **Done when:** each feature builds with no FAIL, a CLI test, labels readable in the PNG.
- **Owner:** measure the magnets, then print the `magnet` coupon (needed for phase 3) and the
  `hole`/`press`/`slide` coupons if the tolerance gauge was never printed.

### Phase 3. Gridfinity

- **Goal:** a minimal Gridfinity of our own with our checks.
- **Scope:** `cadlib/gridfinity.py`: baseplate N×M (plain, magnet, screw), bin base, stacking lip,
  label shelf through `label()`, magnet pocket (`cadlib.magnets.pocket`: nominal magnet Ø plus `magnet_fit_mm`, the value from
  the phase 2 `magnet` coupon), test pieces in `calibration/gridfinity/` (a 1×1 bin, a 2×2 plate),
  splitting a plate into pieces
  that fit the bed (5×5 maximum). A generic "grid of cups in a given compartment" generator (MEIHO
  inserts build on it later). Dimensions from kennetek/gridfinity-rebuilt-openscad (MIT), source and
  licence in the module docstring and in `README.md` "Licence". The standard's own clearances are
  kept as the standard says, not from `printer.toml`, so bins fit other people's plates.
- **Files:** `cadlib/gridfinity.py` (new), `calibration/gridfinity/` (new), `printer.toml`,
  `cadlib/config.py`, tests, `README.md`, docs.
- **Depends on:** phase 2 (the `magnet` coupon and its result), the owner's answers (screws, bins
  they own, sizes they want).
- **Done when:** tests on pitch, lip profile and pockets, a 6×6 plate splits into pieces that pass the
  bed check, a 1×1 bin and a 2×2 plate build green in tests.
- **Owner (before the code):** the `magnet` coupon result from phase 2, the screw type if plates go
  on with screws, whether Gridfinity bins or plates from others are at home to fit against, and the
  plate and bin sizes wanted. After: print the test pieces.

### Phase 4. Materials and environment

- **Goal:** a part declares where it lives, and the build fails when the plastic cannot take it.
- **Scope:** `hdt_c` per plastic in `[materials.*]` (from a maker's datasheet, source in a comment).
  TPU as a new plastic (no fit values until calibrated, a note that rigid-plastic fits do not apply).
  `ENVIRONMENT` or `SERVICE_TEMP_C` in a model with presets `room`, `car-dash`, `car-cabin`,
  `outdoor-sun`, `boat-sun` in `printer.toml`. A FAIL when the plastic's `hdt_c` minus a margin is
  below, naming the plastics that would pass. A UV note for the outdoor presets. "What not to print"
  rules (oarlocks and oar pins, motor mounts, lifting points, pressure parts, lead moulds) in
  `CLAUDE.md` and the skill.
- **Files:** `printer.toml`, `cadlib/config.py`, `cadlib/service.py` (new), `cad.py` (report line),
  tests, docs.
- **Depends on:** nothing.
- **Done when:** tests for each preset pass and fail at the edge, `build --all` green (no existing
  part declares an environment, so none changes).
- **Owner:** nothing.

### Phase 5. Vessel

- **Goal:** pots, cups and containers from a profile, with drainage and a saucer, built correctly.
- **Scope:** `cadlib/vessel.py`: a body of revolution from points or a spline, wall and floor from
  `p.min_wall_mm`, drain holes or slots, feet or ribs under the floor, a saucer with `slide_fit`
  clearance, a double shell (solid inner, outer for decor later). `PRINT_HINTS` guidance for
  `goal: "watertight"`. A `leak` coupon feature (2 to 3 wall counts).
- **Files:** `cadlib/vessel.py` (new), `cadlib/coupon.py`, tests, docs.
- **Depends on:** phases 4 (outdoor presets for pots) and 2.
- **Done when:** tests on wall, floor, drain area and saucer clearance, the leak coupon builds green.
- **Owner:** print the leak coupon, fill it with water for 24 hours, report which one stayed dry.

### Phase 6. Mounts and joints

- **Goal:** common ways to attach a part to something, as tools.
- **Scope:** `cadlib/mounts.py`: clamp for a board thickness, pipe clamp for a diameter, bolt pattern
  for a bought pad, a compatible 1"/1.5" ball (no brand names). `cadlib/joints.py`: the toothed
  rosette extracted from lamp-arm (lamp-arm itself is the owner's local part and is not edited). An
  optional openGrid back from phase 1 on mounts.
- **Files:** `cadlib/mounts.py`, `cadlib/joints.py` (new), tests, docs.
- **Depends on:** phase 1 for the openGrid option, else nothing.
- **Done when:** tests on clamp gap, rosette tooth count and engagement, ball Ø, all on plain blocks.
- **Owner:** nothing (measure a board or a pipe when a real part is made later).

### Phase 7. Beam estimate from `LOADS`

- **Goal:** a part declares its loads and the build estimates the safety margin, before any FEA.
- **Scope:** `LOADS` in a model (force, point, direction), a cantilever and simple-beam estimate from
  the root section, plastic strength per material in `printer.toml` (source in a comment, a reduced
  value across layers), a WARN when bending puts layers in tension in the chosen `PRINT_DOWN`, with
  the better side named in the message.
- **Files:** `cadlib/loads.py` (new), `printer.toml`, `cadlib/config.py`, `cad.py`, tests, docs.
- **Depends on:** phase 4 (material data).
- **Done when:** a known cantilever matches the hand formula within 5%, the layer WARN fires for a
  bar printed standing and not for one lying, `build --all` green.
- **Owner:** nothing.

## Later backlog (after week 1, in this order)

| # | Phase | Size | Depends on |
|---|---|---|---|
| 8 | `cadlib.shafts` (D-shaft, knurled spline, square) with a coupon | 1 day | phase 2 |
| 9 | Snap-fit cantilever generator with a strain check per plastic | 1 day | phases 2, 4 |
| 10 | `cadlib.hose`: hose barb, O-ring groove, seal coupon | 1 day | phases 2, 5 |
| 11 | G (BSPP) pipe thread profile in `threads.py`, teardrop and bent channels | 1 day | 10 |
| 11a | Printed internal threads below M6: `threads.internal_thread_tube` cannot fuse the turns at M3–M5 pitches (found by the phase 2 review); fix it, then open M3–M5 in the thread coupon | 0.5 day | none |
| 12 | `cadlib.assembly`: placements, interference and minimum clearance, motion steps | 1 day | none |
| 13 | `MEASURED` table template and broken-original checklist, SVG import to an outline | 1 day | none |
| 14 | Part families from a variants table, a generated catalogue of committed parts | 1 day | none |
| 15 | `PRINT_HINTS` keys `seam` and `xy_hole_compensation` | 0.5 day here | bambu-mcp schema change first |
| 16 | Vessel archetype in `cadlib.style` (lattice wrapped on a revolved surface) | 2 to 3 days | `worktree-style-module` merged, phase 5 |
| 17 | Styled brackets on top of mounts and the beam estimate | 1 to 2 days | style merged, phases 6, 7 |
| 18 | **Site and terrain models seen from above (mandatory, owner's request 2026-11-28).** See below. | L (3 to 4 days in 2 phases) | phase 4 for material notes, text labels exist; split-and-join from `worktree-style-module` if merged |
| 19 | Bearings A: catalogue, profile keys, `seat` (spec steps 1, 2, tests 1 to 8, 11) | 1 day | none |
| 20 | Bearings B: coupon through the generator, `pin`, `spacer`, `ring_relief`, `pair`, `lid_tool`, `require_*` (spec steps 3, 4). The owner prints the coupon with real bearings. | 1 day | 19, phase 2 |
| 21 | Bearings C: report line, creep WARN (uses phase 4 material data), `parts/example-bearing-hub/`, coupon values into `printer.toml`, docs (spec step 5) | 1 day | 20 |


### 18. Site and terrain models seen from above

- **What:** gift models of a company's plant (several sites), a small neighbourhood or district:
  building footprints extruded to heights, optional terrain, on a base with an engraved name or logo.
  Foundation first: a `cadlib.site` module and an import tool, models of real sites only on request.
- **Data sources:**
  - OpenStreetMap buildings and footprints (`building=*`), heights from `height` or
    `building:levels` × a default storey height (for example 3 m), a default for untagged buildings.
  - Terrain from a DEM: Copernicus GLO-30 or SRTM. Flat sites can skip it.
  - Alternative: the owner's own site plan or a DXF from the company (often better for a plant:
    OSM may lack inner buildings, and the company's plan is what they will recognise).
- **Licences:**
  - OSM is ODbL. A print or picture made from it is a "produced work": attribution
    "© OpenStreetMap contributors" is required, on the base or a card with the gift, and in the README
    of any committed example. Data extracts themselves (the derived database) are not committed to the
    public repo: if they were, they would have to be offered under ODbL. Our code stays MIT.
  - Copernicus DEM: free with attribution ("produced using Copernicus WorldDEM-30 ... ESA"), SRTM is
    public domain (NASA). Attribution goes into the part's README and, for Copernicus, on the card.
  - The owner's or the company's own plans: their property, kept local, never committed.
- **Offline rule:** `cad.py` and models never go online. Data is fetched once, by the owner or by a
  separate import tool outside the build (an Overpass export saved as `.osm`/GeoJSON, a DEM tile as
  GeoTIFF), and stored as a file in the part's folder (ignored by git). The build reads only that file.
  `tests/test_no_network.py` keeps covering the module.
- **Scale and minimum features (0.4 nozzle):** a 200 m site on a 200 mm base is 1:1000. Walls and
  gaps below about 0.8 mm (2 lines) disappear: buildings narrower than that are widened or dropped
  with a report line, streets narrower than 0.8 mm closed. Heights below 2 layers (0.4 mm) are raised
  to that. The build report lists what was merged, widened or dropped.
- **Large sites and several sites:** split into tiles that fit the P2S bed (246 × 246 after margins),
  joined by pins or a jigsaw edge, or several sites as separate pieces of a kit (`kit.py`), each on
  its own base, with an index label. The hanger's split-and-join on `worktree-style-module` is reused
  if merged by then.
- **Colour:** buildings, roads, water and green areas as separate bodies, so AMS can colour them
  (bambu-mcp would need multi-material support), or as separate parts glued later. Single colour by
  default.
- **Base:** a plinth with the name or logo through `cadlib.text.label`, the north arrow, the scale and
  the OSM attribution engraved on the side.
- **Privacy and security:** industrial sites can be sensitive. Use only what is public in OSM or what
  the company itself hands over, do not add details from other sources (aerial imagery, staff
  photos), do not model security fences, gates or critical infrastructure in detail, and keep real
  sites local (never committed). A committed example uses a generic or invented site.
- **Phases:** (a) import tool + footprints and heights + base and labels + scale rules, 2 days.
  (b) terrain from a DEM, tiling and jigsaw, colour bodies, 1 to 2 days.
- **Not started.** Questions for the owner when it starts: a first real site, the gift size, colour
  or single plastic.

The bearing spec's open questions (which bearings, PETG or PLA, slicer hints) are asked when
phase 19 starts.

Not planned (from the ideas review): printed bearings, statistical tolerance stacks, printed pipe
threads for pressure, engine-bay hoses, photogrammetry, finished fishing or pot models (they are
built later from these modules on request).

## Status

- Phase 1 (openGrid and Multiconnect) is built and verified in code, uncommitted until the owner
  reviews it. Its test pieces wait to be printed and tried on a board.
- Phase 2 (coupon generator) is committed. Thread coupons cover M6 to M12 (see 11a). After it:
  `cadlib.magnets` (nominal disc sizes, pocket tool) and a multi-size `magnet` coupon.

## Open questions before phase 2 (coupon generator)

1. Phase 1 test pieces: result on the board.
2. Magnets: answered. Neodymium discs, nominal sizes from sellers up to 10 × 3 (`cadlib.magnets`),
   no measuring. The `magnet` coupon prints 5x4, 6x2 and 10x3 strips.

## Open questions before phase 3 (Gridfinity)

1. The `magnet` coupon result (`uv run cad.py coupon magnet`).
2. Screws, if plates are screwed down: type and size.
3. Gridfinity bins or plates from others at home to fit against: which ones.
4. Sizes wanted: plates (cells or the drawer's inside size) and bins (cells, height units).
