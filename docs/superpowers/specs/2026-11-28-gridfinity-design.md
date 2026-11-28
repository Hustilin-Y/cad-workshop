# Gridfinity: design (roadmap phase 3)

## Intent

The owner wants Gridfinity as a way to organise their desk drawers: a base made to fit one particular
drawer, then bins made for that base as needs come up. Planned drawers: tools plus small parts
storage, fishing tackle, technical bits, more later. Bins will be small boxes for bolts, holders
shaped for tools and other purposes. The first real job for the module will come after this phase.

The owner has no Gridfinity parts from others. We still keep the standard grid and profiles: it costs
nothing and lets bins from MakerWorld fit our bases and ours fit theirs.

## The first drawer (the owner's numbers)

- Inside 525 × 296 mm, straight walls and no fillets all round (owner, 2026-11-28: 525 × 295 by
  tape, the width re-measured as 296).
- Bins do not need to be held down: the drawer has walls, a plain base is enough.
- Drawer height: not given yet. Needed only when bins for it are designed (later task).

With a 42 mm grid: 12 × 7 cells (504 × 294 mm). Along the length 21 mm is left for a filler rim.
Across 2 mm is left: enough for the wall gaps and the one joint, too little for a rim, so 7 cells
with about 1 mm gap per side.

## Goals

1. A baseplate generator that takes a drawer's inside size and gives a base that fills it: as many
   whole cells as fit, the rest filled with a solid rim, a small gap to the drawer walls.
2. The base split into pieces that fit the P2S bed, laid side by side in the drawer, no joints.
3. Bins: a parametric box of N × M cells and H height units, with compartments, an optional label
   shelf, and an insert for simple tool pockets.

## Non-goals

- Interlocking or puzzle edges between plate pieces (walls hold them, owner does not need it).
- Screw-down plates (owner does not fix bins or plates). Can come later on request.
- Tool pockets traced from a photo or SVG outline: roadmap item 13. This phase does rectangles,
  circles and slots only.
- Printed test pieces in `calibration/gridfinity/` (owner, 2026-11-28: not needed, only the module).
- Weighted bases, drawer-handle cut-outs, stacking bins in tall stacks beyond the standard lip.

## Anti-goals

- A base that rattles or sticks in the drawer (wrong gap), or pieces that do not meet flush.
- Bins that do not drop into a standard base, or the standard changed to suit our printer.
- Splitting that leaves a piece over the bed or a thin sliver of a piece.

## Constraints

- All fits and walls from the profile (`printer.toml` through `cadlib`), except the Gridfinity
  standard's own sizes and clearances: those stay as the standard says so other people's parts fit.
- Dimensions from kennetek/gridfinity-rebuilt-openscad (MIT): source and licence in the module
  docstring and in README "Licence". Read the numbers from its source, not from memory. The
  project's offline rule is for scripts: the builder may read the source on the web while writing
  the module, and the module itself never goes online.
- Bed: P2S 256 × 256 minus `bed_margin_mm` (5) per side = 246 mm, so a piece has at most 5 × 5 cells
  (6 cells are 252 mm). The limit is computed from the profile, not hard-coded.
- Magnet pockets only through `cadlib.magnets.pocket`. Lettering only through `cadlib.text.label`.
- The owner's drawer parts are local in `parts/` and never committed. Only `cadlib/gridfinity.py`,
  tests and docs are committed.

## Approaches considered

1. **Thin plain base with a filler rim, pieces laid side by side (chosen).** Quick and cheap to print,
   the drawer walls keep the pieces together. My recommendation, the owner confirms it with this doc.
2. **Pieces with interlocking edges.** The base comes out in one piece, but adds geometry and a fit to
   calibrate, with little gain inside a walled drawer.
3. **Magnet or screw base.** Holding bins down is not needed. Magnet pockets stay an option in the
   module (cheap, already have `cadlib.magnets`), screws are dropped for now.

## Design

### Baseplate

- `baseplate_layout(inside_x, inside_y, p, align=...)`: cells per axis are the most that leave a
  gap of at least 2 × `p.slide_fit_mm` to the walls plus `p.gridfinity_joint_mm` per joint between
  pieces on that axis (printed pieces come out slightly over size, the joints add up). The remainder
  goes into a solid rim. If the cells do not fit, the layout drops one cell and widens the rim: the
  cells are never trimmed below the standard size (my call). `gridfinity_joint_mm` is a new
  `[tolerances]` key, starting value 0.1, refined after the first real base is printed. Rim split evenly
  between both sides by default, or all to one side (`align`: centre, or a side such as front).
  A rim narrower than `p.min_wall_mm` is not made: that space is left as gap.
- The base is the standard open-frame plate profile (no floor), the rim is solid at the same height.
- `split(layout, p)`: pieces of at most N × N cells, N from the bed. Prefer equal pieces (12 → 4+4+4,
  7 → 4+3), never a 1-cell strip unless the axis has fewer cells than that. The rim goes with the edge
  pieces and its width counts toward the bed check.
- Optional magnet pockets in the plate cells (standard positions), off by default.

### Delivering the pieces

A drawer base is one part folder whose model returns several pieces. Today `build` writes one body
per part. The builder adds a way for a model to return a list of pieces and have `build` write a
3MF with one plate per piece (reusing what `kit` uses), with identical pieces built once and counted.
Each piece passes the usual checks. How exactly is the builder's call.

### Bins

- `bin(cells_x, cells_y, units_h, p, ...)`: standard bin base per cell, outer 41.5 per cell minus
  standard clearance, height in 7 mm units, standard stacking lip on top (optional).
- Walls at least `p.min_wall_mm`, floor at least the standard base height plus one wall.
- Compartments: `divisions_x`, `divisions_y`, or a list of compartment widths. This is the "grid of
  cups in a given compartment" generator that later inserts build on. Nothing is known yet about
  those inserts, so this API may change in a later phase (my call).
- Label shelf on the back wall of each compartment row, optional text through `label()`.
- Tool insert: a solid bin with pockets cut from the top: rectangle, circle, slot, each with its own
  depth and a finger notch option. Sizes come from the owner (caliper) plus `p.slide_fit_mm`.
- Optional magnet pockets in the bin base (standard positions).
- `_validate` style errors: compartment narrower than a wall, pocket wider than the bin, pocket
  deeper than the floor allows.

### Tests

Pitch and cell count from inside sizes (including 525 × 296 → 12 × 7, rim 21 / 0, and a narrower
width falling back to 6 cells with a wide rim), lip and base
profile heights against the standard numbers, magnet pocket positions, 6 × 6 and 12 × 7 split into
pieces that pass the bed check, a 1 × 1 bin and a 2 × 2 plate build green.

### Docs

README (module, Licence), CLAUDE.md rule (Gridfinity only through `cadlib.gridfinity`), the cad skill,
roadmap status.

## Left to the builder

- The multi-piece build mechanism (above).
- Exact standard numbers from kennetek's source, and the bin's inner fillet radius.
- Default rim alignment, file names, function signatures.
