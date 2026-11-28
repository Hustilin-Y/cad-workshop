# openGrid and Multiconnect interface (roadmap phase 1)

Date: 2026-11-28. Status: approved by the owner (approach 1, both interfaces).

## Intent

The owner hangs things on openGrid boards. Any part made in the workshop should be able to carry,
on its back, either a Multiconnect slot (the part slides down onto a Multiconnect snap sitting in
the board) or an openGrid snap of its own (the part clips straight into a board cell). This is a
foundation module, not a part: tools in the style of `cadlib.fasteners`.

## Source and licence

- openGrid, "openGrid - Wall/Desk mounting framework/ecosystem" by David D,
  https://makerworld.com/en/models/1179191-opengrid-wall-desk-mounting-framework-ecosystem ,
  Creative Commons Attribution (CC BY). The Multiconnect slot geometry is taken from the
  "Multiconnect modeling files" in the same package.
- Approach (chosen): our own parametric build123d code with the dimensions measured from those
  files (sections through the official STEP), every number with the file it came from. The code is
  MIT. Attribution (author, title, link, licence, "dimensions derived from their modeling files")
  goes into the module docstring and `README.md` "Licence".
- The official files stay local. They are not committed (project rule). A test compares our
  geometry with them when they are on disk and is skipped otherwise.

Approaches considered: (2) loading the official STEP at build time: exact, but the public repo
would not build and the Bare Snap STEP is not closed (9 bodies). (3) committing their files: allowed
by CC BY but against the project rule. Both rejected.

## Measured geometry (mm)

Multiconnect slot (`Multiconnect modeling files/slot-negative.step`, `half-round-negative.step`,
`snap-in-slot-negative.step`, `slot-opening.step`), depth measured from the back face:
- neck: 15.3 wide, 0.438 deep, then 45° out to 20.3 wide at 2.938, straight to 4.15 deep.
- closed end: the same profile revolved, centre of the connector at the arc centre (R 10.15).
- detent ("snap-in"): the wide part narrows to 2 × 9.759 at 3.55 below the connector centre
  (toward the open end), running out at 0.76 and 8.76.
- entry flare at the open end: R 10.15 at the bottom of the slot to R 11.0 at the surface.
- the clearance to the connector (0.15 per side and in depth) is part of these sizes: they are the
  standard, not values from `printer.toml`, so parts fit official snaps.
- back thickness in the official examples: 6.4. Slot pitch: 28 (the grid).

openGrid snap (`Snap modeling files/openGrid Bare Snap.step`, `openGrid Bare Lite Snap.step`;
board from `openGrid/opengrid-2x2.step`):
- octagon 24.8 across flats, 45° corners with 4.818 legs, 6.8 high (Lite 3.4).
- four flex tabs, one per side: slit 0.6 wide, 12.4 long, from the wall side up to 6.2 (Lite 2.8),
  tab 0.7 thick, free top with a 0.4 gap under a 0.8 front plate.
- latch bump on each tab: 0.4 proud, z 3.4 to 5.4 with a flat at 3.971 to 4.829 (Lite 0.2 to 2.0).
- the remaining corner details are taken during implementation from the same sections.
- board bars: 3.0 wide at the faces, 1.6 in the middle (undercut the bumps latch into).

## API

The part's back face is Z = 0, the part lies below (−Z), the wall above (+Z), +Y is up on the wall.
Slots are subtracted (they go down into the part, like `cadlib.fasteners`), snaps are added (they
stand up toward the wall). A part is lowered onto a Multiconnect connector and hangs on the slot's
closed end, so the slot opens downward. (Corrected after review: an earlier draft had the open end
up, which would let the part slide off.)

```python
from cadlib import opengrid as og

og.PITCH                                    # 28.0
og.multiconnect_slot(length, *, detent=False, flare=True) -> Part
    # closed rounded end up with the connector centre at (0, 0), open end down at Y = -length
og.snap(*, lite=False) -> Part               # front face at Z = 0, wall side at Z = 6.8 (3.4)
og.grid_positions(width, height=None) -> list[tuple[float, float]]   # centred 28 mm cells that fit
og.require_cells(width, height=None)         # FAIL when the back holds no 28 mm cell
og.require_back(thickness, p)                # FAIL below slot depth + p.min_wall_mm, names 6.4 as usual
```

## Checks and tests

- Sections of a block minus `multiconnect_slot` match the profile to 0.02.
- Detent narrows the slot only in the wide part, at the measured place.
- `snap` sizes: across flats, height, slit, bump, Lite variant.
- `grid_positions` count and centring. `require_back` passes at the limit and fails below it.
- Against the official files when `CAD_OPENGRID_SOURCE` points at the package folder: symmetric
  difference with the official slot negative and the Bare Snap below 3% of the volume.
- A test block (`calibration/opengrid/`) with one Multiconnect slot (detent) and one snap builds
  with no FAIL. The owner prints it (about 10 g) and checks it on a board.

## Non-goals

Boards, connectors, the Lock (beta) and Directional snaps, the threaded Multiconnect snaps, HSW and
GOEWS. Directional snaps are a later addition through the same module.

## Left to the builder

Corner relief of the snap, chamfers of the front plate, how the detent blends in Z: matched to the
official sections and the comparison test.
