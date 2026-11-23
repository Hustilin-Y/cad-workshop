# CAD Workshop print manifest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** every print-ready build and every kit also writes `out/<name>.print.json`, a machine-readable manifest that the separate bambu-mcp connector slices from, and a part can state its print wishes in `PRINT_HINTS`.

**Architecture:** a new `cadlib/manifest.py` builds the manifest from what `cad.py build` and `cad.py kit` already compute (the check report, the estimate, the profile, the written 3MF) and validates `PRINT_HINTS` against a closed key list. CAD Workshop stays offline: it only writes a file.

**Tech Stack:** Python, uv, pytest, the existing cadlib (trimesh, build123d).

**Spec:** `E:\Projects\bambu-mcp\docs\superpowers\specs\2026-11-22-bambu-mcp-design.md`, section 6 ("CAD Workshop contract"). Contract consumer: bambu-mcp phase 2 plan, `E:\Projects\bambu-mcp\docs\superpowers\plans\2026-11-23-phase2-slicing.md` (Task 2 reads this manifest).

## Global Constraints

- No network, no printer, no slicer in CAD Workshop: `tests/test_no_network.py` must keep passing unchanged.
- Everything in the repo in English.
- The exact JSON shape is pinned by the consumer's fixtures `E:\Projects\bambu-mcp\tests\fixtures\manifest\{part,kit}.print.json` (branch `phase2-slicing`): `estimate: {"grams": n}` at top level and per plate (kits), `profile: {"material", "nozzle_mm", "tolerances"}`, `source` a dict, `checks` and `hints` as in Task 1. The manifest this repo writes must load with bambu-mcp's `load_manifest` unchanged: copy both fixtures into `tests/fixtures/manifest/` here and add a test that the written manifest has the same keys (recursively) as the matching fixture.
- Manifest schema version `1`. File name `out/<name>.print.json`, UTF-8, LF, `indent=1`, keys sorted.
- The manifest is written only by `build --print-ready` and `kit`. A plain `build` writes none and deletes a stale `out/<name>.print.json` if one exists (a stale manifest must never describe a non-print-ready file).
- `PRINT_HINTS` keys (closed list): `walls` (int 1..10), `infill_pct` (int 0..100), `infill_pattern` (one of `grid`, `gyroid`, `honeycomb`, `cubic`, `line`, `rectilinear`, `zig-zag`, `adaptivecubic`, `lightning`), `supports` (`none`, `auto`, `tree`, `normal`), `brim` (`none`, `auto`, `outer`), `material` (a key of `[materials.*]` in `printer.toml`), `material_reason` (str ≤ 200 chars). Any other key or value fails the build with a clear message naming the key.
- Owner's parts and WIP stay local: tests build in temp copies (existing pattern), never commit generated `out/`.

## Review Focus

- A part with `PRINT_HINTS` but no `PRINT_DOWN`: the manifest still says `print_ready: true` (files already lie as printed), matching the build's own message. (Test in Task 2.)
- A remix (`SOURCE`) build: the manifest carries `source.original_sha256` from SOURCE.md. (Test in Task 2.)
- `--set NAME=VALUE` overrides: recorded in `source.overrides` as strings, so a later reprint knows the variant. (Test in Task 2.)
- A failed build (`report.failed`): no manifest is written and a stale one is removed. (Test in Task 2.)
- A kit with a part printed twice: two objects on the plate, each with its own name suffix `#1`, `#2`. (Test in Task 3.)

---

### Task 1: Manifest model and PRINT_HINTS validation

**Files:**
- Create: `cadlib/manifest.py`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Produces:
  - `HINT_KEYS: Final[dict[str, object]]` (the closed list above with its validator per key).
  - `validate_hints(hints: object, profile) -> dict` (returns a cleaned dict; raises `ValueError` naming the bad key and the allowed values).
  - `checks_summary(report) -> dict` with keys `failed` (bool), `islands` (int, 0 when the check passed), `bodies_above_bed` (int), `overhang_warn` (bool), `base_warn` (bool), `supports_suggested` (bool = islands > 0 or bodies_above_bed > 0 or overhang_warn), read from the `Report` check names `5. Islands`, `5. Bodies above the bed`, `6. Overhangs`, `5. Base` (parse the counts from the messages; a missing check counts as 0/False).
  - `build_manifest(*, kind: str, name: str, file: Path, print_ready: bool, model_path: Path, overrides: dict[str, str], profile, plates: list[dict], checks: dict, estimate_g: float, hints: dict, original_sha256: str | None) -> dict` (adds `schema: 1`, `file_sha256`, `model_sha256`, `git_commit` from `git rev-parse --short HEAD` or `None` when git is unavailable).
  - `write_manifest(manifest: dict, path: Path) -> None` and `remove_stale(path: Path) -> None`.

