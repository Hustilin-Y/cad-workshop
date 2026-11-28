# CAD workshop

[![tests](https://github.com/Hustilin-Y/cad-workshop/actions/workflows/tests.yml/badge.svg)](https://github.com/Hustilin-Y/cad-workshop/actions/workflows/tests.yml)

Parametric parts and remixes of other people's models for 3D printing on a Bambu Lab P2S. Models are written as code (build123d, manifold3d), built with one command, checked, and delivered as STEP, STL and 3MF with a PNG preview. You print them yourself: open the file in Bambu Studio.

It works best through Claude Code: open this folder and ask, for example, "make a holder for …" or "rework this STL: …". The workflow is in the skill [.claude/skills/cad](.claude/skills/cad/SKILL.md) and in [CLAUDE.md](CLAUDE.md).

## Setup

All it needs is [uv](https://docs.astral.sh/uv/). It installs Python 3.12 and the packages inside the project folder:

```bash
uv sync
```

```bash
uv run pytest
```

The first run after installing can take a few minutes on Windows while Defender scans the new files. After that a build takes seconds.

## Commands

| Command | What it does |
|---|---|
| `uv run cad.py new part <name>` | create `parts/<name>/` from the template |
| `uv run cad.py new remix <name> <file>` | create `remix/<name>/`: the original is copied into `source/` read-only, and `inspect` runs right away |
| `uv run cad.py build <folder>` | build: STEP, STL, 3MF, PNG and the check report in `<folder>/out/` |
| `uv run cad.py build --all` | build every model, one line each; the failures in full |
| `uv run cad.py preview <folder or file>` | only the PNG (`--section x/y/z` adds a section) |
| `uv run cad.py check <file>` | checks of any STL, 3MF or STEP, someone else's too |
| `uv run cad.py inspect <file>` | size, volume, bodies, base, flat faces |
| `uv run cad.py orient <folder or file>` | best sides to print on: a table, a PNG of each and the `PRINT_DOWN` line to use |
| `uv run cad.py coupon <feature>` | a calibration coupon in `calibration/coupons/out/`: `hole`, `press`, `slide`, `magnet` (`--size 5x4,10x3`, default 5x4, 6x2, 10x3), `thread` (`--size M8`); `--from/--to/--step` set the range |
| `uv run cad.py kit <folder>` | a set of parts in one 3MF for Bambu Studio: every part its own object, turned with `PRINT_DOWN` on the bed, a plate each (as `<folder>/kit.py` lists them) |

Build flags:
- `--nozzle 0.6`, `--material petg`: another nozzle or plastic for one build.
- `--set NAME=VALUE` changes a model parameter for one run without editing the file: `--set WIDTH=45 --set LOGO=False`, or a shared module's, `--set hanger.ROUND_R=2`. Only what `build(p)` reads at run time changes.
- `--print-ready` exports STL and 3MF turned so the `PRINT_DOWN` side lies on the bed: open them in the slicer and print as they are. STEP keeps the design orientation.

## Adding a part

1. `uv run cad.py new part phone-stand`
2. In `parts/phone-stand/model.py` set the parameters at the top (mm) and the geometry in `build(p)`. Take clearances from `p` and screw holes from `cadlib.fasteners`. Example: [parts/example-bracket](parts/example-bracket/model.py).
3. `uv run cad.py build parts/phone-stand`, look at `out/phone-stand.png` and the report.
4. Open `out/phone-stand.3mf` (or the STL) in Bambu Studio, check it shows no mesh warnings, then print.

## Reworking someone else's model

1. `uv run cad.py new remix holder-fix C:\Users\<you>\Downloads\holder.stl`
2. Put the link, the author and the licence into `remix/holder-fix/SOURCE.md`.
3. In `remix.py` describe the edits with `cadlib.mesh`: `subtract` (holes, slots), `add`, `cut`, `scale`, `rotate`, `mirror`. Example: [remix/example-stub](remix/example-stub/remix.py).
4. `uv run cad.py build remix/holder-fix`. The report compares the result with the original and checks that the original itself is unchanged.

Other people's files in `remix/*/source/` never go into git.

## Checks in a build

1. The mesh is closed and manifold, with no degenerate triangles. **Error.**
2. The volume is above 0; the number of bodies is as expected. Volume ≤ 0 is an **error**, extra bodies a warning.
3. The part fits the 256 × 256 × 256 bed with a 5 mm margin. **Error.**
4. Plausible scale: the size is between 5 and 1000 mm. Otherwise a warning: the model may be in inches or metres.
5. Support, warnings:
   - there is a flat base, and under a tall part it isn't too narrow (less than 10% of the footprint while the part is taller than twice the width of the contact patch: it tears off or tips over);
   - every body stands on the bed;
   - no islands: places where a layer starts in the air, as a slicer sees them. A small island that joins the part within 1 mm is only mentioned.
6. Share of overhangs steeper than 45°; above 25% it's a warning.
7. For a remix: the change in volume and size against the original, and the original's hash.

Checks 3, 5 and 6 are judged in the print orientation. If a model is printed on a side other than its bottom in the file, `model.py` sets `PRINT_DOWN = "-y"` (the side that goes on the bed); for someone else's file use `check <file> --down -y`. The files themselves are not turned (unless you build with `--print-ready`).

The report ends with the weight: grams of plastic at the infill share from `printer.toml` (shells + infill, about ±20% of the slicer's figure) and the solid mass as an upper bound. With `price_per_kg` set for the material it also shows the cost.

If any **error** check fails, `build` exits with code 1.

## Tolerances and calibration

Tolerances and the nozzle (0.2 / 0.4 / 0.6 / 0.8) and plastic (PLA, PETG, ABS, ASA) profiles are in [printer.toml](printer.toml). The values are starting points. To fit them to your printer, print the tolerance gauge (`uv run cad.py build calibration`) for plastic-in-plastic fits and the fit-test plate (`uv run cad.py build calibration/fit-test`) for screws, shafts and threads against metal, and follow [the instructions](calibration/README.md). For any single fit, `uv run cad.py coupon <feature>` makes a labelled step series of it ([calibration/coupons](calibration/coupons/README.md)); the build names the `printer.toml` key the result goes to. Magnet pockets (`cadlib.magnets`) use `magnet_fit_mm` on the magnet's nominal diameter.

## openGrid and Multiconnect

`cadlib.opengrid` puts an openGrid interface on a part's back: a Multiconnect slot (`multiconnect_slot`, open end down, with an optional snap-in detent and entry flare) to lower onto an official Multiconnect snap in a board, or an openGrid snap (`snap`, full or Lite) to clip straight into a board cell. Cells are 28 mm (`grid_positions`). The sizes are the openGrid standard, clearances included, so they don't follow `printer.toml`. Print the test pieces (`uv run cad.py build calibration/opengrid`, about 10 g) and try them on a board first.

## Layout

```
cad.py              CLI
printer.toml        printer, nozzles, plastics, tolerances, filament estimate
cadlib/             export, preview, checks, orient, estimate, info, fasteners, mesh, text, threads, finish, logo, opengrid, coupon, magnets, config
parts/<name>/       parts from scratch: model.py, README.md, out/
remix/<name>/       remixes: source/ (the original), remix.py, SOURCE.md, README.md, out/
calibration/        tolerance gauge; fit-test/ for fits against metal; opengrid/ test pieces for an openGrid board; coupons/ output of `cad.py coupon`
templates/          templates for new part / new remix
multiclaude/        the add-in for the multiclaude Telegram bot
tests/              pytest
```

## Through Telegram (multiclaude)

The workshop installs as an add-in for [multiclaude](https://github.com/korsicheg/multiclaude), a Telegram bot that gives each person their own Claude Code. Then a part can be ordered from the chat, and the assistant sends back the PNG preview and a print-ready 3MF. Setup is in [multiclaude/addon/README.md](multiclaude/addon/README.md). An Ubuntu server also needs `libgl1`; the add-in's `setup` installs it. On a weak laptop a build takes 10–60 s and up to 0.7 GB of memory, a downloaded model of a million triangles up to 1.2 GB.

## Printing through bambu-mcp

The workshop only prepares files. Slicing and printing are done by [bambu-mcp](https://github.com/Hustilin-Y/bambu-mcp), a separate project (a connector for Claude). The link between the two is a print manifest, `out/<name>.print.json` (schema version 1, UTF-8, sorted keys): the print-ready 3MF with its hash, the weight estimate, the material, nozzle and tolerances, the check results and the hints below.

- It is written by `build --print-ready` and `kit` only. A plain `build` writes none and removes a stale one.
- A build or kit whose checks fail writes no manifest.
- A part may carry slicing hints in `model.py`; all keys are optional, any other key or value fails the build with a message naming the key:

| Key | Values |
|---|---|
| `walls` | integer 1..10 |
| `infill_pct` | integer 0..100 |
| `infill_pattern` | `grid`, `gyroid`, `honeycomb`, `cubic`, `line`, `rectilinear`, `zig-zag`, `adaptivecubic`, `lightning` |
| `supports` | `none`, `auto`, `tree`, `normal` |
| `brim` | `none`, `auto`, `outer` |
| `material` | a plastic described in `[materials.*]` of `printer.toml` |
| `material_reason` | a string of at most 200 characters |
| `goal` | one of `balanced`, `speed`, `strength`, `quality`, `cheap`, `light`, `fit`, `watertight`, or a list of two different ones (primary, secondary) |
| `goal_reason` | a string of at most 200 characters: why this goal |

Give either a `goal` or explicit `walls`/`infill_*` hints. When both are set, the goal's base point wins for the settings it sets (walls, infill and so on), and bambu-mcp decides. Set `goal` from what the part does and say why in `goal_reason`: load-bearing gives `strength`, heat or outdoor use gives `strength` plus a suitable `material`, threads, snaps and press fits give `fit`, liquids or seals give `watertight`, visible decor gives `quality`, test and calibration pieces give `speed` and `cheap`. The owner's words override.

```python
PRINT_HINTS = {"walls": 4, "infill_pct": 25, "infill_pattern": "gyroid"}
PRINT_HINTS = {"goal": ["fit", "strength"], "goal_reason": "load-bearing bracket with a press fit"}
```

Claude never starts a print: the owner starts every print, outside the model. Without bambu-mcp, open the 3MF in Bambu Studio as before.

## What's not here

No connection to the printer, no slicing, no downloading by link, no multi-colour (AMS). The scripts never go online; a test checks that. Printing from a build is done by a separate project, see [Printing through bambu-mcp](#printing-through-bambu-mcp).

## Licence

The code is under the [MIT licence](LICENSE). It does not cover:
- **the workshop's logo** (a shiba inu with a bow tie). It is the owner's personal mark: the logo's picture and contours are not in the repository, and the logo may not be used without permission. Without the logo data `cadlib/logo.py` builds parts without it, and the logo tests are skipped;
- **remixes of other people's models**: each model has its own licence, given in the remix's `SOURCE.md`.
- **the openGrid and Multiconnect designs**: `cadlib/opengrid.py` is our own code, but its dimensions are derived from the modeling files of [openGrid - Wall/Desk mounting framework/ecosystem](https://makerworld.com/en/models/1179191-opengrid-wall-desk-mounting-framework-ecosystem) by David D, licensed [CC BY](https://creativecommons.org/licenses/by/4.0/). Their files are not in this repository. A part that uses the interface says so in its README: "openGrid/Multiconnect interface: dimensions from openGrid by David D, CC BY".
