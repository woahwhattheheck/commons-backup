# TrafficFlowBench 2026 — source-safe competition carrier

This carrier prepares reusable engineering for the **2026 IEEE Big Data Cup — TrafficFlowBench** without joining Kaggle, accepting rules, downloading competition data, submitting, or claiming any official score/rank/prize/payment.

## Pinned public authority

The implementation is bound to organizer repository `jacky850/trafficflowbench-public` at commit `c88cddf533bbf0afa4ff1fc6c031d760a08e7a31` (verified 2026-09-17 UTC). It pins the public scoring spec, submission schema, merge helper, and all four task scorers by Git blob identity in `contract.py`.

That generation matters: the upstream 2026-09-11 correction removed a cross-split Task 4 weak-prior mistake. The local ODME solver therefore requires the **split-local** `task4/<panel>/<split>/synthetic_weak_prior.csv`; it never falls back to a shared corridor prior.

Published task aggregation is mirrored exactly:

`S_total = 0.35*S_state + 0.30*S_queue + 0.15*S_physics + 0.20*S_ODME`

Task 3 has no standalone submission. It is derived from Task 1 state predictions.

## What is implemented

- exact local mirrors of the public Task 1 regime score, Task 2 IoU rule, Task 3 term aggregation, Task 4 synthetic/public-train score, and total weighting;
- a Task 1 reconstruction helper that blends visible local structure with the historical profile and projects flow under a triangular fundamental-diagram envelope;
- a Task 2 queue-wave forecaster using only visible speed history, including an onset fixture where it beats origin persistence;
- a non-negative split-local prior-regularized ODME projected-gradient solver for Task 4;
- deterministic compiler/verifier for the organizer's six-column merged upload shape with duplicate-key rejection, finite/non-negative gates, queue binary enforcement, **complete-row fail closed with no permissive zero-fill mode**, a SHA-256 binding to the exact ordered `submission_key` generation, canonical SHA-256 digests of the normalized state/queue/ODME input generations, and deterministic recompilation against those trusted inputs at verify time (stricter than the organizer's zero-fill behavior);
- immutable contract/evidence receipts whose authority ceiling keeps Kaggle join, rule acceptance, competition-data acquisition, official score, rank, prize, payment, and revenue false;
- hostile tests for duplicates, missing rows, invalid queue states, receipt tampering, non-negative ODME projection, FD projection, and local-method improvement.

## Evidence ceiling

Everything in this carrier is `PUBLIC_OR_LOCAL_SYNTHETIC_ONLY`. Local diagnostic scores are not organizer scores. Hidden truth, private labels, private complete counts, queue truth, organizer boundary flows, and private evaluator configuration are not present and must not be fabricated.

When an authorized entrant later acquires the official release, the safe continuation is: verify the organizer repo/source pin; verify split-local prior identity; run the methods locally against allowed train/validation assets; compile with the exact shipped `submission_key.csv`; verify the deterministic receipt against that exact `submission_key` generation **and the retained state/queue/ODME input generations** (verified receipts require complete predictions and zero gaps); then use a separately authorized single account for any Kaggle action.

## Local proof

From repository root:

```bash
python -m revenue.trafficflowbench_2026.benchmark
python -m unittest tests.test_trafficflowbench_2026
python -O -m unittest tests.test_trafficflowbench_2026
python -m py_compile revenue/trafficflowbench_2026/*.py tests/test_trafficflowbench_2026.py
```