- [ ] **Step 1: Tests**
  - `test_validate_hints_accepts_full_set`: all keys with valid values -> returned unchanged.
  - `test_validate_hints_rejects_unknown_key`: `{"wall": 3}` -> `ValueError` whose message contains `wall` and `walls`.
  - `test_validate_hints_rejects_bad_value`: `{"supports": "yes"}` -> `ValueError` naming `supports`.
  - `test_validate_hints_material_must_exist`: `{"material": "TPU"}` with the test profile -> `ValueError`.
  - `test_checks_summary_from_report`: a `Report` with `5. Islands` warn "2 islands …" and `6. Overhangs` warn -> `islands == 2`, `supports_suggested is True`.
  - `test_build_manifest_hashes_and_schema`: tmp 3MF and model files -> `schema == 1`, sha256 values match `hashlib.sha256` of the files.
  - `test_write_manifest_is_sorted_lf`: written text ends with `\n`, contains no `\r`, keys sorted.
- [ ] **Step 2:** Run `uv run pytest tests/test_manifest.py -q`. Expected: FAIL (no module).
- [ ] **Step 3:** Implement. Read the exact message formats in `cadlib/checks.py` (lines ~185-236 and ~396) before writing the parser and pin them in the tests.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `cadlib: print manifest model and PRINT_HINTS validation`.

### Task 2: Manifest from `build --print-ready`

**Files:**
- Modify: `cad.py` (`_build`, ~lines 249-315)
- Modify: `templates/` part template (add a commented `PRINT_HINTS` example)
- Test: `tests/test_build_manifest.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `out/<name>.print.json` with `kind: "part"`, `file: "<name>.3mf"`, one plate `{"index": 1, "objects": [{"name", "bbox_mm": [x, y, z], "volume_mm3"}]}` from the turned mesh.

- [ ] **Step 1: Tests** (build a tiny template part in a temp copy, as existing build tests do):
  - `test_print_ready_build_writes_manifest`: fields `kind`, `print_ready`, `file`, `profile.material`, `profile.nozzle_mm`, `estimate.grams` (from `cadlib.estimate`), `checks.failed is False`.
  - `test_plain_build_removes_stale_manifest`: write a dummy manifest, run `build` without `--print-ready` -> file gone.
  - `test_failed_build_writes_no_manifest`.
  - `test_hints_from_model`: `PRINT_HINTS = {"walls": 4}` -> `hints.walls == 4`; an invalid hint -> build exits 1 with the key named in output.
  - `test_overrides_recorded`: `--set WIDTH=45` -> `source.overrides == {"WIDTH": "45"}`.
  - `test_remix_records_original_hash`.
  - `test_no_print_down_still_print_ready`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement in `_build` after the report is complete: validate hints early (before exporting) so a bad hint fails fast; write the manifest only when `args.print_ready and not report.failed`; otherwise `remove_stale`. Print one line `JSON out/<name>.print.json` with the other outputs.
- [ ] **Step 4:** Run, then `uv run pytest -q` (full suite). Expected: PASS.
- [ ] **Step 5:** Commit: `build --print-ready writes the print manifest`.

### Task 3: Manifest from `kit`

**Files:**
- Modify: `cad.py` (`cmd_kit`, ~lines 524-600)
- Test: `tests/test_kit.py` (extend)

**Interfaces:**
- Produces: `out/<kit>.print.json` with `kind: "kit"`, `file: "<kit>.3mf"`, `plates` in kit order, objects named as in the 3MF (`<part>#<n>` for copies), per-plate `checks` (the worst of its parts) and per-plate `hints` (the parts' hints when they agree, else `{}` plus a `hint_conflicts` list), `estimate.grams` per plate.

- [ ] **Step 1: Tests:** `test_kit_writes_manifest_per_plate`, `test_kit_copies_named_with_suffix`, `test_kit_conflicting_hints_listed`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement; run the checks per part on the turned mesh (`check_mesh` with its `PRINT_DOWN`) to fill per-plate `checks`.
- [ ] **Step 4:** Run, then full suite. Expected: PASS.
- [ ] **Step 5:** Commit: `kit writes the print manifest`.

### Task 4: Rules and docs

**Files:**
- Modify: `CLAUDE.md`, `.claude/skills/cad/SKILL.md`, `multiclaude/addon/rules.md`, `README.md`

- [ ] **Step 1:** Replace "Don't connect to the printer, don't slice, don't touch Bambu Studio. Printing is the user's business." (SKILL.md) and the matching lines in CLAUDE.md and rules.md with: "CAD Workshop itself never connects to the printer or slices. When the owner asks to print, build with `--print-ready` (or `kit`) and hand `out/<name>.print.json` to the bambu-mcp tools." Keep "No automating GUIs".
- [ ] **Step 2:** README: a short "Printing through bambu-mcp" section: the manifest, `PRINT_HINTS` keys, and that the connector is a separate project.
- [ ] **Step 3:** Run `uv run pytest -q`. Expected: PASS (no code change).
- [ ] **Step 4:** Commit: `Rules: hand print-ready builds to bambu-mcp`.
