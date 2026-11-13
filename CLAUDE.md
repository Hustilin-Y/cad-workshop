# CAD workshop: working rules

A project for designing and reworking parts for 3D printing on a Bambu Lab P2S.
Claude Code writes the model as code, builds it, checks it and hands over the files; the user prints them through Bambu Studio.

## Language

- Talk to the user in their language (usually Russian).
- Everything written into the project is in English: code, comments, docs, part READMEs you create, commit messages, CLI output. The user's own existing parts may have Russian comments: leave them as they are.

## Environment

- Windows 11, native. Don't tie code to an OS: paths only through `pathlib`.
- Everything through `uv`: `uv run cad.py ...`, `uv run pytest`. Install nothing globally.
- Network only for `uv add`. Scripts never go online and never talk to the printer (a test checks that).
- No Blender. No automating GUIs (Bambu Studio and the like).

## Printer profile

- All tolerances, walls and bed sizes come from `printer.toml` through `cadlib`; no numbers in model code.
- The default nozzle is 0.4; the 0.2/0.6/0.8 profiles are described. If the user says they're fitting another nozzle, change `nozzle_mm` (or pass it to the build) without editing models.
- The default plastic is PLA; PETG, ABS and ASA are there too. For heat, outdoors or load, suggest a suitable plastic and say why.

## Output

- For own parts: STEP + STL + 3MF in `parts/<name>/out/`.
- Preview: a PNG (isometric + 3 projections); always show it to the user.
- Live 3D view: OCP CAD Viewer in the browser, no VS Code needed. The viewer's packages are in the optional `viewer` group: the user runs `uv run --group viewer python -m ocp_viewer` (a local server on localhost:3939), and a model is sent there by a script under `uv run --group viewer` with `from ocp_vscode import show`. It's an optional extra: a build must not fail when the viewer isn't running.

## How to work

- Always start by asking for missing sizes. Don't invent fit sizes: if you don't know a diameter or a distance, ask (a caliper measurement is best).
- Keep a part's parameters at the top of `model.py`, commented in mm. A new part: `uv run cad.py new part <name>`.
- Holes for screws, nuts and heat-set inserts only through `cadlib.fasteners` (ISO sizes + profile tolerances), never drawn by hand. Insert and magnet sizes differ between makers: ask for a measurement before using them.
- The workshop logo (the shiba relief) goes on parts with `cadlib.logo.place_logo(body, origin, normal, up, height, mode, p=p)`: with the profile `p`, rims, margin and level heights follow the nozzle and layer. Choose a flat face that is visible in use and, if possible, on top when printing. Size from 15 mm. `mode="deboss"` (flush) for children's things and parts that rub. A part with the logo comes out as a mesh, without STEP; `LOGO = False` in the model brings STEP back. If there's no room for the logo, tell the user rather than squeeze it in.
- Lettering on parts only through `cadlib.text.label(text, height_mm)`: the font comes from a package, not the system, so it's the same on Windows and Linux. A bare build123d `Text` on Linux without Arial gives an open mesh.
- Check printability in the model's `_validate(p)` (walls ≥ `p.min_wall_mm`, room for each hole) with a clear error.
- After every build show the user the PNG preview and the check report before calling the task done.
- Make edits from comments through parameters rather than by rewriting geometry where you can. To try a variant before changing the file: `build <folder> --set NAME=VALUE`.
- After changing `cadlib/`, run `uv run cad.py build --all` as well as the tests: it rebuilds every part, including the user's local ones.
- Keep a short history in the part's `README.md`: what changed and why (for example "clearance 0.2 → 0.3, fitted too tight").
- For a remix: `inspect` the original first, then a plan of edits in 2–4 points, then the edits.
- A new remix: `uv run cad.py new remix <name> <file>`. The original is copied into `source/` read-only, its SHA-256 goes into SOURCE.md, and inspect runs right away. Ask the user for the link, the author and the licence and put them into SOURCE.md.
- STL/3MF are edited with `cadlib.mesh`: `subtract`, `add`, `cut`, `scale`, `rotate`, `mirror`, `repair`. Tools (holes, slots) are built in build123d. A STEP is edited like an own part through `import_step`, which is more precise.
- If the volume change can be worked out in advance, set `EXPECTED_VOLUME_DELTA`, and the build checks it to ±1%.
- Don't touch `remix/*/source/`: the original is read-only; every edit goes into a new file.
- Suggest the print orientation, but the user makes the final choice in Bambu Studio. When the best side isn't obvious (remixes of downloaded models, figurines), run `uv run cad.py orient <folder or file>` and show its PNGs; it ranks sides by islands, base and overhangs. Record the suggested side in the model as `PRINT_DOWN` if it isn't the bottom in the file: the support and overhang checks use it. Explain the "Islands", "Bodies above the bed" and "Base" warnings to the user rather than ignore them.
- Remind the user to open the STL in Bambu Studio and make sure it shows no damaged-mesh warnings.

## Git

- A public GitHub repository (account Hustilin-Y), a portfolio. `out/` and `remix/*/source/` are always in `.gitignore`: other people's models are never published, except our own generated stubs `remix/example-*/source/` (CC0).
- The user's own parts and work in progress stay local and are not committed; commit only the workshop's code and examples.
- Before committing, check that no one else's models, personal data or paths outside the project got into the index.
- Commit and push only when the user asks.
