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

Tolerances and the nozzle (0.2 / 0.4 / 0.6 / 0.8) and plastic (PLA, PETG, ABS, ASA) profiles are in [printer.toml](printer.toml). The values are starting points. To fit them to your printer, print `calibration/` (`uv run cad.py build calibration`) and follow [the instructions](calibration/README.md).

## Layout

```
cad.py              CLI
printer.toml        printer, nozzles, plastics, tolerances, filament estimate
cadlib/             export, preview, checks, orient, estimate, info, fasteners, mesh, text, threads, finish, logo, config
parts/<name>/       parts from scratch: model.py, README.md, out/
remix/<name>/       remixes: source/ (the original), remix.py, SOURCE.md, README.md, out/
calibration/        tolerance sample
templates/          templates for new part / new remix
multiclaude/        the add-in for the multiclaude Telegram bot
tests/              pytest
```

## Through Telegram (multiclaude)

The workshop installs as an add-in for [multiclaude](https://github.com/korsicheg/multiclaude), a Telegram bot that gives each person their own Claude Code. Then a part can be ordered from the chat, and the assistant sends back the PNG preview and a print-ready 3MF. Setup is in [multiclaude/addon/README.md](multiclaude/addon/README.md). An Ubuntu server also needs `libgl1`; the add-in's `setup` installs it. On a weak laptop a build takes 10–60 s and up to 0.7 GB of memory, a downloaded model of a million triangles up to 1.2 GB.

## What's not here

No connection to the printer, no slicing, no downloading by link, no multi-colour (AMS). The scripts never go online; a test checks that.

## Licence

The code is under the [MIT licence](LICENSE). It does not cover:
- **the workshop's logo** (a shiba inu with a bow tie). It is the owner's personal mark: the logo's picture and contours are not in the repository, and the logo may not be used without permission. Without the logo data `cadlib/logo.py` builds parts without it, and the logo tests are skipped;
- **remixes of other people's models**: each model has its own licence, given in the remix's `SOURCE.md`.
