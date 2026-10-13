# Panel handoff

Target: existing Titan V3 gameplay-panel owner.

1. Materialize the canonical archive whose SHA-256 is exactly
   `3b4b083ec2647bb0e715978c2565e916da0ee94c08b234902e3a7e4d3418c320`.
2. Run `build_candidate.py` into a new output directory.
3. Verify the emitted `ARGUS-G01-BUILD.json` and retain it with the run.
4. Enable **only** `TITAN_E11_RIVAL_SELL=1`; explicitly disable O01, E20, SHOP.
5. Run the already-assigned paired development registry against unchanged 3b4b,
   both seats, preserving per-opponent and per-seed cells.
6. Return candidate/control archive hashes, runner commit, environment, command,
   all errors/timeouts, wins, cash delta, and the immutable result artifact.
7. Stop on any import error, deadline fallback increase, illegal action evidence,
   cell-count mismatch, or hash mismatch. Do not silently retry a changed build.
8. Do not promote from aggregate mean alone. Inspect opponent and seat slices,
   the known V1 regression cell, and holdout only after development is clean.

This handoff does not claim or reserve the panel lane; it supplies a repaired arm
to the owner already running it.
