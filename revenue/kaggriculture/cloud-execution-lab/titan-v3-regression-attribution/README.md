# TITAN V3 regression attribution

Operation: `titan-v3-causal-regression-attribution-20260910-sol-pro-01`

This lane closes a gap between the existing paired-game promotion gates and the
reported V2 regression. The paired gates correctly decide whether terminal
`GAMES.jsonl` evidence is complete and whether a candidate passes a declared
policy. Terminal rows cannot identify the first behavior that caused a loss.
This tool consumes an **ordered build lineage**, exact terminal ledgers, and
step-complete action traces to report:

1. the first declared comparison that fails the regression policy;
2. the exact config paths changed at that boundary;
3. the first action difference in every affected `(opponent, seed, seat)` cell;
4. the earliest divergence step and whether the first change is market-only,
   worker-only, farmer-only, unit-only, or mixed;
5. the first differing market/hand row and changed runtime diagnostics; and
6. every build's comparison to the anchor, so a later recovery is not mistaken
   for monotone behavior.

It does not modify `main.py`, select a release, upload to Kaggle, or turn a small
panel into a leaderboard claim. `titan-v3-paired-game-gate/gate.py` and
`dual_predecessor_gate.py` remain the promotion authorities.

## Why this is needed now

The canonical config changed in an ordered prefix after the measured
redundant-hire checkpoint:

| Prefix | Commit | Config Git blob | Newly enabled behavior |
| --- | --- | --- | --- |
| P0 | `b1ae926a0f4abb48cd388c969ed4d52a0a3b36eb` | `00ef5b6d14a35b892ab71a50a25d1c1587fe794d` | `redundant_hire` |
| P1 | `ff180abbad4c5dd8cbd102d3ddb20aad29f45aa8` | `4037bc851c151a356abd871f933b8222fb9e10ac` | `market_pressure` |
| P2 | `9811fb45b1f78fc9779246d68e776661f1f42d2e` | `41db678812e7b197fd658ec0352c1ea742cc6e77` | `operating_stock` |
| P3 | `1ec36ca1638e53be399d85da71506941fece6e08` | `18de23d2a2572a11e1fe5572b098b3f0a85a5d4a` | `idle_fertilizer` |
| P4 | `25ee75280489a94e781d2779abded879b51308f5` | `0ca9528ea40ce986747785cb8fcb7aed9ca40346` | `crop_release` |
| P5 | `c1e83252491485fba9af437b511a201dd78ecd0e` | `3a3bef83899d3010fad623b628d9e95d9978111b` | `early_capital` |

A historical-prefix panel locates the commit boundary, but each commit may also
contain source changes. `CURRENT-LINEAGE.json` therefore specifies a second,
stronger experiment on one current source closure: neutralize the five suspect
flags, enable each flag alone, and compare the fully enabled current config.
That seven-arm matrix separates config-mediated effects from source-version
drift. Pairwise interaction arms should be built only after the single-arm
screen identifies the active factors.

## Materialize the ablation matrix

`materialize_ablation_matrix.py` removes the most error-prone manual step. It
requires the fully enabled current `TITAN-CONFIG.json`, the immutable current
source closure, and its exact commit. It then publishes one atomic directory
containing seven byte-distinct configs plus `ABLATION-MATRIX.json`:

```bash
python3 materialize_ablation_matrix.py \
  --base-config /build/TITAN-CONFIG.json \
  --source-closure /build/current-source.tar.gz \
  --source-commit <40-or-64-hex-commit> \
  --expected-source-closure-sha256 <64-hex-sha256> \
  --output-dir /evidence/titan-v3-ablation-matrix
```

The arms are `neutral-current-source`, five single-feature arms, and
`full-current`. The generated comparison graph anchors every non-neutral arm
directly to `neutral-current-source`; it never treats one single-feature arm as
the predecessor of another. The materializer verifies that all non-suspect
config values are preserved, every input suspect flag is boolean and currently
enabled, every generated diff is exact, and every config is byte-distinct. The
source closure is streamed into SHA-256 rather than loaded into memory.

Publication is all-or-nothing: an existing output, symlinked input, symlinked
output target, duplicate JSON key, non-finite value, closure hash mismatch, or
invalid source identity exits `2` without a partial matrix. The emitted
`ABLATION-MATRIX.json` carries source/config receipts and the exact six
neutral-anchored comparisons to copy into the attribution evidence manifest.
It does not build the seven executable closures; the executor must package each
config with the bound source and then bind those complete closures in the
attribution manifest.

## Trace contract

The manifest declares a complete Cartesian grid and an inclusive trace step
interval. Every build must contain exactly one terminal row per game cell and
exactly one trace row per cell/step.

Terminal `GAMES.jsonl` row:

```json
{"opponent":"arlene","seed":101,"candidate_seat":0,"status":"complete","scores":[100.0,90.0]}
```

Step trace row:

```json
{
  "opponent": "arlene",
  "seed": 101,
  "candidate_seat": 0,
  "step": 250,
  "status": "complete",
  "observation_sha256": "<64 lowercase hex>",
  "action": {"farmer":"PASS","hands":["PASS"],"market":[["SELL","MELON",6]]},
  "diagnostics": {"producer":"frozen","stage":"market_pressure"}
}
```

`diagnostics` is optional. Actions and diagnostics are canonicalized with sorted
JSON keys only for comparison and hashing; the original action structure is not
rewritten.

