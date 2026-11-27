# example-styles

The cantilever bracket archetype of `cadlib.style` in one of four dialects: a 6 mm wall plate with two M4 screws, a 120 mm arm with an eye for an M4 at the tip, and the bracing between them. It shows how the style toolkit composes a whole part, and it is the reference for tuning the dialects.

```
uv run cad.py build parts/example-styles --set STYLE='gaudi'
```

## What and why

| Dialect | Bracing | Finish |
|---|---|---|
| gothic | solid web with a pointed-arch window at the plate, a second pointed arch in the spandrel, a hood-mould rib round the window | sharp edges with a chamfer |
| gaudi | a catenary brace of varying width from the plate's foot to the drooping arm | large soft roundings |
| hitech | a truss fanning from the plate's foot to nodes under the arm, triangle lattice through the plate | crisp thin members, small roundings |
| parametric | a web under a curved lower chord, filled with a hex lattice graded from the plate-arm corner | smooth roundings |

- Every motif is structural: the window and the voids leave the screw heads free on the plate's face (reachable with a stubby or angled driver), the brace, truss and chord carry the load, the lattice is densest where the bending peaks.
- The elevation is drawn in 2D and extruded, so the part stays B-rep and exports STEP.
- `PRINT_DOWN = "-y"`: lying on its side every opening is a vertical through-cut and the load acts along the layers, the strong direction. The archetype can also rebuild for `"-x"` (standing on the wall plate): openings then point up and void roofs are capped at 45°.
- The plate's back (x = -`PLATE_T`) goes against the wall. The load hook for later stages is a 20 N pull straight down at the tip hole.

## Key sizes

| Parameter | Value | Source |
|---|---|---|
| Reach × height × depth | 120 × 90 × 20 mm | example |
| Arm at the plate | 10 mm, tapering by the dialect | `DIALECTS[...].taper` |
| Plate | 6 mm | ≥ 2 × the 1.2 mm minimum wall |
| Screw holes | M4, Ø4.5 = 4.3 (ISO 273 fine) + 0.2 clearance | `printer.toml` |
| Keep-out round each screw | Ø9.3 = hole + 4 × min wall | lattices and openings stay clear |

## History

- 2026-11-27: created with the style module (cantilever archetype, four dialects).
