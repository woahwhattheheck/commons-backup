# Intersection contract schema

Every key is mandatory. Unknown keys are rejected. `schema_version` is currently `1`.

```json
{
  "schema_version": 1,
  "panel_id": "immutable-human-readable-id",
  "parent_report_sha256": "64-lowercase-hex",
  "opponents": ["arlene", "apex"],
  "seeds": [2611092301, 2611092303],
  "seats": [0, 1],
  "expected_cells": 8,
  "policy": {
    "require_parent_promote": true,
    "min_positive_margin_pair_fraction": 1.0,
    "max_negative_opponent_seat_own_strata": 0,
    "max_negative_opponent_seat_margin_strata": 0,
    "min_worst_pair_margin_delta": 0.0,
    "min_worst_opponent_seat_own_mean": 0.0,
    "min_worst_opponent_seat_margin_mean": 0.0
  }
}
```

`expected_cells` must equal `len(opponents) × len(seeds) × 2`, and seats must be exactly `[0, 1]`.

Policy semantics:

- `require_parent_promote`: must be literal `true`; the parent must say `PROMOTE`, carry a non-empty check list, and have every check pass. A companion gate cannot escalate `REJECT` or `INVALID`.
- `min_positive_margin_pair_fraction`: minimum fraction of `(opponent, seed)` pairs whose mean margin delta across both candidate seats is strictly positive.
- `max_negative_opponent_seat_own_strata`: maximum count of `(opponent, candidate_seat)` own-cash means below zero.
- `max_negative_opponent_seat_margin_strata`: maximum count of `(opponent, candidate_seat)` margin means below zero.
- `min_worst_pair_margin_delta`: optional floor for the worst two-seat pair mean margin; use `null` to report without gating.
- `min_worst_opponent_seat_own_mean`: optional floor for the worst opponent×seat own-cash mean.
- `min_worst_opponent_seat_margin_mean`: optional floor for the worst opponent×seat margin mean.

The separate schema preserves historical parent contracts and decisions exactly; no hidden default is injected into them.
