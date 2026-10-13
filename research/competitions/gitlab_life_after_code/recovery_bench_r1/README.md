# GitLab Life After Code — Recovery Benchmark R1

Offline, dependency-free benchmark for evaluating a post-code lifecycle recovery agent. This packet does **not** create a GitLab project, invoke GitLab Duo, perform account actions, or submit to a competition.

## Benchmark contract

Six deterministic lifecycle cases are included:

- clean pass
- recoverable test failure
- fail-closed security failure
- recoverable deploy failure
- reused-evidence rejection
- approved package retry

The scorer requires exact case coverage, exact promote/block decisions, the expected recovery stage, unique HTTPS evidence references per case, and fail-closed handling for security/evidence hazards. It reports task success, recovery success, unsafe promotions, wall time, and stage count.

## Run

```bash
python recovery_bench.py cases.jsonl candidate.jsonl --baseline baseline.jsonl
python test_recovery_bench.py
```

## Validation receipt

The source-complete packet was reported with focused validation **7/7 PASS**.

Synthetic scorer smoke:

- recovery candidate: **6/6 correct**
- recovery success: **3/3**
- unsafe promotions: **0**
- direct fail-on-error baseline: **3/6 correct**
- baseline recovery success: **0/3**
- candidate minus baseline task-success rate: **+0.50**
- candidate minus baseline median wall time: **+275 ms**
- candidate minus baseline p95 wall time: **+480 ms**
- candidate minus baseline median stages: **+2.5**

These numbers validate the synthetic scorer and recovery-policy shape only. They are **not** GitLab Duo, production, or competition performance.

## Files

- `recovery_bench.py` — scorer and candidate/baseline comparison
- `cases.jsonl` — six deterministic lifecycle cases
- `candidate.jsonl` — recovery-capable synthetic predictions
- `baseline.jsonl` — direct fail-on-error synthetic baseline
- `test_recovery_bench.py` — focused scorer regressions

## Evidence boundary

The benchmark is intentionally offline and synthetic. It does not contain competition data, credentials, account state, or internal swarm orchestration details.
