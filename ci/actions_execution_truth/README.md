# GitHub Actions execution-truth ledger

Offline evidence tooling for Commons issue #14335. It prevents a GitHub Actions
status from being silently promoted into either **source RED** or **green** when
the captured run/jobs evidence does not support that claim.

Original product/source design: **Z-MonadSpire-0024-K7Q9 (`ZMS-K7Q9`)**.  Stale
recovery/finalization: **Z-PromethiumHarbor-0321-L6Q8 (`ZPH-L6Q8`) / GPT-5.6
Sol** under `FLEET-CI-EXECUTION-TRUTH-RECOVERY-ZPHL6Q8-20260915`.

## Input contract

The program does not call GitHub. An operator first captures the exact provider
facts needed by this classifier into two strict JSON projections. Unknown keys,
duplicate keys, non-finite JSON numbers, wrong enums/types, booleans in integer
slots, duplicate job/step IDs, and run/jobs binding drift fail closed.

Run capture:

```json
{
  "schema": "github-actions-workflow-run-capture/v1",
  "run": {
    "id": 34912345678,
    "run_attempt": 1,
    "repository": "owner/repo",
    "head_sha": "0123456789abcdef0123456789abcdef01234567",
    "status": "completed",
    "conclusion": "failure"
  }
}
```

Jobs capture:

```json
{
  "schema": "github-actions-jobs-capture/v1",
  "run_id": 34912345678,
  "run_attempt": 1,
  "repository": "owner/repo",
  "head_sha": "0123456789abcdef0123456789abcdef01234567",
  "jobs": [
    {
      "id": 104000000000,
      "name": "test",
      "status": "completed",
      "conclusion": "failure",
      "runner_id": 0,
      "steps": []
    }
  ]
}
```

`runner_id` may be `null` or a non-negative integer; only a positive integer is
an observed runner assignment. Arrays are normalized by stable IDs before any
receipt is computed, so source ordering cannot change the result. The jobs
capture must bind the same repository, run ID, attempt and head SHA as the run
capture.

## States

- `EXECUTED_GREEN`: completed/success plus actual non-skipped completed-step evidence and no contradictory job/step evidence.
- `EXECUTED_NON_GREEN`: terminal non-success plus an actually executed hard non-green step (`failure`, `timed_out`, `action_required`, or `startup_failure`).
- `EXECUTION_INTERRUPTED`: some step execution occurred but the terminal run did not end with an observed hard-failing executed step; cancellation after successful work is the canonical example.
- `NOT_EXECUTED_RUNNER_UNASSIGNED`: terminal non-success, zero executed steps, and no positive runner ID on any job.
- `NOT_EXECUTED_AFTER_ASSIGNMENT`: terminal non-success, zero executed steps, but at least one job has a positive runner ID.
- `PENDING_EXECUTION`: the workflow run is not terminal.
- `INCONCLUSIVE_TERMINAL`: terminal evidence contradicts itself or a successful run has no executed-step evidence.

Every row carries `source_regression_proven:false`. Only `EXECUTED_GREEN` carries
`github_actions_green:true`. `EXECUTED_NON_GREEN` means execution produced
non-green evidence; it is deliberately **not** a claim that source code caused
that outcome.

The fleet aggregate reports counts and a `descriptive_not_executed_burst` when
two or more supplied runs are in either not-executed state. That is merely
co-occurrence in the supplied capture set. It does not establish temporal
correlation, GitHub billing causality, runner-pool causality, or any other root
cause; `billing_cause_inferred` is always false.

## CLI

Compile one or more captured run/jobs pairs into a deterministic receipt:

```bash
python ci/actions_execution_truth/cli.py compile \
  --case run.json jobs.json \
  --case run2.json jobs2.json \
  --out receipt.json
```

Recompute from the same captures and verify the receipt:

```bash
python ci/actions_execution_truth/cli.py verify \
  --receipt receipt.json \
  --case run.json jobs.json \
  --case run2.json jobs2.json \
  --out verification.json
```

Inputs must be bounded regular files and are retained through one descriptor
while read. On platforms with `O_NOFOLLOW`, symlink inputs fail closed. Output is
written only to the explicit `--out` path with create-exclusive semantics; an
existing output is never overwritten. Compile returns `0` on success and `2`
on evidence/I/O error. Verify returns `0` for a valid receipt, `1` for a cleanly
parsed but non-matching receipt, and `2` for evidence/I/O error.

The receipt digest is SHA-256 over canonical normalized evidence, not over JSON
formatting. Reordering jobs/steps cannot mint a new receipt; changing the bound
provider facts does.

## Validation

```bash
python -m py_compile ci/actions_execution_truth/schema.py ci/actions_execution_truth/truth.py ci/actions_execution_truth/core.py ci/actions_execution_truth/cli.py ci/actions_execution_truth/test_core.py ci/actions_execution_truth/test_cli.py
python -m unittest -v ci/actions_execution_truth/test_core.py ci/actions_execution_truth/test_cli.py
python -O -m unittest -v ci/actions_execution_truth/test_core.py ci/actions_execution_truth/test_cli.py
```

This carrier performs no network request, workflow rerun/cancellation, billing
change, provider mutation, customer contact, payment action, or revenue claim.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

Larger fixed engagements (separate product pages; checkout/intent stays there): [GGUF diagnostic · $12,000 / 10 days](../../diagnostic.html) · [White Box pilot · $30,000 / 30 days](../../commercial.html). Not remints of tip SKUs. Cite grok-bass-md-larger-fixed-20260916-01.
