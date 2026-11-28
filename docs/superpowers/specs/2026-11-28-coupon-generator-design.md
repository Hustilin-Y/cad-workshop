# Coupon generator (roadmap phase 2)

Date: 2026-11-28. Status: started at the owner's word ("делаем дальше") from the roadmap entry.

## Intent

Every fit in the workshop gets its value from a printed step series, not a guess. Today that means
two hand-made plates (`calibration/model.py`, the owner's local `calibration/fit-test`). Gridfinity
(phase 3) needs a magnet pocket, later phases need shafts, seals and bearings. One generator makes a
labelled series for any fit, so a new fit is a new feature function, not a new plate.

## Goals

- `uv run cad.py coupon <feature> [options]` builds a coupon through the normal build pipeline
  (checks, PNG, STL/3MF, `--print-ready` manifest) into `calibration/coupons/out/`.
- Features at start, each with a default step range and the `printer.toml` key its result goes to:
  - `hole`: vertical holes `d + c` in a plate, tried with a metal rod or drill shank → `hole_clearance_mm`.
  - `press`, `slide`: plastic in plastic, holes `d + c` and pins `d − c` on one plate plus a key with
    an exact `d` pin and ring, as the tolerance gauge → `press_fit_mm`, `slide_fit_mm`. Same feature
    shape, different default ranges.
  - `magnet`: blind pockets `d + c` for disc magnets, depth = magnet height rounded up to a layer, a
    push-out hole in the floor → a new `magnet_fit_mm`.
  - `thread`: rings with an internal thread, major Ø `size + c`, one body each with a labelled tab,
    screwed onto a real bolt → `thread_clearance_mm`.
- Default ranges (on the diameter, mm): hole 0.0 to 0.5 by 0.1, press 0.0 to 0.25 by 0.05, slide
  0.15 to 0.5 by 0.05, magnet 0.0 to 0.3 by 0.05, thread 0.2 to 0.5 by 0.05. `--from --to --step`
  override them.
- Labels through `cadlib.text.label`, raised 3 layers. Samples wrap into rows to fit the bed.
- A feature registry, so the bearing phases add `bearing` without touching the layout code.

## Non-goals

Horizontal holes and seal or leak coupons (later features), automatic reading of results, editing
`printer.toml` from the CLI (the owner reports, Claude writes the value, as today).

## Decisions (my calls)

- Sizes that depend on the owner's hardware are required options, never defaults: `magnet` needs
  `--d` and `--h` (measured). `hole`, `press`, `slide` default to `d = 8` (the existing gauge and the
  common 8 mm drill shank), `thread` to `--size M8`. ISO coarse pitches (ISO 261) for M3 to M12 go
  into `cadlib/threads.py` as a table with its source.
- The CLI builds an in-memory model module and runs the existing `_build`, so the coupon gets every
  check and the print manifest for free. `calibration/coupons/` holds only a README; `build --all`
  skips it (no `model.py`), and the default tolerance gauge stays as it is.
- `magnet_fit_mm` is added now to `[tolerances]` and `Profile` (starting guess 0.1, plus the
  plastic's `clearance_add_mm`, like the other fits), so the coupon can say where its result goes
  and Gridfinity reads it from the profile.
- `PRINT_HINTS` on every coupon: `{"goal": ["fit", "cheap"], ...}`.
- The output file name carries the feature and the main size: `coupon-magnet-d6`, `coupon-thread-M8`.

## Checks and tests

Sections measure each sample (hole and pocket Ø, pin Ø, ring minor Ø), magnet depth is a multiple
of the layer with a floor ≥ `p.min_wall_mm`, body counts per feature, wrapping keeps the plate on
the bed, wrong input gives a clear error (`magnet` without sizes, unknown thread size, too many
samples for the bed, a range that is empty), and the CLI builds each feature with no FAIL.