### Causal alignment rule

For each paired cell, observations must remain byte-identical through the first
action difference. If observation hashes differ before any action difference,
the run is invalid: the engine, opponent stream, seed, seat, reset behavior, or
trace capture is not actually aligned. If terminal scores differ but all traced
actions are identical, the run is also invalid rather than attributed to TITAN.
After the first action difference, downstream observations may diverge and are
not used to invent additional independent causes.

This makes the reported first divergence causal under the supplied deterministic
runner boundary. It does not prove that the changed action is globally optimal
or that every later score delta is mediated only by the reported config key.

## Manifest

All paths are relative to the manifest unless absolute. Every referenced file is
a regular, non-symlink input with an explicit SHA-256 binding. Engine and runner
are observed artifacts, not free-form labels. Each build artifact must represent
the complete executable closure and must be byte-distinct from every other build.

```json
{
  "schema_version": 1,
  "panel_id": "titan-v3-ablation-dev-01",
  "engine": {"path":"engine.bundle","sha256":"<64 hex>"},
  "runner": {"path":"runner.bundle","sha256":"<64 hex>"},
  "grid": {
    "seeds": [101, 102],
    "opponents": ["arlene", "apex"],
    "seats": [0, 1],
    "trace_step_start": 0,
    "trace_step_end": 718
  },
  "policy": {
    "min_mean_own_delta": -100.0,
    "min_mean_margin_delta": -100.0,
    "max_result_regressions": 0,
    "max_new_losses": 0,
    "min_worst_cell_own_delta": -2000.0
  },
  "comparisons": [
    {"id":"neutral-vs-market","before":"neutral-current-source","after":"market-pressure-only"}
  ],
  "builds": [
    {
      "name": "neutral-current-source",
      "source_commit": "<40-or-64 hex>",
      "artifact": {"path":"neutral.tar.gz","sha256":"<64 hex>"},
      "config": {"path":"neutral-config.json","sha256":"<64 hex>"},
      "games": {"path":"neutral.GAMES.jsonl","sha256":"<64 hex>"},
      "trace": {"path":"neutral.TRACE.jsonl","sha256":"<64 hex>"}
    },
    {
      "name": "market-pressure-only",
      "source_commit": "<same current source commit>",
      "artifact": {"path":"market.tar.gz","sha256":"<64 hex>"},
      "config": {"path":"market-config.json","sha256":"<64 hex>"},
      "games": {"path":"market.GAMES.jsonl","sha256":"<64 hex>"},
      "trace": {"path":"market.TRACE.jsonl","sha256":"<64 hex>"}
    }
  ]
}
```

Policy is evaluated on each explicitly declared comparison. If `comparisons` is
omitted, consecutive builds are the default comparison plan. The report also
emits all consecutive transitions and every build versus the first anchor as
diagnostics, but only the declared plan controls the top-level verdict. This is
important for independent ablation arms: compare each single-feature artifact
directly to the neutral current-source anchor instead of comparing one single
arm to another. W/T/L regression is calculated from the candidate seat's own
and rival terminal scores. A comparison is `REGRESSION` if any declared floor
or count limit fails. The report preserves the ten worst cells rather than
hiding a seat/opponent failure behind a global mean.

## Run

```bash
python3 regression_attribution.py \
  --manifest /evidence/ATTRIBUTION-MANIFEST.json \
  --report /evidence/ATTRIBUTION-REPORT.json
```

Exit codes:

- `0` — complete, aligned evidence with no policy-regressing transition;
- `2` — invalid identity, hash, schema, grid, trace, or causal alignment;
- `3` — valid evidence and at least one policy-regressing transition.

Output replacement is atomic. Reports are deterministic for the same immutable
inputs.

## Recommended swarm execution

Use one fresh development seed registry for all seven current-source arms and
both seats. Start with at least two public opponents plus the strongest retained
frozen control. The fastest useful screen is the neutral arm, five single-feature
arms, and full current arm over the same small grid. Then:

1. rerun the first bad single arm and neutral anchor on a larger disjoint grid;
2. add pairwise interaction arms only among factors that changed actions;
3. retain action traces only through the first divergence for analysis, while
   preserving full trace files as immutable evidence inputs; and
4. submit only an exact archive that subsequently passes the existing complete
   paired gate against both V1 and V2 on disjoint holdout seeds.

Do not infer innocence from a feature that never activates in a tiny panel. The
report distinguishes “no action divergence” from “changed actions with no score
regression,” which keeps activation coverage visible.

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 \
  python3 -m unittest -v \
    test_regression_attribution.py \
    test_materialize_ablation_matrix.py
python3 -m compileall -q .
```

Analyzer result: **22/22 passed**. Coverage includes declared comparison graphs,
first-regression selection, anchor comparisons, market-row attribution, diagnostic
changes, observation drift before action, score drift without action, missing/extra/duplicate cells,
missing/duplicate trace rows, hash drift, duplicate JSON keys, NaN, artifact
aliasing, invalid commits, boolean seats, nested config diffs, deterministic
atomic reports, CLI exit codes, and symlink substitution.

The matrix materializer adds **16/16 passing tests** for exact seven-arm output,
neutral-anchored comparisons, deterministic bytes, preservation of non-suspect
config, closure custody, atomic publication, CLI exit codes, duplicate keys,
invalid flags/identities, existing destinations, and symlink substitution.
Combined result: **38/38 passed**.
