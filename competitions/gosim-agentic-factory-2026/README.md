# GOSIM Agentic Factory 2026 — internal readiness harness

This directory is an **offline internal comparison harness** for the GOSIM Agentic Factory competition lane. It does not register, submit, contact organizers, spend API/cloud money, or claim qualification, ranking, prize, acceptance, or revenue.

The public competition material discusses executable agent factories and evaluation pressure around functional test success, token efficiency, and completion time. The scorer therefore preserves those raw axes while deliberately calling its aggregate an **internal readiness score**. It is **not an official GOSIM score and is not a prediction of organizer ranking**.

## Evidence contract

Each run is a strict JSON object under `gosim-agentic-factory-readiness/v1`. A run binds:

- immutable `task_id` + `trial_id`;
- harness revision and model label;
- canonical millisecond UTC `started_at` / `finished_at` timestamps;
- `wall_clock_ms`, which must equal the timestamp interval exactly;
- integer input/output/cache token counts;
- integer test total/pass/fail counts where pass + fail = total;
- SHA-256 digests for the task specification, artifact manifest, and raw trace.

Unknown fields, duplicate JSON keys, bool/int aliases, negative or oversized counts, malformed/noncanonical timestamps, mismatched wall-clock evidence, impossible test totals, malformed digests, non-finite JSON, and reused trial identities fail closed.

The digest fields are evidence references. This harness never invents benchmark execution records; an executor must supply the real trace/artifact/task digests and measured timing/token/test data.

## Internal score policy

`score_policy.json` is an operator-selected policy, not an organizer policy. The default example gives correctness 80% of the internal score and gates the remaining token/time efficiency terms behind an 80% correctness floor. Fixed-point integers are used so repeated compilation is byte-stable.

Regression gates are intentionally stronger than one aggregate number:

- each baseline task is comparable only to the same `task_id`, exact `task_spec_sha256`, and test cardinality; a same-name task with a changed generation fails the gate;
- a candidate or baseline that mixes multiple task generations under one `task_id` is rejected as ambiguous;
- correctness regressions fail before token/time savings are considered;
- when correctness is equal, token growth beyond the policy tolerance fails;
- when correctness is equal, wall-time growth beyond the policy tolerance fails;
- missing candidate tasks fail.

A cheaper/faster candidate cannot hide a correctness loss or substitute an easier same-name task inside the aggregate.

## Outputs

`compile` emits canonical JSON plus a Markdown projection. The JSON contains:

- raw validated run evidence;
- raw public-axis metrics;
- the internal readiness score;
- per-task Pareto status (maximize correctness, minimize tokens and time);
- median/worst summaries per structurally keyed harness/model configuration;
- optional baseline regression-gate results;
- a SHA-256 receipt covering policy, exact run evidence, optional baseline evidence, and report core.

Input ordering does not affect output bytes.

## Usage

```bash
cd competitions/gosim-agentic-factory-2026
python harness_score.py compile \
  --runs example_runs.json \
  --policy score_policy.json \
  --output-json /tmp/gosim-report.json \
  --output-md /tmp/gosim-report.md

python harness_score.py verify \
  --runs example_runs.json \
  --policy score_policy.json \
  --report /tmp/gosim-report.json
```

With a previously frozen baseline:

```bash
python harness_score.py compile \
  --runs candidate_runs.json \
  --baseline frozen_baseline.json \
  --policy score_policy.json \
  --output-json /tmp/gosim-report.json \
  --output-md /tmp/gosim-report.md
```

Exit code `2` means the baseline regression gate failed and no report files are created. Output files are create-exclusive so an existing report is never silently overwritten.

## Validation

```bash
python -m unittest -v
python -O -m unittest -v
```

The same suite must pass with assertions optimized away; contract enforcement lives in production code, not `assert` statements.

## Authority ceiling

This carrier is readiness tooling only. It has no provider credentials or network write path and grants no authority to register or submit, change competition settings, contact GOSIM, spend money/tokens, commit travel, claim organizer acceptance, claim a prize, or recognize revenue.
