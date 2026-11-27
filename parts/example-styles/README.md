# example-styles

The cantilever bracket archetype of `cadlib.style` in one of five dialects: a 6 mm wall plate with two M4 keyhole slots, a 120 mm arm with an eye for an M4 at the tip, and the bracing between them. It shows how the style toolkit composes a whole part, and it is the reference for tuning the dialects.

```
uv run cad.py build parts/example-styles --set STYLE='gaudi'
```

## What and why

| Dialect | Bracing | Finish |
|---|---|---|
| gothic | a flying buttress: one pointed-arch strut springing level from the plate's foot and meeting the arm at a point, nervure ribs in relief along its intrados and along the arm's lower edge | sharp edges with a chamfer |
| gaudi | a catenary brace of varying width from the plate's foot to the drooping arm | large soft roundings |
| hitech | a truss fanning from the plate's foot to round nodes under the arm, a row of triangle pockets along the arm's side like a lattice girder | crisp thin members, small roundings |
| parametric | a web under a curved underside, its whole field cut into a hex lattice whose bars thicken towards the plate-arm corner, where the bending peaks | smooth roundings |
| biomech | a sci-fi biomechanical look: four thin tendons fanning from the plate to the arm with open gaps between them, a segmented spine of relief vertebrae along the arm, shrinking towards the tip | soft roundings |

- Every motif is structural: the strut, brace, truss, web and tendons carry the load, the lattice is densest where the bending peaks.
- Mounting: keyhole slots in the plate. Set two M4 screws in the wall 65.2 mm apart (centre to centre, the same for every dialect), leave the underside of each head 2.5 mm off the wall (the plate's back layer is 2.4 mm), put the bracket's round entries over the heads and slide it down 7.6 mm. The heads ride in a channel inside the plate, so nothing in front of the plate has to be opened up for a driver.
- The relief (gothic ribs, hitech pockets, biomech spine) is on the +Y face, which faces up when printed. The preview's isometric camera looks at the -Y face; the top and right views show the relief.
- The elevation is drawn in 2D and extruded, so the part stays B-rep and exports STEP.
- `PRINT_DOWN = "-y"`: lying on its side every opening is a vertical through-cut and the load acts along the layers, the strong direction. The archetype can also rebuild for `"-x"` (standing on the wall plate): voids then get 45° roofs, holes 45° caps.
- The plate's back (x = -`PLATE_T`) goes against the wall. The load hook for later stages is a 20 N pull straight down at the tip hole.

## Key sizes

| Parameter | Value | Source |
|---|---|---|
| Reach × height × depth | 120 × 90 × 20 mm | example |
| Arm at the plate | 10 mm, tapering by the dialect | `DIALECTS[...].taper` |
| Plate | 6 mm | ≥ 2 × the 1.2 mm minimum wall |
| Keyhole slot | 4.5 mm wide = 4.3 (ISO 273 fine) + 0.2 clearance | `printer.toml` |
| Keyhole entry and channel | Ø7.6 = M4 head 7.0 (ISO 4762) + 2 × 0.3 slide fit, 4.3 deep behind a 2.4 mm back layer | `printer.toml` |
| Keep-out | the keyhole's outline grown by the 1.2 mm minimum wall | lattices stay clear |

## History

- 2026-11-27: created with the style module (cantilever archetype, four dialects).
- 2026-11-27: owner review: gothic became a flying buttress, parametric's hex field fills the web with visible grading, hitech's lattice moved to the arm's side as pockets, new biomech dialect, screws through keyhole slots instead of a bay in the web.
