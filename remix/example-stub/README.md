# example-stub

An example remix of a finished STL: a through hole Ø8 and a slot 6 × 20 cut into a 60 × 40 × 20 block. The source is described in [SOURCE.md](SOURCE.md). It is a generated stub, so unlike other people's models its `source/` is kept in git.

## What changes and why

1. A hole Ø8 at X = −15.
2. A slot 6 × 20 along X at X = 12.
3. The build checks the volume change against the calculated one to ±1%, and the original's hash against SOURCE.md.

## History

- 2026-11-03: created as the reference example (stage 4 of the spec). Volume −3250.1 mm³ against the calculated −3250.8.
