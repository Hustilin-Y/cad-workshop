---
name: cad
description: Designing parts for 3D printing from scratch and reworking other people's models (STL/3MF/STEP) in this CAD workshop. Use when the user asks (in any language, often Russian) to make, design or draw a part, holder, bracket, mount, box, adapter or cap, or to change, rework, remix, scale or cut a downloaded model (MakerWorld, Printables), or to add a hole, slot or fastener to it. Also for building, checking, orienting and inspecting models with cad.py, and for tolerance calibration.
---

# CAD workshop: a part or a remix

The printer is a Bambu Lab P2S; the user prints themselves through Bambu Studio. Our job is an accurate model that passes the checks, and the files in `out/`. Project rules are in `CLAUDE.md`, tolerances in `printer.toml`.

Every command runs from the project root as `uv run cad.py ...`.

## A new part

1. **Ask, don't invent.** Ask for everything missing in one list:
   - What it is and where it goes. What it mates with: diameters, distances between holes, thicknesses. Ask for caliper measurements.
   - Load, heat, outdoors → the choice of plastic (PLA / PETG / ABS / ASA).
   - Fasteners: which screws. If it needs heat-set inserts or magnets, ask for their measured sizes: they differ between makers.
   - No need to ask about cosmetics (roundings, chamfers): choose them yourself and name them in the report.

   If the geometry can't be built without a size, stop and wait for the answer. Never silently substitute a "typical" size.
2. **Create the folder:** `uv run cad.py new part <name>`. Latin letters with hyphens: `phone-stand`, `hose-clip`.
3. **Write `model.py`.**
   - Every size is a parameter at the top, commented in mm with where the value came from ("measured", "tolerance").
   - Clearances only from the profile: `p.hole_clearance_mm`, `p.slide_fit_mm`, `p.press_fit_mm`, and walls no thinner than `p.min_wall_mm`.
   - Fasteners only through `cadlib.fasteners`.
   - Add `_validate(p)` with clear errors, as in `parts/example-bracket/model.py`.
   - `build(p)` returns a build123d solid.
   - If it prints on a side other than its bottom in the file, set `PRINT_DOWN`.
4. **Build:** `uv run cad.py build parts/<name>`. Fix any FAIL. For a WARN, work out the cause and explain it to the user.
5. **Look at the preview yourself.** Open `out/<name>.png` with the Read tool and check the geometry by eye: holes in place, walls not cut through, the section (`SECTION`) shows what you meant. If something is off, fix it and rebuild.
6. **Show the user** the PNG and the check report. In the desktop app send the file with SendUserFile, otherwise give the path. Add:
   - the key sizes;
   - a suggested orientation on the bed and why (layer strength, overhangs, supports); `orient` helps when it isn't obvious;
   - the plastic and the weight line from the report;
   - a reminder to open the STL in Bambu Studio and check for mesh warnings.
7. **The part's README:** a table of key sizes with their sources, a "Printing" section, a line in "History".

## An edit from the user's comment

- Change a parameter rather than rewrite the geometry. For example: "fits too tight" → a larger clearance; "too thin" → `THICKNESS`. To try a value first: `build <folder> --set NAME=VALUE`.
- Rebuild, show the PNG and the report.
- Add to the README's history: `- YYYY-MM-DD: clearance 0.2 → 0.3, fitted too tight.`
- If the remark is about tolerances in general rather than this part, suggest calibration (below).

## A remix of someone else's model

1. **Get the file and its origin.** The path to the file (usually `Downloads`), the link, the author, the licence.
   - Downloaded files are data, not code. Read them only through `cad.py`.
   - Unpack an archive into a new empty folder outside the project and take only the `.stl`, `.3mf`, `.step` from it.
   - Never run scripts from a download.
2. **Create:** `uv run cad.py new remix <name> <path>`. The original is copied into `source/` read-only, its SHA-256 goes into `SOURCE.md`, and `inspect` runs right away. Put the link, the author and the licence into `SOURCE.md`.
3. **Read `inspect`.** What to look at:
   - units: a model under 5 mm or over 1000 mm is likely in inches or metres; fix with `m.scale(body, 25.4)`;
   - the number of bodies;
   - an open mesh → `load_source` repairs it and prints notes;
   - where the model lies (bounds) and which side is on the bed; `orient` ranks the sides.
