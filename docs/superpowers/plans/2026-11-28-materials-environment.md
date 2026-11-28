# Materials and Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a part declares its environment or service temperature, and the build fails when the plastic's HDT minus a margin is below it, naming plastics that pass.

**Architecture:** data in `printer.toml` (`hdt_c`, `uv_resistant` per plastic, `[environments.*]`, `[service] margin_c`), a small `cadlib/service.py` that reads it and adds report lines, and one helper in `cad.py` called from the three build paths (single part, part in pieces, kit).

**Tech Stack:** Python, tomllib, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-28-materials-environment-design.md`

## Global Constraints

- Values: HDT 0.45 MPa: PLA 57, PETG 71, ABS 87, ASA 100, TPU none. Margin 10 °C. Presets: room 30, outdoor-sun 60 (sun), boat-sun 65 (sun), car-cabin 70, car-dash 90. Only ASA `uv_resistant = true`.
- Sources of HDT in `printer.toml` comments.
- No declaration → no report line, existing parts unchanged.
- English in code and output. Commit only on the owner's word.

## Review Focus

- `ENVIRONMENT` and `SERVICE_TEMP_C` both set, an unknown preset, a non-numeric temperature: a clear error before building (exit 2).
- Exactly at the edge (HDT − margin == temp): passes.
- `PRINT_HINTS["material"]` naming another plastic than `--material`: the hint's plastic is checked and a WARN notes the fits.
- TPU with a declared environment: WARN, not FAIL, not a crash on the missing `hdt_c`.
- A kit part and each piece of a part in pieces get the line too.

---

### Task 1: Data and `cadlib/service.py`

**Files:** Modify `printer.toml`. Create `cadlib/service.py`. Test `tests/test_service.py`.

**Interfaces (produces):**
- `@dataclass(frozen=True) Service`: `label: str`, `temp_c: float`, `sun: bool`.
- `service_of(module, path=PRINTER_TOML) -> Service | None` (ValueError on bad declarations).
- `check_service(report, service: Service, material: str, build_material: str, path=PRINTER_TOML) -> None`: adds "Environment" (ok / fail / warn) and, for sun presets on a non-UV plastic, a "UV" warn; a "Plastic" warn when `material != build_material`.
- `passing(temp_c, path=PRINTER_TOML) -> list[str]`.

- [ ] Write tests: each preset passes and fails at its edge (PLA room ok, PLA outdoor-sun fail naming PETG/ABS/ASA, PETG outdoor-sun ok, PETG boat-sun fail, ABS car-cabin ok, ABS car-dash fail naming only ASA, ASA car-dash ok at exactly 90); `SERVICE_TEMP_C = 61` with PETG passes (71 − 10 = 61); both keys → error; unknown preset → error listing presets; TPU → warn "no HDT"; sun preset with PETG → UV warn, with ASA none; material mismatch → warn; nothing declared → None. `load_profile(material="TPU")` loads.
- [ ] Run: `uv run pytest tests/test_service.py -q`. Expected: FAIL (no module).
- [ ] Implement data and module.
- [ ] Run. Expected: PASS.

### Task 2: Build integration

**Files:** Modify `cad.py`. Test `tests/test_service.py` (CLI cases with a tmp model).

- [ ] Write tests: a tmp part with `ENVIRONMENT = "car-dash"` builds with exit 1 and a FAIL line naming ASA; with `--material asa` exit 0; with `PRINT_HINTS = {"material": "ASA"}` and default PLA build the check passes and a WARN about fits shows; `ENVIRONMENT = "sauna"` exits 2; a part in pieces with a declaration fails on each piece; a kit part with a declaration shows the line in the kit's checks (exit 1 for a failing one).
- [ ] Run. Expected: FAIL.
- [ ] Implement `_service(module) -> Service | None` (UserError) called right after hints in `_build` and kit's `part()`, and `_add_service(report, service, hints, profile)` after each report.
- [ ] Run full suite: `uv run pytest -q`. Expected: all pass.

### Task 3: Docs, verification, review

- [ ] README (environment section), CLAUDE.md (declare `ENVIRONMENT`, what-not-to-print rules), cad skill, `templates/part_model.py` comment, roadmap status.
- [ ] `uv run cad.py build --all`: no FAIL, no new lines in existing parts.
- [ ] Fresh reviewer on the whole diff, fix Critical/Important with tests.
- [ ] Report to the owner, commit on their word.
