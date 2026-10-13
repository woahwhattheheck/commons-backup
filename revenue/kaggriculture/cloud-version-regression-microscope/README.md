# TITAN three-way regression delta microscope

This is an additive diagnostic consumer for the owner-reported V2 regression.
It does **not** replace the shared paired-evidence causal auditor, run games,
choose feature defaults, or emit an `ADVANCE`/promotion decision.

Given an upstream causal-gate `PASS` receipt plus the exact same
`opponent × seed × candidate-seat` cells for V1, V2, and V3, it reports:

- every V1→V2 candidate-own cash or W/T/L regression cell;
- every V2→V3 repair that reaches at least the original V1 result;
- unrepaired V2 regressions and newly introduced V3 regressions;
- the first tested-seat returned-action divergence for each regression;
- repeated harmful divergence signatures, ranked by own-cash damage.

The report is diagnostic only. It exists to turn “V2 regressed” into concrete
returned-action culprit families that policy owners can repair and retest.

## Exact input boundary

```json
{
  "schema": "titan-three-way-regression-microscope/v1",
  "expected_action_count": 719,
  "expected_cells": [
    {"opponent": "Arlene", "seed": 9921001, "seat": 0},
    {"opponent": "Arlene", "seed": 9921001, "seat": 1}
  ],
  "upstream_causal_gate": {
    "tool": "SOL-AUDITOR paired-evidence causal gate",
    "schema": "titan-paired-evidence/v1",
    "status": "PASS",
    "receipt_sha256": "..."
  },
  "three_way": ["v1", "v2", "v3"],
  "versions": {
    "v1": {
      "identity": {
        "source_sha256": "...",
        "archive_sha256": "...",
        "config_sha256": "..."
      },
      "cells": [
        {
          "opponent": "Arlene",
          "seed": 9921001,
          "seat": 0,
          "state": "complete",
          "phase": "finalize",
          "engine_sha256": "...",
          "opponent_sha256": "...",
          "tested_seat_actions": ["... exactly 719 returned actions ..."],
          "tested_action_sha256": "...",
          "terminal": {
            "own_cash": 100000,
            "rival_cash": 90000,
            "terminal_world_sha256": "...",
            "full_trace_sha256": "..."
          }
        }
      ]
    },
    "v2": {"identity": {"source_sha256": "...", "archive_sha256": "...", "config_sha256": "..."}, "cells": []},
    "v3": {"identity": {"source_sha256": "...", "archive_sha256": "...", "config_sha256": "..."}, "cells": []}
  }
}
```

All identity and trace fields must be lowercase 64-hex SHA-256 values. The
production lifecycle is fixed at exactly 719 returned actions. `expected_cells`
is mandatory, duplicate-free, and must contain both seats for every declared
opponent/seed pair; each version must equal that literal grid. The tested
action hash is mandatory and recomputed from the supplied sequence. Wrapped
action rows must carry continuous `step=0..718` and the correct tested seat.

The upstream causal gate is authoritative. This consumer still repeats narrow
defense-in-depth invariants needed for safe cross-version localization:
action identity cannot coexist with terminal-world, trace, or score drift; an
action difference cannot coexist with an identical full trace; engine and
opponent bytes must match.

## Run

```bash
python3 -B regression_microscope.py evidence.json \
  --json-out three-way-regression.json \
  --markdown-out three-way-regression.md
python3 -B -m unittest -v test_regression_microscope.py
```

Exit code `2` means the input is not exact enough for attribution. No partial
receipt is emitted.
