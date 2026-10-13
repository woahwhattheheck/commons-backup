# UIOWA-068 — worked synthetic restoration scenario

Assessment: `UIOWA-068-SYNTHETIC-RESTORE-01`  
Status: **fictional rehearsal / not a University finding**

## Scenario

Three fictional services are represented so the interview instrument exercises different evidence states rather than pretending every successful backup is a demonstrated recovery.

| Service | Business function | Target RPO | Target RTO | Dependencies |
|---|---|---:|---:|---|
| Synthetic sign-in | Authenticate users to in-scope services | 15 min | 60 min | none |
| Synthetic research submission | Submit and route a research administration packet | 60 min | 120 min | Synthetic sign-in |
| Synthetic registration | Register a student for an eligible course | 30 min | 90 min | Synthetic sign-in |

The RPO/RTO targets above are **scenario assumptions only**. They are not University objectives.

## Generated assessment

| Service | Backup | Restoration | RPO | RTO | Dependencies | Business verification |
|---|---|---|---|---|---|---|
| Synthetic sign-in | EVIDENCED | PARTIAL | MEETS_TARGET | UNKNOWN | NOT_APPLICABLE | NOT_EVIDENCED |
| Synthetic research submission | EVIDENCED | DEMONSTRATED | MEETS_TARGET | MEETS_TARGET | EVIDENCED | EVIDENCED |
| Synthetic registration | EVIDENCED | NOT_DEMONSTRATED | UNKNOWN | UNKNOWN | UNKNOWN | NOT_EVIDENCED |

### Synthetic sign-in

The fixture contains a successful backup and an exercise record with a 10-minute observed data-recovery point. Restore completion is recorded, but no evidence proves that the sign-in business function actually worked after restoration.

**Interpretation:** restoration remains `PARTIAL`; RPO can be calculated from the supplied timestamps, but RTO remains `UNKNOWN` because business recovery was not evidenced.

**Interview follow-up:** What transaction or user journey must succeed before sign-in recovery is declared complete, and where is that verification retained?

### Synthetic research submission

The exercise begins at 01:00 UTC, restores a data point from 00:30 UTC, completes technical restoration at 02:20 UTC, verifies the sign-in dependency at 02:00 UTC, and verifies the research-submission business function at 02:40 UTC.

Observed synthetic RPO: **30 minutes** against a 60-minute scenario target.  
Observed synthetic RTO: **100 minutes** against a 120-minute scenario target.

**Interpretation:** the supplied synthetic record supports `DEMONSTRATED` restoration because the evidence chain includes the recovery reference time, restored-data point, technical restore completion, dependency verification, and business-function verification.

**Interview follow-up:** Does the real exercise test the full submission path, including downstream routing/notifications, or only application startup and authentication?

### Synthetic registration

The fixture contains evidence of a successful backup but no restoration exercise record.

**Interpretation:** restoration is `NOT_DEMONSTRATED`; RPO and RTO remain `UNKNOWN`. A successful backup job is evidence that backup activity occurred, not proof that data can be restored into a service that performs its necessary business function.

**Interview follow-up:** What was the latest full or representative restoration exercise, what dependencies had to be recovered, and what business transaction established success?

## Evidence request matrix

For each in-scope service, request enough evidence to answer these separately:

1. **Recovery objective:** documented RPO/RTO target, owner, scope, and any peak-period variation.
2. **Backup coverage:** source/data components covered, frequency, retention, evidence of successful jobs, and known exclusions.
3. **Restore mechanics:** restoration runbook/process, required credentials/keys, infrastructure or vendor dependencies, and prerequisite order.
4. **Exercise evidence:** dated exercise or actual recovery record; source data point restored; start, restore-complete, and business-verification times.
5. **Dependency recovery:** evidence that services required by the restored application were usable before the application was declared recovered.
6. **Business-function verification:** specific transaction, workflow, or other outcome proving the recovered service was usable for its intended purpose.
7. **Learning/follow-through:** gaps found during the exercise, owner, follow-up action, and evidence the action was tested or closed.

## Assessment rules embodied by the tool

- A backup completion event cannot by itself produce `DEMONSTRATED` restoration.
- Missing exercise or verification evidence remains `UNKNOWN` / `PARTIAL`; it is not rewritten as a failed control.
- RPO is calculated only when the disruption/reference time and restored-data point are known.
- RTO is calculated only to evidenced business-function verification, not merely process startup or storage restoration.
- Required dependencies must have dated verification evidence before a dependent service can be marked demonstrated.
- Impossible chronology is rejected.
- The tool performs no live backup, restoration, credential, or provider action.

## Reproduction

```bash
python assess_recovery.py fixtures/synthetic_recovery_records.json \
  --json-output /tmp/uiowa-068-report.json \
  --csv-output /tmp/uiowa-068-matrix.csv \
  --markdown-output /tmp/uiowa-068-scenario.md

python -m unittest -v test_assess_recovery.py
```

Expected regression result on the authored fixture: **7/7 tests pass**.
