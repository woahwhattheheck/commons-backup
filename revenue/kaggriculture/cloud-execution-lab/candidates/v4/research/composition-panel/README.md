# V4 cross-feature composition panel

One research tool on `main:candidates/v4/research/composition-panel`. This is not
another V4 integration branch, policy, evaluator, result reporter, or gameplay
activation. It generates **complete JSON test configurations** for an existing
runner. It never imports or runs an agent and does not edit production config.

Individually green feature lanes can collide when combined. Testing the baseline
and each isolated toggle never exercises a two-toggle collision. This planner
preserves those probes and adds configurations covering every **feasible unary
and pairwise Boolean assignment**, including OFF/OFF, OFF/ON, ON/OFF and ON/ON.
A pairwise panel is a test-selection technique, not a proof of correct gameplay:
three-way interactions, state trajectories, timeout effects and economic regressions
can remain undetected.

## Executed current-source exercise

The bundled declaration copies the 13 explicit Boolean keys from production
`TITAN-CONFIG.json` Git blob `3a3bef83899d3010fad623b628d9e95d9978111b`.
Other config fields remain unchanged. Its constraints come from the read
`Features.__post_init__` in runtime blob
`b952c9c228ecbde592bf3d2df01638677abb0d24`:

- `terminal_route` excludes `redundant_hire`, `fourth_quadrant`,
  `idle_fertilizer` and `crop_release` in this explicit feature set.
- `terminal_history` stays false because the baseline does not supply hypotheses.
- The consumer remains frozen; unswept spatial options retain their false defaults.

The local exercise produced **18 configurations covering 309 feasible unary/pair
obligations**, with 29 infeasible obligations explicitly reported. All 8,192
Boolean combinations were checked against the literal `Features` class excerpt:
2,176 satisfy this constructor contract. Constructor legality is not economic
acceptance. The excerpt is test-only; it does not authenticate a later runtime.
All emitted cases also passed that constructor. No game episode was run and no
score, speedup, feature activation or leaderboard improvement is claimed.

## Run

```sh
python composition_panel.py current-production.spec.json --output panel.json
python composition_panel.py current-production.spec.json --audit panel.json --output audit.json
python -m unittest -v test_composition_panel
python -O -m unittest -v test_composition_panel
```

A custom spec is a JSON object with integer `schema_version: 1`, `base_config`,
and a list of 1..48 distinct `features`. Every swept key must already exist as a
literal Boolean in the supplied base. Optional `requires` rows `[a,b]` mean
`a => b`; `excludes` rows mean not both ON; `fixed` pins explicit Boolean values.
Optional `provenance` is included in the fingerprint. Unknown spec fields,
nonfinite JSON, duplicate JSON keys and invalid baseline assignments fail.
Only unary/binary Boolean constraints are supported; do not approximate a
higher-order requirement as pairwise constraints without validating equivalence.

The spec fingerprint binds the normalized declaration, including unswept config
and provenance. Each case uses a full SHA-256 ID binding that spec and assignment.
IDs identify configurations, not actual execution or independent samples.
Changing feature order or duplicating/reordering equivalent constraints does not
change the plan. Equal-case tie breaking never depends on hash/set iteration.

## Selection and audit

An exact iterative 2-SAT solver determines which assignments are feasible under
**the declared constraints only**. There is no exponential full-configuration
enumeration in the planner. Satisfying witnesses plus deterministic diverse
witnesses feed greedy set cover. The baseline and each legal exact isolated
toggle are mandatory. An illegal isolated toggle is reported, not silently
replaced by a multi-feature dependency closure. Feasible dependent ON/ON pairs
still receive coverage through other cases.

This is not a minimum-size optimizer. `--max-cases N` caps emitted configurations.
Insufficient budget returns `INCOMPLETE_BUDGET` with missing obligations and
mandatory probe IDs, never a green coverage claim. Audit reconstructs all
obligations and checks actual cases independently of the plan's stated status
and audit metadata. It rejects altered identities, non-Boolean swept values,
changed keys, unswept type/value drift and duplicate configurations. The tests
compare solver feasibility to an independent exhaustive Boolean oracle on
2,256 pin/constraint cases and independently enumerate panel coverage.

CLI exit codes: **0** complete declared coverage; **1** valid but incomplete
coverage; **2** invalid input or I/O failure. These are coverage codes, never
performance verdicts. Invalid input does not overwrite an existing output.
Output cannot alias input files or the planner; successful writes are atomic.

## Consumer handoff: one V4, existing runners

Before running, verify that the actual package/config ABI matches the supplied
source pins. The planner does not fetch Git or verify provenance claims. A drifted
runtime requires a refreshed declaration and constructor checks. Do not feed
legacy `r04_*` donor flags into this production-ABI exercise, nor execute the old
materializer against the new runtime. New composed V4 keys require a new explicit
spec matching the generated package, not automatic inclusion from donor receipts.

For each case, use its `config` unchanged in an isolated agent instance, keep the
same declared opponents/seeds, run both seats, and retain case ID, artifact hashes,
activation counts, failures and action timings. Feed each case's paired game
results separately to the existing `repairs/tooling/paired-panel` auditor and
`research/paired-field-gate`. Do not pool different configurations into one arm,
count pairwise assignments as independent games, or reuse mutable agent state
across cases. Match the same baseline across cases deliberately; its repeated
use does not create additional independent baseline evidence.

Only real matched results can decide which combinations belong in the single V4.
This delivery adds no automatic runner demand, default flip, production mutation,
archive, workflow or Kaggle submission.
