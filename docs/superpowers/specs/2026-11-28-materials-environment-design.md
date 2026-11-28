# Materials and environment: design (roadmap phase 4)

## Intent

A part says where it will live, and the build fails when the plastic it is printed in cannot take
the heat there. The owner prints car, boat and outdoor parts and wants the workshop to stop a PLA
part for a dashboard before it is printed, and to say which plastic would do.

## Decisions (owner approved 2026-11-28)

- Heat limit: the plastic's HDT at 0.45 MPa (ISO 75) minus a 10 °C margin must be at least the
  service temperature. HDT from Bambu Lab data sheets (source in a `printer.toml` comment):
  PLA 57, PETG 71, ABS 87 (retailer listing; Bambu's V2 sheet gives 84 at 1.8 MPa), ASA 100. TPU
  has no HDT in its sheet.
- Presets in `printer.toml` `[environments.*]`: `room` 30, `outdoor-sun` 60, `boat-sun` 65,
  `car-cabin` 70, `car-dash` 90 °C. `outdoor-sun` and `boat-sun` are in the sun (UV).
- A model declares `ENVIRONMENT = "car-dash"` or `SERVICE_TEMP_C = 65` (not both).
- The plastic checked: `PRINT_HINTS["material"]` if the model sets it, else the build's plastic
  (`--material`). When they differ, a WARN says the fits were computed for the build's plastic.
- Fail: names the plastics that would pass. No plastic passes: says so.
- UV: a WARN for sun presets when the plastic is not marked `uv_resistant` (only ASA is).
- TPU: a new plastic, no HDT, `clearance_add_mm` 0 with a note that the rigid-plastic fits do not
  apply and are not calibrated. A heat check with TPU is a WARN "no HDT data", not a FAIL.
- "What not to print" rules (oarlocks and oar pins, motor mounts, lifting points, pressure parts,
  lead moulds) in `CLAUDE.md` and the cad skill.

## Non-goals

Load or creep calculation (phase 7), annealing, per-colour data, cold limits.

## Design

- `cadlib/service.py`: reads `[service] margin_c`, `[environments.*]` (`temp_c`, `sun`) and the
  plastics' `hdt_c`, `uv_resistant` from `printer.toml`; `service_of(module)` returns the declared
  (label, °C) or None, with clear errors for an unknown preset or both keys set;
  `check_service(report, ...)` adds the "Environment" line (ok, fail, warn) and the UV line.
- `cad.py`: a helper called for a single part, each piece of a part in pieces, and each part in a
  `kit`, so the line shows in every report. No declaration, no line: existing parts do not change.
- Docs: README (environment), CLAUDE.md (declare `ENVIRONMENT` for parts that live in heat or sun;
  the what-not-to-print rules), the cad skill, the part template comment, roadmap status.

## Approaches

One sensible way: the check is data in `printer.toml` plus a small module, the same pattern as
fits and the manifest hints. A per-model hard-coded limit or a slicer-side check would put numbers
in model code or outside the workshop.
