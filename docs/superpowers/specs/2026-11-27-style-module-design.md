# Style module: architectural form language for printed parts

Date: 2026-11-27. Status: approved by the owner on 2026-11-27.

## Intent

Parts built in this workshop are correct but look like engineering drawings: boxes, straight
struts of constant section, edge fillets as the only finish. The owner wants parts that are
beautiful in their own right and, where it fits, read like elegant architecture.

This document covers **part 1 of 4** of a larger upgrade:

1. **Style module and hex grid** (this document).
2. Load-aware print orientation: `orient.py` takes a load vector and penalises tension across layers.
3. FEA check and parameter fitting: scikit-fem stress check, safety factor in the build report,
   template parameters tuned to a target safety factor at minimum plastic.
4. Coarse topology optimisation as an advisor (PyTopo3D, PC only): shows load paths to pick
   a template. It never ships geometry.

Parts 2–4 get their own design documents. Part 1 must leave clean hooks for them (see "Hooks for
parts 2–4").

## Goals

- A `cadlib.style` package with four dialects chosen by the owner:
  - **gothic**: pointed arches, tracery rosettes, ribs (nervures), sharp edges with a chamfer.
  - **gaudi**: catenary arches, oval openings, curved beams of varying section, large soft radii.
  - **hitech**: triangular grid (diagrid), open trusses with visible nodes, crisp thin members.
  - **parametric**: hex grid with a density gradient, spline-tapered forms, smooth transitions.
- A shared **hex grid** tool usable by every dialect: uniform or graded by a scalar field.
  Part 1 grades by a simple analytic field (distance from a point, line or face). Part 3 will
  pass an FEA stress field through the same interface.
- **Toolkit first (approach A)**: functions a model composes, for example `arch_opening`, `rib`,
  `lattice`, `taper_beam`, `catenary_beam`, `truss`. They work on any part: brackets, boxes,
  hangers.
- **Archetypes on top (approach B)**: 2 generators of whole parts built from the toolkit:
  - a cantilever bracket (wall plate + arm + bracing), the most common part in `parts/`;
  - a **hanger kit** (decided by the owner): a ceiling/wall mount bar, two arms and a cradle at
    the end of each arm, as separate printed pieces joined by dovetails with a snap detent,
    modelled on the `lamp-hanger` family. It is meant for long objects (the lamp is 470 mm), so
    every piece must fit the P2S bed (`p.usable_volume_mm`) and the generator splits the span
    accordingly. Inputs: the object's span between its ends, each end's profile (a rectangle or
    a trapezoid with sizes, or a 2D sketch), the drop from the mount to the object, the mount
    screws (through `cadlib.fasteners`). It returns named pieces, each with its own `PRINT_DOWN`,
    and the example writes a `kit.py` so `cad.py kit` lays them out on plates.
  The cantilever takes `style=` and its sizes and returns one solid ready for `build(p)`.
  The hanger kit takes `style=` and returns a dict of named solids.
- A generic dovetail joint with a detent in the toolkit (`joint_dovetail`), extracted from the
  approach in `parts/lamp-hanger/hanger.py`: neck, wide part, depth, stop wall, detent bump, all
  clearances from the profile (`p.slide_fit_mm`). The owner's `lamp-hanger` itself is not changed.
- Every template is printable by construction in its stated print orientation: no overhang
  steeper than `checks.OVERHANG_DEG` (45°), no wall or bridge thinner than `p.min_wall_mm`.
- Committed example parts: `parts/example-styles/` builds the cantilever archetype in all four
  dialects (one build per dialect via `--set STYLE=...`), and `parts/example-hanger-kit/` builds
  the hanger kit for a made-up 400 mm object, so the README and tests show them.

## Non-goals

- No load calculation, FEA or topology optimisation here (parts 3–4). Archetype sizes in part 1
  come from parameters and simple rules of thumb, documented in each function.
- No changes to `orient.py` (part 2).
- No restyling of the owner's local parts. They are not committed. The owner can restyle them later
  with the new tools.
- No new heavy dependencies. build123d, manifold3d, numpy and scipy are enough.

## Anti-goals (a failure even if it technically works)

- Decoration that weakens the part: an opening or lattice that cuts through a load path, a screw
  boss or a fastener face. Style tools must respect keep-out zones.
- Forms that need supports in the stated print orientation.
- Silent cosmetics: when a fillet, a lattice cell or an arch is dropped or shrunk, the build report
  must say so (today `finish.soften` drops edges silently).
- Builds that become slow: a styled bracket must still build in under ~30 s on the PC and fit the
  1400 MB cap on the workshop server (measure on a large hex lattice).
- Kitsch: ornament without structure. Every motif in a dialect is also a structural device
  (arch, rib, truss, graded lattice). Pure surface ornament is out of scope.

## Constraints

- Numbers come from `printer.toml` through the profile `p` (CLAUDE.md). Style constants that are
  proportions (arch rise ratio, taper ratio) are dimensionless and live in the dialect, not in
  `printer.toml`.
- Holes and fasteners only through `cadlib.fasteners`. Style tools take keep-out solids so that
  fastener bosses stay solid.
- The result stays B-rep, so STEP export keeps working. Lattices are cut in 2D before extrusion,
  which keeps OCCT fast enough. A mesh fallback is not planned unless the build budget fails.
- Print orientation: tools take the part's `PRINT_DOWN` direction (default: −Z in the file) to
  decide which arch is pointed up and which overhangs are allowed.
- Windows and Linux, `pathlib` only, no network.
- Public repository: only workshop code and the example part are committed.

## Approaches considered

1. **How calculation shapes form (decided across parts 1–4).**
   - *Calculation inside the style* (chosen): templates fix the form language, FEA tunes their
     parameters. Keeps B-rep, STEP, `--set` edits and printability. Roughly 10–30 % heavier than
     an optimum.
   - *Free organic topology optimisation* (deferred, see "Future"): lightest, but mesh-only,
     not editable by parameters, often unprintable thin members, and an unpredictable look.
   - Coarse topology optimisation is kept as an advisor in part 4.
2. **How style is applied (this part).**
   - *A. Toolkit*: functions any model composes. Works for every part type, beauty depends on
     composition.
   - *B. Archetypes*: whole-part generators. Beautiful out of the box, easiest to tune by FEA,
     but only for foreseen part types.
   - **Chosen: A as the base with 2 archetypes from B on top.**

## Owner review of the cantilever (2026-11-27)

- gaudi: good as built, keep.
- hitech: good, but the plate lattice is invisible. The tri lattice moves to the large side face
  (+Y, which faces up in print) as blind pockets or relief, where it is seen in use.
- gothic and parametric: "missed the point", rework both.
  - gothic becomes a **flying buttress**: the arm is carried by one pointed-arch strut springing
    from the plate, nervure ribs in relief along the arch and the arm edge, chamfered edges. No
    scattered small windows.
  - parametric: hex cells fill the whole web following its outline, and the grading is clearly
    visible (bars from `p.min_wall_mm` to about 4 × that, finest away from the load).
- New fifth dialect **biomech** (sci-fi biomechanical look): several thin curved "tendon" strands
  from the plate to the arm that fan out and merge smoothly at their ends, with open gaps between
  them, plus a segmented "spine" of vertebra-like relief ribs along the arm, shrinking toward the
  tip. Code and docs name it `biomech` and describe it in generic terms (no film or artist names).
- Screw access: the large bay next to the plate is replaced by a minimal access that keeps the
  web intact (keyhole slots in the plate, or narrow slots open on the +Y face).

## Decided by the owner

- Dialects: gothic, gaudi, hitech, parametric, and (added after review) biomech.
- Hex grid is a must, available to all dialects, gradable.
- Toolkit plus archetypes.
- The hanger archetype is a kit of pieces with dovetail joints, not a single body.
- Coarse topology optimisation only as an advisor (part 4). Free organic form deferred.

## Calls made by Claude (owner may override)

- (Revised while planning.) Any opening in a wall that stands upright in print gets its roof
  clipped: the part of the roof flatter than 45° is replaced by two 45° tangent lines meeting in a
  point. A catenary or round opening thus gets a small pointed cap at the apex, a circle becomes
  a teardrop. Gothic pointed arches of equilateral rise or taller need no clipping.
- Gothic arches are oriented with the point up in the print orientation.
- Hex grid default cell: across-flats ≥ 4 × `p.min_wall_mm`, bars ≥ `p.min_wall_mm`.
  Graded grids vary the bar width, not the cell pitch, so cells stay aligned and printable.
- (Revised while planning.) Hex cells in a wall that stands upright in print are flat-top: their
  sides are 60° and the top edge is a short bridge, no longer than `max_bridge_mm` (new key in
  `printer.toml`, 10 mm). Pointy-top hexes have 30° roof edges and would need supports. In a wall
  that lies flat in print the orientation is free and pointy-top is the default look.
- (Added while planning.) Planar archetypes (cantilever, hanger arms) are built as a 2D elevation
  extruded to depth and print lying on that side by default. All openings and lattice cells are
  then vertical through-cuts with no overhangs, and the load acts in the layer plane, which is the
  strong direction. Styling is done in 2D, so everything stays B-rep and exports STEP.
- (Added while planning.) The cradle is part of each arm piece, as in `lamp-hanger`. The kit's
  pieces are the mount, arm A, arm B, plus arm segments when an arm does not fit the bed.
- The strict overhang check in the tests exempts horizontal down-facing patches no wider than
  `max_bridge_mm` (bridges), and the area below 1 mm² (tessellation noise).
- The first two archetypes: cantilever bracket and hanger.
- Style selection in a model: `STYLE = "gothic"` parameter at the top of `model.py`, overridable
  with `--set STYLE=...`.
- Dropped or shrunk cosmetics are counted and listed in the build report under a new "Style"
  line.
- "Printable by construction" is enforced by **strict checks in the style tests only**: zero
  faces steeper than 45° outside bed chamfers in the stated print orientation, and a mesh-based
  minimum wall/bar thickness ≥ `p.min_wall_mm`. The build pipeline's `checks.py` is not made
  stricter in part 1, so the owner's local parts and `build --all` are unaffected.
- Print orientation of an archetype: each archetype has one default orientation and declares
  a small set of allowed alternatives it can rebuild for (`allowed_print_down`). Part 2 picks
  among those. Toolkit functions take `print_down` and adapt (arch point, hex vertex up).
- Owner review stop: after the cantilever archetype exists in all four dialects, the work pauses
  for the owner to look at them (PNG plus OCP Viewer) and adjust defaults before the second
  archetype is built.

## Hooks for parts 2–4

- Archetypes declare their supports and load points (`supports`, `loads` as faces/points plus a
  direction), even though part 1 does not use them. Part 2 reads the load vector, part 3 runs FEA.
- Every archetype exposes its tunable parameters with bounds (a small dataclass), so part 3 can
  search them.
- The lattice grading takes any callable `field(x, y, z) -> 0..1`, so an FEA stress field plugs
  in without changing the lattice code.

## Left to the builder

- Module layout inside `cadlib/style/` and the exact function signatures.
- Which operations use build123d and which fall back to manifold3d.
- Test design. At minimum: each dialect's tools on simple bodies give a single valid solid, the
  archetypes pass the existing build checks (manifold, overhangs, min wall) in their print
  orientation, the example part builds in all four dialects, timing and memory stay in budget.
- Preview: the PNG stays as is in part 1. A nicer render is a separate idea, not in this scope.

## Future (not planned)

- **Free organic topology optimisation** as an optional mode for weight-critical parts:
  topology optimisation sets the shape, then marching cubes, smoothing and a re-check. Deferred
  because it is mesh-only, not parametric, prone to thin members and overhangs, needs minutes to
  hours and gigabytes of RAM on the PC, and its look is unpredictable.
- A nicer preview render (soft light, ambient occlusion, 3/4 hero view) to judge beauty.
- More archetypes (box, lamp arm, stand) once the first two prove the toolkit.

## Owner review, round 2 (2026-11-27)

- biomech as built (tendons plus vertebra ribs) "is not organic at all, the vertebrae mean nothing".
  It is replaced by an **organic cell lattice**: like the hex lattice, but the cells are irregular,
  Voronoi-like, with rounded tendon-like bars that thicken and blend smoothly at the junctions, and
  cell sizes that vary across the web (graded by a field, plus controlled randomness from a fixed
  seed so builds are reproducible). The vertebra spine is dropped.
- The organic lattice is a new lattice kind in `cadlib.style.lattice`, usable by any dialect, not
  only by biomech. Cells stay convex so roof clipping works when the web stands upright in print.
- The strict printability check must require a "bridge" patch to be anchored on two opposite
  sides. A one-side-anchored horizontal patch is an overhang (cantilever), not a bridge.
- gothic (owner, round 2): keep it and make it a true pointed arch. The buttress strut is a real
  pointed (ogival) arch: two arcs meeting in a visible point under the arm, not a smooth quarter
  circle. Strengthen the gothic read with a pinnacle (finial) at the arm tip, wider nervure ribs,
  and optionally a trefoil or quatrefoil cut in the spandrel. It must read differently from gaudi
  at a glance.
