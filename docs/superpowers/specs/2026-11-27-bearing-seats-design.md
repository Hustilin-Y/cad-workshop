# Bearing seats: housings and shafts for bought ball bearings

Date: 2026-11-27. Status: draft for the owner, not started.

## Intent

The owner plans parts built around bought ball bearings: wheels, pulleys, rotating mounts,
turntables, hinges. Today every such part would draw its bearing pocket by hand with a guessed
diameter, and the profile has no fit that describes a metal ring pressed into plastic. This
document specifies `cadlib.bearings`: a catalogue of standard bearings, tools that cut a seat for
the outer ring and make a pin or spacer for the inner ring, the print-specific corrections that make
those fits repeatable, a calibration coupon, checks and tests.

Printed bearings (print-in-place races) are out of scope: a bought 608 is cheaper and lasts longer.

## Goals

- A catalogue of common deep groove, thin section, flanged and thrust bearings with sources.
- A seat tool for the outer ring in three fits: press (smooth), ribs (crush ribs), slip (glued or
  retained), with a shoulder, an optional retaining lip or lid, and a lead-in chamfer.
- Tools for the inner ring side: a printed pin, a spacer sleeve for a bolt, a relief that keeps the
  housing off the inner ring and the seals.
- Print-specific corrections built into the tools (see "Print-specific corrections"), so a model
  author gets them without thinking about them.
- New fit values in `printer.toml`, filled from a calibration coupon printed with the owner's real
  bearings.
- Checks a model calls from `_validate(p)`: seat axis vs print orientation, wall around the seat,
  clamping only the inner ring.
- One committed example part and tests.

## Non-goals

- Printed bearings, bushings as a bearing replacement, lubrication, life or load rating
  calculations, FEA.
- Lazy susan turntable rings and other non-standard bearings in the catalogue: those are built from
  caliper measurements through the same tools with explicit sizes.
- Retaining ring grooves (DIN 471/472) in plastic: the groove edge crushes under the ring. Use a lid
  or a lip instead.

## Evaluation: does a seat need print-specific corrections?

Yes. A metal ring has no give, so errors of 0.05 mm decide between "falls out", "holds" and
"cracks the wall". Ranked by effect on the fit:

| # | Effect | Size | What the module does |
|---|---|---|---|
| 1 | Printed holes come out smaller than drawn (perimeter squeeze, corner rounding of the outer wall line). Grows with smaller diameters and differs per plastic. | 0.05–0.2 mm on Ø | Fit values come from a coupon with the real bearing, not from a rule. `clearance_add_mm` of the plastic still applies. |
| 2 | Export tessellation turns a circle into an inscribed polygon. With `LINEAR_TOL_MM = 0.02` and `ANGULAR_TOL_RAD = 0.1` a Ø22 hole loses up to ~0.03 mm on Ø at the flats, and the loss depends on export settings rather than on the model. | up to 0.03–0.04 mm | The seat is drawn as an explicit polygon whose inscribed circle equals the target Ø (vertices on the circumscribed circle). The fit is then independent of export settings and the tests measure exactly what prints. |
| 3 | Seat axis lying horizontal in the print: the top of the hole is bridged, sags and is no longer round. A teardrop fixes printability but ruins the fit. | 0.1–0.4 mm | Not corrected: a check fails the build (`require_vertical`) unless the model passes `allow_horizontal=True` with a reason. The fix is to reorient or split the part. |
| 4 | Elephant's foot when the seat opens onto the bed: the first layers bulge into the hole. | 0.1–0.3 mm locally | A 45° lead-in chamfer, sized from `p.layer_mm` (at least 2 layers), on the bed side. The same chamfer is the press-in lead on the open side. |
| 5 | Seat depth not a multiple of the layer: the shoulder lands mid-layer, so the ring sits proud or sunk by a partial layer. | up to 1 layer | Depth is rounded up to a multiple of `p.layer_mm`, plus one layer of axial play unless `axial="flush"`. |
| 6 | Shoulder that faces down in the print (seat opens toward the bed, shoulder is a ceiling) is a flat overhang ring. | droop, rough land | The shoulder is a 45° cone instead of a flat step when `opening="bed"`. The cone still stops the outer ring because it starts at `D_a max`. |
| 7 | Crush ribs narrower than a line width are dropped by the slicer, and ribs taller than half a line deform into blobs. | rib missing or blob | Rib width ≥ 1.2 × `p.nozzle_mm` at the tip, triangular or trapezoid section, radial height = interference (validated ≤ 0.5 × nozzle). Rib tops chamfered 45° as a lead-in. |
| 8 | Z seam placed inside the seat makes a bump at one angle. | ~0.05–0.1 mm | Not fixable from the model. With ribs the bump hides between ribs or on one. Documented, and an open question for a `PRINT_HINTS` seam key (see "Open questions"). |
| 9 | Creep: a press fit in PLA relaxes over weeks, faster in heat. PETG relaxes less but is softer. | loose ring later | Ribs plus a mechanical stop (lip or lid) for anything loaded or warm. A WARN when `fit="press"` is used without retention on PLA. |
| 10 | Hoop stress: a thin wall around a press fit splits along the layer seam. | cracked housing | Wall check: radial wall ≥ max(`p.min_wall_mm` × 2, 0.15 × D). Below it a FAIL with the minimum outer size in the message. |

