# Executed synthetic operator walkthrough

Python 3.12.14 executed the rehearsal normally and under `-O`; both produced the same receipt and **57 byte-identical files (273,602 bytes)**. These are local synthetic results, not hosted provider execution or SMART observations. The execution receipt separately binds the tested source and logs.

[WORKED_REHEARSAL_BUNDLE.json](WORKED_REHEARSAL_BUNDLE.json) contains every actual UTF-8 artifact with relative path, byte count, SHA-256 and exact contents, including all 150 original expanded records. It is an evidence bundle, not the runtime. Regenerate the files with the command in [README.md](README.md); the readable case names below identify the corresponding directories inside the bundle and generated output.

## Synthetic Wayne SMART operator rehearsal

LOCAL_SYNTHETIC_EXPECTATIONS_MATCHED

Rehearsal receipt: `86b39d10ced857272ff6de7d9a25f65b646066b9455efbb3cfc936ab5be74a38`

The unchanged original 150-state baseline and 18 new proposed scenarios were checked separately.
This is synthetic local execution, not buyer acceptance or measured code coverage.

| Scenario | Expected outcomes matched | Current states | Attempts | Accepted commit observations | Variance sum | Nonzero variance operations | Review disposition |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| `ordinary-confirmed` | Yes | COMMITTED | 1 | 1 | 0 | 0 | SIMULATION_RECONCILED |
| `before-dispatch-retry` | Yes | COMMITTED | 3 | 1 | 0 | 0 | SIMULATION_RECONCILED |
| `retry-budget-exhausted` | Yes | HOLD_RETRY_EXHAUSTED | 3 | 0 | 0 | 0 | HOLD_REVIEW_REQUIRED |
| `capped-logical-backoff` | Yes | COMMITTED | 4 | 1 | 0 | 0 | SIMULATION_RECONCILED |
| `duplicate-alias-and-observation` | Yes | COMMITTED | 1 | 1 | 0 | 0 | SIMULATION_RECONCILED |
| `lost-acknowledgement-no-resend` | Yes | HOLD_UNKNOWN_COMMIT | 1 | 0 | 0 | 0 | HOLD_REVIEW_REQUIRED |
| `lost-acknowledgement-resolved` | Yes | COMMITTED | 1 | 1 | 0 | 0 | HOLD_REVIEW_REQUIRED |
| `explicit-not-committed-review` | Yes | HOLD_NOT_COMMITTED_REVIEW | 1 | 0 | 0 | 0 | HOLD_REVIEW_REQUIRED |
| `same-key-changed-payload` | Yes | READY | 0 | 0 | 0 | 0 | HOLD_REVIEW_REQUIRED |
| `wrong-payload-digest` | Yes | No operation accepted | 0 | 0 | 0 | 0 | HOLD_REVIEW_REQUIRED |
| `competing-key-same-mutation` | Yes | READY | 0 | 0 | 0 | 0 | HOLD_REVIEW_REQUIRED |
| `wrong-commit-observation` | Yes | IN_FLIGHT | 1 | 0 | 0 | 0 | HOLD_REVIEW_REQUIRED |
| `conflicting-evidence-id` | Yes | COMMITTED | 1 | 1 | 0 | 0 | HOLD_REVIEW_REQUIRED |
| `opposing-cent-variances` | Yes | HOLD_LEDGER_VARIANCE, HOLD_LEDGER_VARIANCE | 2 | 0 | 0 | 2 | HOLD_REVIEW_REQUIRED |
| `baseline-unknown-never-upgraded` | Yes | HOLD_BASELINE_STATUS | 0 | 0 | 0 | 0 | HOLD_REVIEW_REQUIRED |
| `baseline-unauthorized-never-upgraded` | Yes | HOLD_BASELINE_STATUS | 0 | 0 | 0 | 0 | HOLD_REVIEW_REQUIRED |
| `stale-attempt-outcome` | Yes | COMMITTED | 2 | 1 | 0 | 0 | HOLD_REVIEW_REQUIRED |
| `explicit-unknown-observation` | Yes | HOLD_UNKNOWN_COMMIT | 1 | 0 | 0 | 0 | HOLD_REVIEW_REQUIRED |

Matching an expected HOLD is a successful synthetic contract check; it is not permission to dispatch.
A resolved COMMITTED operation retains historical HOLD event IDs and the review disposition until a human evaluates the history. The lab never erases that history.
The opposing-cent case records +1 and −1 cent individually: zero net variance still leaves two held operations.

## Original baseline result

```json
{
  "authoritative_writes": 0,
  "duplicate_mutation_effects": 0,
  "ledger_variance_cents": 0,
  "records": 150,
  "replay": {
    "events_added": 0,
    "holds_added": 0,
    "idempotent": 150,
    "protected_reads_added": 0,
    "staged_effects_added": 0,
    "state_unchanged": true
  },
  "statuses": {
    "DUPLICATE_NOOP": 10,
    "HOLD_UNAUTHORIZED": 10,
    "HOLD_UNKNOWN_COMMIT": 10,
    "RECONCILED": 120
  },
  "task_id": "wayne-smart-api-01",
  "unauthorized_reads": 0,
  "unknown_commits_held": 10
}
```

All 150 expanded baseline records are retained in baseline_records.json with their original truth labels. Every case directory retains transcript.json, report.json and report.md.
