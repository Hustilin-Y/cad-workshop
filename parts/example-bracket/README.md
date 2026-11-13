# example-bracket

An L-shaped bracket: shelf and post 40 × 25 mm, 5 mm thick, one M4 hole in each. It is the example of a part "from scratch": every size is a parameter at the top of [model.py](model.py), and tolerances come from `printer.toml`.

## Key sizes

| Parameter | Value | Source |
|---|---|---|
| Shelf × post × width | 40 × 40 × 25 mm | example |
| Thickness | 5 mm | ≥ the 1.2 mm minimum wall for a 0.4 nozzle |
| Inner rounding | R6 | relieves the stress concentration in the corner |
| Outer rounding | R11 = R6 + thickness | the corner wall is 5 mm all round |
| M4 holes | Ø4.5 = 4.3 (ISO 273 fine) + 0.2 clearance | `printer.toml` |
| Chamfer at the holes' entry | 0.6 mm × 45° | removes the first-layer lip |

The holes sit in the middle of each leg's straight part. The shelf's screw enters from above, the post's screw from the shelf's side.

## Printing

- Plastic: PLA; for load or heat better PETG.
- Orientation (suggested): **on its side**, with the L profile on the bed. The layers then run along the bend, so the corner won't delaminate under load. The holes are horizontal in this orientation, and Ø4.5 bridges without supports.
- Printed as modelled (shelf down), the outer rounding at the bed is an overhang (5% of the area) and the corner's layers lie across the load. The corner is noticeably weaker.
- No supports needed.

## History

- 2026-11-03: created as the reference example (stage 3 of the spec).
