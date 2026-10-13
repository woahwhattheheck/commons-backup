# Contract and evidence schema

Both documents use `schema_version: 1`. Unknown or missing top-level keys are
rejected so a typo cannot silently disable a gate.

## CONTRACT.json

```json
{
  "schema_version": 1,
  "panel_id": "immutable-human-readable-id",
  "baseline_name": "canonical-3b4b",
  "candidate_name": "g01-e11-only",
  "seeds": [2611061001, 2611061002],
  "opponents": ["arlene", "apex"],
  "seats": [0, 1],
  "expected_cells": 8,
  "provenance": {
    "engine_commit": "40-or-64-hex-object-id",
    "engine_sha256": "64-hex-source-or-bundle-digest",
    "runner_commit": "40-or-64-hex-object-id",
    "runner_sha256": "64-hex-runner-digest",
    "baseline_artifact_sha256": "64-hex-archive-digest",
    "candidate_artifact_sha256": "64-hex-archive-digest"
  },
  "policy": {
    "min_mean_own_delta": 0.0,
    "min_median_own_delta": 0.0,
    "min_mean_margin_delta": 0.0,
    "min_positive_cell_fraction": 0.5,
    "min_positive_pair_fraction": 0.5,
    "max_result_regressions": 0,
    "max_baseline_win_regressions": 0,
    "max_new_losses": 0,
    "max_negative_opponent_strata": 0,
    "max_negative_seat_strata": 0,
    "min_worst_cell_own_delta": null,
    "require_any_change": true
  }
}
```

`expected_cells` must equal `len(seeds) × len(opponents) × 2`. Seeds and
opponents must be non-empty and unique. Seats must contain exactly 0 and 1.

All policy values are mandatory. This prevents version changes or hidden
defaults from changing a historical promotion decision.

- `min_mean_own_delta`: arithmetic mean candidate-own-cash delta over cells.
- `min_median_own_delta`: median candidate-own-cash delta over cells.
- `min_mean_margin_delta`: mean change in `(own cash - rival cash)`.
- `min_positive_cell_fraction`: fraction of individual cells with own delta > 0.
- `min_positive_pair_fraction`: fraction of `(opponent, seed)` pairs whose mean
  own delta across the two candidate seats is > 0.
- `max_result_regressions`: any W→T/L or T→L cell.
- `max_baseline_win_regressions`: baseline W becoming T or L.
- `max_new_losses`: baseline W/T becoming candidate L.
- `max_negative_opponent_strata`: opponent groups with mean own delta < 0.
- `max_negative_seat_strata`: seat groups with mean own delta < 0.
- `min_worst_cell_own_delta`: optional floor on the worst cell; `null` disables
  only this one check.
- `require_any_change`: reject byte-different candidates whose panel scores are
  completely identical under the declared grid.

Thresholds are experiment policy, not universal truth. Freeze them before
opening results. Do not relax them after observing development outcomes.

## PROVENANCE.json

```json
{
  "schema_version": 1,
  "panel_id": "immutable-human-readable-id",
  "provenance": {
    "engine_commit": "same expected value",
    "engine_sha256": "same expected value",
    "runner_commit": "same expected value",
    "runner_sha256": "same expected value",
    "baseline_artifact_sha256": "same expected value",
    "candidate_artifact_sha256": "same expected value"
  },
  "exact_command": "redacted-of-secrets but otherwise exact execution command"
}
```

Every provenance value must equal the predeclared contract. The gate also hashes
both JSON documents and both JSONL inputs into its report, so the decision binds
to exact evidence bytes.

## GAMES.jsonl

Each nonblank line must be a unique object with at least:

```json
{"opponent":"arlene","seed":2611061001,"candidate_seat":0,"status":"complete","scores":[12000,11000]}
```

Additional evaluator fields are preserved in the source file but not trusted as
promotion inputs. A status other than exactly `complete`, malformed score, NaN,
unknown grid cell, duplicate row, or missing row invalidates the whole panel.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
