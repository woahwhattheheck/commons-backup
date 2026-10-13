# Paired-panel completeness preflight

Canonical home: `main:revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/tooling/paired-panel/`.
ASTRA-PAIRGRID support tooling; no alternative V4, gameplay key, production import,
legacy materializer, default change or submission. The adjacent `delta-evidence/`
reporter retains ownership of score statistics and promotion-policy evaluation.

## What this closes

Matching the baseline and candidate rows that happen to be present cannot reveal
an entire missing seed/seat/opponent pair. This auditor compares both arms against
a separately declared Cartesian panel. It rejects omitted pairs, single missing
arms, failed games, unexpected cells, duplicate attempts, artifact-pin drift and
reused confirmation seeds. A successful but disastrous score remains in the
export: complete evidence is not the same thing as a winning candidate.

There is no best-attempt/last-attempt selection. A timeout plus a successful retry
is still an invalid panel input, rather than permission to erase the failure.
Keep the original attempt log. Any replacement experiment needs an explicit new
plan and a documented runner policy; this tool does not choose that policy.

## Runner contract

Create and preserve the plan before evaluating or inspecting outcomes. Do not
infer its expected grid from the surviving result rows. The exact plan fields are:

| Field | Required value |
|---|---|
| `schema` | `titan-paired-panel/v1` |
| `panel_id` | Nonempty, unpadded string |
| `purpose` | `explore` or `confirm` |
| `engine_sha256`, `environment_sha256` | Lowercase 64-character SHA-256 digests |
| `baseline_sha256`, `candidate_sha256` | Digests of the complete executed agent artifacts |
| `opponents` | Nonempty object mapping distinct opponent IDs to artifact digests |
| `seeds` | Nonempty, unique, nonnegative integer seeds; booleans forbidden |
| `seats` | Exactly both seats, `[0, 1]` or `[1, 0]` |
| `prior_plan_sha256` | Unique prior-plan fingerprints; nonempty for confirmation |

Agent pins must bind configuration as well as code. Pin the actual package or a
deterministic complete artifact manifest, not a floating branch or one helper.
The environment digest should bind all shared environment/evaluator settings.
Compute the plan fingerprint with `plan_digest(plan)` from this module: sorted,
compact, ASCII-escaped JSON of the complete plan value, hashed with SHA-256.
Whitespace/key formatting in the saved JSON does not affect that fingerprint.

Each JSONL row requires `plan_sha256`, `arm` (`baseline` or `candidate`),
`opponent`, `seed`, `candidate_seat`, `status`, `agent_sha256`, `opponent_sha256`,
`engine_sha256`, and `environment_sha256`. Status is `complete`, `error`, `timeout`
or `cancelled`. A complete row also requires `scores: [seat0, seat1]`: these are
player-ordered scores, NOT own/rival order. Failed status is never usable evidence.
Optional fields are `activations` (lane-name to nonnegative integer count),
`trace_sha256`, and `error` (not allowed on a complete row). Unknown fields,
ambiguous aliases, duplicate JSON keys, booleans in numeric domains and nonfinite
scores reject. Missing activation counts stay missing, not invented zeroes.

Confirmation requires the exact content-pinned prior manifests via repeated
`--prior-plan`. Include the transitive closure of their declared history both in
the current plan's pins and as input files. Seed overlap with ANY supplied prior
plan rejects, even under a different opponent or seat. This conservative rule
prevents relabeling a reused world as fresh confirmation; it is not proof of
statistical independence and cannot discover undeclared experiments.

## Run

From this directory, after the existing evaluator has written strict result rows:

```sh
python audit_paired_panel.py PLAN.json RESULTS.jsonl \
  --paired-out paired.json > coverage.json && \
python ../delta-evidence/v31_delta_distribution_report.py paired.json
```

For confirmation, append one `--prior-plan PRIOR.json` per pinned prior manifest
to the audit command. Exit **0** means complete declared coverage/provenance;
exit **2** means invalid or incomplete evidence. No economic verdict is implied.
Use `&&` or explicitly check the exit code: on failure an existing `paired.json`
is deliberately left unchanged and must NOT be reused as this run's output.
Successful writes are atomic and cannot replace an input path.

The export uses nested `baseline/candidate: {"scores": [seat0, seat1]}` inside
`cells`, avoiding the reporter's historical flat-score alias ambiguity. It also
retains the plan fingerprint and full manifest. Raw JSONL logs remain the source
for failures, trace pins and attempt details; preserve them alongside the export.

## Executed validation

```sh
python -m py_compile audit_paired_panel.py test_audit_paired_panel.py
python -m unittest -v test_audit_paired_panel
python -O -m unittest -v test_audit_paired_panel
python run_mutation_checks.py
```

Python 3.13.5: **34/34 normal, 34/34 optimized, zero skips**. Each mode includes
64 individual missing-row cases and 128 deterministic row-order permutations.
Seven deliberate fault variants are caught in both modes (14 mutant executions);
the mutation script changes temporary copies only and rejects import/syntax
failures as false mutation receipts. `VALIDATION.json` pins the tested source,
tests and mutation runner and lists the exact checks.

All test games, scores, worlds and digests are SYNTHETIC. No actual game panel,
hosted CI, full sibling reporter execution or current production materialization
was run for this receipt. The exporter matches the inspected nested-score and
activation-map interface; that is not a claim of end-to-end runner adoption.
Declared hashes do not attest that an executor truly ran those bytes, and this
tool cannot prove when a manifest was created. Enforce pre-registration and
honest artifact custody in the runner process, not by trusting a headline here.

Durable coordination claim: existing PR #12646, comment 5642716165. This package
does not alter that reporter or compete with its seat/schema repair owners.
