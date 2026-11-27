# example-hanger-kit

The hanger kit archetype of `cadlib.style` in one of five dialects: a ceiling mount bar and two arms with cradles that hold a long object below the ceiling, joined by dovetails with a snap detent. The example hangs a made-up 400 mm object (a slim LED bar, say) 200 mm below the ceiling: its -X end is a 32 × 16 mm block, its +X end a flat 32 × 7.2 mm plate. Three pieces, three folders:

| Folder | Piece |
|---|---|
| `parts/example-hanger-kit` | the mount (this folder, also holds `hanger_params.py` and `kit.py`) |
| `parts/example-hanger-kit-arm-a` | arm A, cradle round the -X end |
| `parts/example-hanger-kit-arm-b` | arm B, cradle round the +X end |

```
uv run cad.py kit parts/example-hanger-kit                          # all three pieces, a plate each
uv run cad.py build parts/example-hanger-kit-arm-a --set STYLE='gaudi'
```

The style and the sizes live in `hanger_params.py`; every piece's `model.py` loads it and takes its piece with `hanger_piece(...)`. The kit is built once and cached, so a kit build makes it once, and each piece's build report still lists the style notes of that piece only.

## What and why

| Dialect | Arm | Mount |
|---|---|---|
| gothic | a triangle frame (ceiling rail, strut, post) whose spandrel is an arcade of pointed lancet windows standing on the strut, nervure ribs in relief along the rail, the strut, the post and over each window head, a pendant finial under the cradle | a pointed pendant under the bar between the screws |
| gaudi | one sweep from the hub curving down into the post, tapering, with a hanging catenary brace under it: the two frame one large organic opening | a catenary belly under the bar |
| hitech | a truss: a chord along the ceiling, a lower chord to the post, Warren diagonals between, round joints inside the members | blind triangle pockets on the +Y face |
| parametric | a web under the ceiling with a rising (concave) spline underside, perforated by a hex lattice whose bars thicken towards the hub, where the bending peaks | a spline belly with hex cells |
| biomech | a full web: its outer contour sweeps from the hub down into the post, its underside sags, every corner but the mating face is rounded and the web is an organic cell lattice, finest at the hub | a rounded belly with organic cells |

Edges follow the dialect: gothic chamfers, the others round.

- Every piece prints lying on its -Y face (`PRINT_DOWN = "-y"`): the styling is all outline and through-cuts, which print without support, and the load acts along the layers.
- Dovetails slide along Y, which is vertical in print. An arm slides into the mount from +Y until the detent snaps. The tenon stands on the bed with its arm, so the mount, which holds the sockets, carries their closed ends and stop walls below the arms' -Y face: it is 3.3 mm deeper on -Y than the arms (slide fit 0.3 + stop wall 3).
- The cradle pocket fits the end profile plus the 0.3 mm slide fit per side, centred on the depth. It is open on top and on +Y and closed on -Y: a wall on +Y would be a roof over the pocket in print, while the -Y wall lies on the bed. Lay the object in from above or slide it in from +Y against that wall. Both arms' walls are as tall as the taller end.
- Nothing of an arm comes inward of the cradle's end wall below the object's top plus one more object height, so an end can be lifted in.
- The mount's screws are countersunk 3 mm wood screws, the heads 6 mm up from the room face. Lying on its side the holes are horizontal, so each gets a 46° teardrop roof towards +Y.
- An arm wider than the bed (246 mm usable, less a 10 mm margin) is cut square to its centreline into the fewest equal segments that fit, each cut a dovetail in a solid band across the arm. The example's arms fit whole.
- Hooks for later stages: the load is two 7.5 N pulls straight down at the cradle floors, the support the mount's ceiling face, tunables `arm_t`, `depth`, `mount_h`.

## Key sizes

| Parameter | Value | Source |
|---|---|---|
| Span × drop | 400 × 200 mm | example |
| Mount | 70 × 18 mm, 38 + 3.3 mm deep | `HangerSpec` defaults |
| Arm members | 8 mm (gothic 10 mm, room for a rib), 38 mm deep | `arm_t`, `depth` |
| Dovetail | neck 8, wide 12, 8 deep, as long as the depth, 0.3 mm slide fit | `DovetailSpec` defaults, `printer.toml` |
| Cradle | 20 mm long, floor 4 mm, end wall 8 mm, -Y wall 2.7 mm | `cradle_len`, ratios in `hanger.py` |
| Screws | Ø3 wood screws: hole 3.6, countersink 6.2 | `cadlib.fasteners`, `printer.toml` |

## History

- 2026-11-27: created with the hanger kit archetype (five dialects, dovetail joints, splitting for long spans).