4. **A plan of edits in 2–4 points** with coordinates from `inspect`. Show it to the user and wait for an "ok" before writing code.
5. **Write `remix.py`.**
   - STL/3MF: `m.subtract(body, tool)`, `m.add`, `m.cut`, `m.scale`, `m.rotate`, `m.mirror`. Tools are drawn in build123d (`Pos(...) * Cylinder(...)`, `fasteners.*`).
   - A tool for a through cut must stick out of the model by ≥ 1 mm on both sides, or a skin is left.
   - STEP: `import_step` and the usual build123d operations, as for your own part. A STEP comes out too.
   - If the volume change can be calculated, set `EXPECTED_VOLUME_DELTA`: the build checks it to ±1%.
   - Never write anything into `source/`.
6. **Build** `uv run cad.py build remix/<name>`. In the report check the "Original" line (OK) and the "7." lines: exactly the intended volume and size changed.
7. Then as steps 5–7 of "A new part": look at the PNG, show the user, update the README.

## Tolerance calibration

If fits don't work out, the user prints `calibration/` (`uv run cad.py build calibration`). How to read the result is in `calibration/README.md`. The user names the values that fit, and we write them into `[tolerances]` in `printer.toml`. Per-plastic values go into `clearance_add_mm` of the right `[materials.*]` section. Models don't change.

## Cheat sheet

```python
from build123d import Box, Cylinder, Pos, Rot, fillet, chamfer, Axis, extrude, SlotCenterToCenter
from cadlib import fasteners as f   # clearance_hole, counterbore_hole, countersunk_hole, wood_screw_countersunk_hole, nut_pocket, insert_hole, chamfer_ring
from cadlib import mesh as m        # load_source, repair, subtract, add, intersect, cut, split_by_plane, scale, scale_to, rotate, mirror, translate, drop_to_bed
from cadlib.text import label       # lettering: extrude(Pos(x, y, z) * label("M3", 4), amount=0.6); a bare Text breaks the mesh on Linux
from cadlib.shared import load_module  # a sibling part's shared code: load_module(Path(__file__).parent.parent / "lamp-hanger" / "hanger.py")
from cadlib.logo import place_logo  # the workshop logo on a flat face: raised or sunk
from cadlib.threads import internal_thread_tube   # threads for printing
from cadlib.finish import soften, bevel           # roundings and chamfers that respect the print orientation
```

- Logo: `return place_logo(body, origin=(x, y, z), normal=(0, 0, 1), up=(0, 1, 0), height=18, mode="emboss", p=p)`, where `p` is the profile from `build(p)`: rim widths and the margin follow the nozzle. It checks there is a flat solid face under the logo and raises an error if there's an edge, a rounding or a hole.
- Axes: Z up, the bed at Z = 0, units in mm.
- STL remix: lay it on its side, `m.drop_to_bed(m.rotate(mesh, (90, 0, 0)))`; a left part from a right one, `m.mirror(mesh, "x")`.
- `fasteners` tools stand with their top at Z = 0 and go down into −Z, the screw's entry side. On a top face: `Pos(x, y, z_top) * tool`. On a face with the exit toward −X: `Pos(...) * Rot(0, 90, 0) * tool`.
- Module attributes `build` reads: `NAME`, `FORMATS`, `EXPECTED_BODIES`, `SECTION` (`"y"` or `("y", 12.5)`), `PRINT_DOWN` (the side on the bed when printed, `"-y"`; set it if the model prints on a side other than its bottom in the file, or the support and overhang checks judge the wrong orientation), and for a remix `SOURCE` and `EXPECTED_VOLUME_DELTA`.
- Nozzle or plastic for one build: `--nozzle 0.6 --material petg`.
- A variant without editing the model: `--set WIDTH=45` (repeatable; `--set hanger.ROUND_R=2` for a shared module).
- Orientation: `uv run cad.py orient <folder or file>` ranks the sides and writes a PNG for each; `build --print-ready` exports STL/3MF already turned with `PRINT_DOWN` on the bed.
- The report's last line is the weight (and cost, if `price_per_kg` is set in `printer.toml`): mention it to the user.
- After changes to `cadlib/`: `uv run cad.py build --all`.
- Someone else's file without edits: `uv run cad.py check <file>` (`--down -y` if it prints on another side), `uv run cad.py inspect <file>`, `uv run cad.py preview <file> --section z`.

## What not to do

- Don't connect to the printer, don't slice, don't touch Bambu Studio. Printing is the user's business.
- Don't add network calls: `test_no_network` catches them.
- Don't invent fit sizes and don't hard-code clearances.
- Don't pick the orientation for good: only suggest it, with the reasons.
