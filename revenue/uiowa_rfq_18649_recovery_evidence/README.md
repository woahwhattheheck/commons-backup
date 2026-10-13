# University of Iowa RFQ 18649 — UIOWA-068 recovery evidence kit

Owner: **ZZ-Semaphore / GPT-5.6 Sol**  
Status: **assessment preparation / synthetic rehearsal**

This isolated kit supports operational-resilience interviews by distinguishing four different things that are often collapsed into one statement:

1. a backup job completed;
2. data was actually restored;
3. required dependencies were recovered and verified;
4. the recovered service performed its necessary business function.

Only the complete evidence chain can produce `DEMONSTRATED` restoration in this tool.

## Files

- `assess_recovery.py` — dependency-free JSON → JSON/CSV/Markdown recovery-evidence assessor.
- `fixtures/synthetic_recovery_records.json` — fictional sign-in, research-submission, and registration records.
- `examples/recovery-evidence-matrix.csv` — generated worked matrix for interviews.
- `examples/worked-restoration-scenario.md` — scenario interpretation, evidence requests, and follow-up questions.
- `test_assess_recovery.py` — seven regression/hostile tests.

## Run

```bash
cd revenue/uiowa_rfq_18649_recovery_evidence

python assess_recovery.py fixtures/synthetic_recovery_records.json \
  --json-output /tmp/uiowa-068-report.json \
  --csv-output /tmp/uiowa-068-matrix.csv \
  --markdown-output /tmp/uiowa-068-scenario.md

python -m unittest -v test_assess_recovery.py
```

## What is assessed

For each service the input captures:

- business function;
- proposed/confirmed RPO and RTO targets;
- required service dependencies;
- successful-backup evidence;
- restoration-exercise identity;
- disruption/reference time;
- restored data point-in-time;
- technical restore completion;
- dependency verification time + evidence;
- business-function verification time + evidence.

The output separately reports:

- `backup_status`;
- `restoration_status`;
- observed RPO and target comparison;
- observed RTO and target comparison;
- dependency verification;
- business-function verification;
- explicit evidence gaps.

## Core evidence rules

### Backup completion != restoration

A record can have `backup_status=EVIDENCED` and still have `restoration_status=NOT_DEMONSTRATED`. The synthetic registration example intentionally proves that boundary.

### RPO needs an actual restored data point

Observed RPO is calculated as the elapsed time from the restored data point to the exercise disruption/reference time. A backup schedule alone does not establish the actual recovery point achieved in a restoration.

### RTO ends at usable business function

Observed RTO is measured to evidenced business-function verification. Technical restore completion without evidence that the service's necessary workflow works leaves RTO `UNKNOWN`.

### Dependencies are part of recovery

A dependent service cannot become `DEMONSTRATED` merely because its own process started. Required dependency verification must be present and must not occur after the business-function verification it supposedly enabled.

### Missing evidence stays missing

The assessor uses `UNKNOWN`, `PARTIAL`, or `NOT_DEMONSTRATED` to communicate what the supplied evidence can establish. It does not transform absent evidence into a claim that a backup, dependency, or recovery process failed.

## Synthetic acceptance result

The authored fixture produces three deliberately different outcomes:

- **Synthetic research submission:** `DEMONSTRATED`; RPO 30 min <= fictional target 60; RTO 100 min <= fictional target 120; dependency and business verification evidenced.
- **Synthetic sign-in:** `PARTIAL`; RPO observed, but business verification is missing so RTO remains unknown.
- **Synthetic registration:** backup evidenced but restoration `NOT_DEMONSTRATED`; there is no exercise evidence, so RPO/RTO remain unknown.

Local authored-byte regression result: **7/7 tests pass**.

## Authority boundary

The fixture is wholly fictional. Target objectives in the fixture are scenario assumptions, not University commitments or measured performance.

The tool is offline. It does not:

- connect to a backup platform;
- read or restore real University data;
- use recovery credentials or encryption keys;
- alter retention or backup policy;
- initiate a recovery exercise;
- schedule an exercise;
- establish compliance, maturity, or procurement suitability.

Actual engagement findings require authorized University evidence and context.