Not worth doing: per-printer hole compensation formulas, slicer arc fitting tweaks, polyholes with
few sides (Nophead's trick predates slicers that keep many-sided holes round).

## Catalogue

`cadlib/bearings.py`, a frozen dataclass per size, keyed by designation:

```python
@dataclass(frozen=True)
class Bearing:
    name: str             # "608"
    kind: str             # "deep_groove" | "thin" | "flanged" | "thrust"
    d: float              # bore
    D: float              # outside diameter
    B: float              # width
    r_min: float          # ring chamfer, min (r_s min)
    da_min: float         # shaft shoulder Ø, min (catalogue d_a min)
    Da_max: float         # housing shoulder Ø, max (catalogue D_a max)
    flange_d: float | None = None   # flanged only
    flange_b: float | None = None
```

Initial sizes (d × D × B, mm):

| Group | Sizes |
|---|---|
| Miniature and 600 | 623 (3×10×4), 624 (4×13×5), 625 (5×16×5), 626 (6×19×6), 608 (8×22×7), 688 (8×16×5) |
| 6000 / 6200 | 6000 (10×26×8), 6001 (12×28×8), 6002 (15×32×9), 6200 (10×30×9), 6201 (12×32×10), 6202 (15×35×11) |
| Thin section | 6700 (10×15×4), 6800 (10×19×5), 6801 (12×21×5), 6802 (15×24×5), 6805 (25×37×7) |
| Flanged | F623, F625, F608, F688: flange sizes from a maker datasheet, verified with a caliper before the entry is added |
| Thrust | 51100 (10×24×9), 51101 (12×26×9), 51102 (15×28×9) |

Rules for the table:
- `r_min`, `da_min`, `Da_max` come from one maker's published table (SKF or NSK), named in a comment
  with the table it came from, the same way `fasteners.METRIC` names ISO standards.
- An entry without a verified value is not added. No guessed numbers.
- `bearing(name)` raises a clear error listing the known sizes. `custom(d, D, B, ...)` builds a
  `Bearing` from caliper measurements for anything not in the table.
- Thrust bearings: the two washers differ (shaft washer bore d, housing washer bore larger). The
  entry carries both bores. Seat tools treat the housing washer like an outer ring.

## Fit values

New keys in `[tolerances]` of `printer.toml`, all on the diameter, added to the nominal ring size.
Negative means smaller than the ring. Values below are starting guesses until the coupon is printed:

```toml
bearing_press_mm = 0.10        # smooth seat for a press fit: printed holes shrink, so drawn larger than D
bearing_slip_mm = 0.30         # smooth bore of a ribbed or retained seat: the ring slides in by hand
bearing_rib_mm = 0.25          # crush rib interference on the radius: rib tips at (D + slip)/2 - rib
bearing_pin_press_mm = -0.05   # printed pin into the inner ring (pins print larger than drawn)
bearing_pin_slip_mm = -0.20
```

- `Profile` gains the same fields. `clearance_add_mm` of the plastic is added to the smooth values
  the same way as for the other fits. The rib interference is not changed by the plastic.
- The current `press_fit_mm` (8 mm plastic in plastic) is not reused: different diameter, metal ring.
- If coupon results for small and large bearings differ by more than 0.05 mm, a second stage adds a
  per-diameter table (`[tolerances.bearing_by_d]`, keys as diameter bands). Not built until the data
  shows it is needed.

## API

Conventions follow `cadlib.fasteners`: a seat tool stands with its top at Z = 0 and goes down into
−Z (the side the bearing enters from), and it is subtracted from the body. Solids that are added
(pins, spacers) stand on Z = 0 and go up.

```python
from cadlib import bearings as b

b.bearing("608") -> Bearing
b.custom(d=8, D=22, B=7, r_min=0.3) -> Bearing           # measured; da/Da from a rule if not given

b.seat(brg, p, *,
       fit="ribs",            # "press" | "ribs" | "slip"
       depth=None,            # default B rounded up to a layer + one layer of play
       through=False,         # through bore below the shoulder for the shaft
       shoulder=True,         # stop for the outer ring at Da_max
       opening="top",         # "top": opens away from the bed, "bed": opens onto the bed
       retention=None,        # None | "lip" | "lid"
       ribs=None,             # rib count, default 3 for D < 13, 4 for D < 25, 6 above
       axial="play") -> Part  # "play" | "flush"

b.lid_tool(brg, p, screws="M3", n=3) -> (Part, Part)     # (cut for the housing, solid of the lid)
b.pin(brg, p, length, fit="ribs") -> Part                # printed pin for the inner ring
b.spacer(brg, p, length, bolt="M8") -> Part              # sleeve that bears on the inner ring only
b.ring_relief(brg, p, depth=None) -> Part                # annular recess so a face clears the
                                                         # outer ring and seals, touches only da_min..d
b.pair(brg, p, gap, **seat_kwargs) -> Part               # two seats back to back with a spacer land

b.require_vertical(axis, print_down)                     # FAIL if the seat axis is not along the print Z
b.require_wall(brg, outer_d_or_min_dist, p)              # FAIL below the hoop-stress wall
b.require_inner_clamp(stack)                             # FAIL if a clamp stack touches the outer ring
```

Notes:
- The lip (`retention="lip"`): a ring 0.3 mm radial (validated ≥ 0.5 × nozzle, ≤ 0.6 × nozzle),
  45° on both sides so it prints as an overhang of at most 45° and the ring snaps past it.
- The lid: a printed washer with clearance holes through `fasteners`, inserts or self-tap pilots in
  the housing, the lid pressing on the outer ring only (inner diameter ≥ `Da_max`).
- `pin` below Ø5 prints weak and shears at the layer: below `d = 5` `pin` raises an error that tells
  the author to use a metal shaft (a bolt or a dowel) with `spacer`.
- Every tool takes the profile `p` and reads no numbers of its own for tolerances.

## Calibration coupon

`calibration/bearing-seats/`, a model in the same style as `calibration/fit-test`:

- Parameter `BEARINGS = ["608"]`: the sizes the owner has. One block per size.
- Row 1, smooth seats: `D + c` for `c` from 0.00 to 0.30 step 0.05, labelled through `cadlib.text`.
- Row 2, ribbed seats: slip bore `D + 0.30`, rib interference from 0.10 to 0.35 step 0.05.
- Row 3, pins for the inner ring: `d + c` for `c` from −0.25 to 0.05 step 0.05.
- Seats open upward, blind with a 2 mm floor and a Ø6 push-out hole, so the bearing can be pressed
  out with a screwdriver and reused.
- Size kept under ~80 × 60 mm per bearing size and ~20 g of PLA.

README in the folder: how to press the bearing in (by hand, then a vice with soft jaws), what each
fit feels like (press: needs a vice, holds by itself; ribs: firm hand push, no play; slip: slides in,
falls out turned over), and which value goes into which key. Results are recorded per plastic the
same way as the existing calibration: the plastic's values go into `clearance_add_mm` if they differ.

The coupon is committed (it is the workshop's own model). Its `out/` stays ignored.

## Checks and reporting

- `_validate(p)` in a model calls `require_vertical`, `require_wall`, and for stacks
  `require_inner_clamp`. Errors name the bearing, the value and the minimum that would pass.
- `seat(..., fit="press", retention=None)` on PLA prints a WARN line through the build report
  (creep). Mechanism: the tool records a note in a module-level list the build reads, like the style
  log planned in the style module. If that log lands first, use it instead of a second mechanism.
- The build report gains one line per seat: bearing, fit, drawn Ø, depth. It makes a later
  "too tight" edit a one-line parameter change.

## Example part

`parts/example-bearing-hub/` (committed): a pillow block for a 608 on an M8 bolt.
- Base with two M5 clearance holes through `fasteners`.
- A ribbed 608 seat opening upward, a lip, a through bore for the bolt.
- A `spacer` and a `ring_relief` so only the inner ring is clamped.
- `kit.py` lays out the block and the spacer on one plate.
- README in the usual form: key sizes with sources, printing (PETG suggested for anything that warms
  or carries load, why), history.

## Tests

`tests/test_bearings.py`, using `section_loops` as `test_fasteners.py` does:

1. Every catalogue entry: `d < da_min < Da_max < D`, `B > 0`, a source comment present (the test
   reads the module text).
2. `seat` smooth: the inscribed Ø of the section polygon equals `D + p.bearing_press_mm` to 0.005.
3. `seat` ribs: rib count, rib tip Ø equals `D + slip - 2 × rib` to 0.01, rib width at the tip
   ≥ 1.2 × nozzle.
4. Depth is a multiple of `p.layer_mm`, plus one layer for `axial="play"`.
5. `opening="bed"` gives a cone shoulder and a lead-in chamfer at least 2 layers high.
6. The lip's overhang is ≤ 45° (run `overhang_fraction` on a block minus the tool).
7. The tool's top is at Z = 0 and it sticks out by `EPS`, like the fastener tools.
8. `pin` with d < 5 raises. `bearing("999")` raises with the list of sizes.
9. `require_vertical` fails for a seat along X with `PRINT_DOWN = "-z"`, passes with `"-x"`.
10. `require_wall` fails at the threshold minus 0.1 and passes at the threshold.
11. Changing `bearing_press_mm` in a temporary `printer.toml` changes the drawn Ø (the profile is
    really read).
12. The coupon and the example part build with no FAIL (`test_parts.py` picks them up).
13. `test_no_network` stays green: the module reads nothing from outside.

## Docs and rules

- `CLAUDE.md`: "Seats and pins for bought bearings only through `cadlib.bearings`, fits from the
  profile, never drawn by hand. Ask which bearing (marking on the shield) and measure it if it has
  no marking."
- Skill cheat sheet: one import line and one example call.
- `README.md`: a row in Layout, a short "Bearing seats" section, the coupon in "Tolerances and
  calibration".
- After the change: `uv run pytest` and `uv run cad.py build --all`.

## Order of work

1. Catalogue with sources, `Profile` fields and `printer.toml` keys with the starting guesses. Tests 1, 8, 11.
2. `seat` with the polygon bore, depth rounding, chamfers, shoulder (flat and cone), ribs, lip.
   Tests 2–7.
3. Calibration coupon and its README. The owner prints it with their real bearings, the values
   go into `printer.toml`. **Stop here until the owner reports the result.**
4. `pin`, `spacer`, `ring_relief`, `pair`, `lid_tool`, the `require_*` checks. Tests 9, 10.
5. Example part, report line, creep WARN, docs, full rebuild.

Effort: steps 1–3 about 2 days, 4–5 about 2 days.

## Open questions for the owner

1. Which bearings are on hand or planned? They set the first catalogue entries and the coupon.
2. Default plastic for bearing parts: PETG (less creep in warmth) or PLA (more precise)? The coupon
   should be printed in the one that will be used.
3. bambu-mcp: add `PRINT_HINTS` keys for `xy_hole_compensation` (forced 0 for seats) and
   `seam` (back or aligned)? That changes the manifest schema and needs the bambu-mcp side too.

## Appendix: other ideas from the same review (backlog, not specified here)

Recorded so they are not lost. Each needs its own design document before work starts.

| Idea | For | Effort |
|---|---|---|
| Service temperature check: `SERVICE_TEMP_C` or an environment preset in a model, `hdt_c` per plastic, FAIL if the plastic is below. Add TPU. | car interior (dash 70–90 °C in sun) | S |
| Generic fit coupon generator `cad.py coupon <feature>`: stepped samples of any fit with labels. Reuses the bearing coupon's code. | all | M |
| Shaft interfaces `cadlib.shafts`: D-shaft, knurled spline, square, with profile clearances and a coupon. | knobs, buttons | M |
| Measurement intake: a `MEASURED` table (value, tool, ±) at the top of `model.py` and a checklist for a broken original. | reverse-engineering car parts | S |
| SVG import to an outline for icons on buttons. | car buttons | S–M |
| Snap-fit cantilever generator with a strain check per plastic. | clips, covers, brackets | M |
| Hose barb generator, O-ring groove tool, seal test coupon. | hose adapters | M |
| Pipe thread G (BSPP, 55° Whitworth) as a profile option in `threads.py`. NPT not planned. | hose adapters | M |
| Teardrop horizontal channels and bent channels with a minimum bend radius. | hose adapters | M |
| Beam-formula strength estimate from declared `LOADS`, and a WARN when bending puts layers in tension. Before any FEA. | brackets | S–M |
| `cadlib.assembly`: placements, interference and minimum clearance through manifold, motion steps. Generalises the check in `lamp-arm`. | hinges, turntables, buttons in housings | M |
| Part families from a variants table, and a generated parts catalogue (committed parts only). | all | S |

Not planned: statistical tolerance stacks, printed pipe threads for pressure, coolant or oil hoses
in an engine bay in PLA, PETG or ASA, photogrammetry for small parts.
