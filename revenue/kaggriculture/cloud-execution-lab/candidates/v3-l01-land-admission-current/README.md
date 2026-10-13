# TITAN V3 — current LAND admission

This lane takes the only completed L01 arm with a positive result and tests it
against the **current** selected TITAN archive. It does not modify the canonical
runtime, selected configuration, archive, or default entrypoint.

## Why this lane exists

PR #11459 evaluated five isolated leader-mechanism flags on the historical
`3b4b...` archive. `LAND` was the only completed arm that materially improved
the panel: Arlene moved from 24–8 with mean margin `-2418.219` to 32–0 with mean
margin `+1631.031`; the other five opponent summaries were unchanged.

The raw paired cells reveal a sharper mechanism:

* exactly 8 of 192 cells changed;
* all 8 were Arlene, candidate seat 0, seeds `2611061001..2611061008`;
* every changed cell flipped `L -> W`;
* total margin improved by `129,576` (`+4,049.25` per Arlene cell and
  `+674.875` per full-panel cell);
* changed-cell own cash **fell** by `8,505` on average, while rival cash fell by
  `24,702` on average.

So the effect is not “more cash.” It is a route/turn-order correction that
suppresses an Arlene seat-0 failure mode. Seven of the eight corrected cells
exactly reproduce the historical opposite-seat score pair, which is a strong
seat-normalization signature and a reason to demand disjoint holdout evidence.

## Intervention

`land_admission.py` preserves the historical L01 intervention surface:

1. wait for `TitanAgent._initialize()` to build `controller.R`;
2. at route steps 74 and 98, append `["BUY_LAND"]` when the market row has
   fewer than ten orders and no existing land buy;
3. read no observation, opponent, seed, seat, score, or environment variable.

Current `early_capital.py` only reorders an existing `BUY_LAND`. It does not
create one, so this mechanism is not redundant with the current package.

## Evidence ladder

1. Unit tests prove idempotence, capacity preservation, shared-row behavior,
   fail-closed archive binding, strict paired-grid math, and exact route diffs.
2. The workflow downloads the immutable PR #11459 panel at commit
   `c817c06...`, verifies both Git blob IDs, and reproduces the exact eight-cell
   signature.
3. `build_candidate.py` verifies the current archive and source-manifest
   SHA-256 values, extracts a byte-identical baseline, and creates one additive
   candidate by copying `land_admission.py` and inserting one fail-closed wrap
   call into `main.py`.
4. `route_probe.py` initializes both current packages and proves the candidate
   route table equals `baseline + exact LAND transform`; it records the first
   route/step divergence.
5. The official `kaggle-environments==1.32.7` engine runs a disjoint
   384-game paired panel: 16 new seeds × 6 opponents × both seats × 2 arms.
   `panel_delta.py` refuses incomplete, duplicate, missing, or unpaired cells
   and emits exact per-cell, per-seat, and per-opponent deltas.

A result is marked `advance` only when the complete current panel changes,
creates no new losses, and has positive mean margin delta. That is evidence to
continue promotion work, not permission to overwrite the canonical archive or
submit to Kaggle.
