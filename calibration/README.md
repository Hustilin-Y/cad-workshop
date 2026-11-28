# Tolerance calibration

The `tolerance-gauge` sample (148 × 58 × 11 mm, about 21 cm³, two bodies on the bed):

- **Plate.** A row of 11 holes `8 + c` in diameter at the top, a row of 11 pins `8 − c` at the bottom. Between the rows the values of `c` are labelled: `.00`, `.05` … `.50` mm. The clearance is on the diameter.
- **Key.** A pin of exactly 8 mm at one end, a ring with a hole of exactly 8 mm at the other.

Build: `uv run cad.py build calibration`, files in `calibration/out/`.

## Printing

- With the same plastic, nozzle and profile you'll print parts with. Each plastic has its own tolerances.
- Lay it as it is, flat side on the bed. No supports needed.
- Don't finish it after printing: the point is the tolerances straight off the printer.

## Reading the result

1. **Holes.** Push the key's pin into each hole of the plate.
2. **Pins.** Slide the key's ring onto each pin of the plate.

For each row find three values:

| Fit | Sign | Key in `printer.toml` |
|---|---|---|
| Press fit | goes in with force, holds by itself, no play | `press_fit_mm` |
| Slide fit | moves freely by hand but with almost no play | `slide_fit_mm` |
| For a screw/shaft | goes in freely with noticeable play, never sticks | `hole_clearance_mm` |

Tell me the result, for example "holes: press .10, slide .25, free .35; pins: press .05, slide .20". I'll put the values into `printer.toml`. If holes and pins differ a lot, I'll give them separate tolerances.

The first layers at the holes are usually squeezed narrower (the elephant's foot). If it's tight there and free higher up, go by the top of the hole and mention it.

## Coupons for one fit

`uv run cad.py coupon <feature>` makes a small labelled series of a single fit (holes for a rod, press or slide pins, magnet pockets, thread rings), see [coupons/README.md](coupons/README.md). The build ends with how to read it and the `printer.toml` key the value goes to.

## openGrid test pieces

`uv run cad.py build calibration/opengrid`: a back with a Multiconnect slot (snap-in detent) and a tile on an openGrid snap, about 10 g, printed as they lie. Lower the slot piece onto an official Multiconnect snap in a board, open end first: it should click into the detent and not lift off. Push the tile into a full board cell: it should click in and need a firm pull to come out. These sizes are the openGrid standard and are not tuned in `printer.toml`. If a piece is too tight or loose, check the tolerance gauge above first, then tell me what you felt.

openGrid/Multiconnect interface: dimensions from [openGrid](https://makerworld.com/en/models/1179191-opengrid-wall-desk-mounting-framework-ecosystem) by David D, CC BY.
