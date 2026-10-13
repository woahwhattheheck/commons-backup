# Test-data readiness evidence

Supplied metadata only. Synthetic examples are fictional. Evidence references are not independently verified. No institutional finding, compliance verdict or release authorization.

Context: synthetic-demo; cutoff: 2026-09-19T12:00:00+00:00
Canonical catalog SHA-256: `444b94ed1cfd37afe514703046ffb902a95a647122a734ac6ca5eed7755e755b`

Counts are coverage descriptors, not a maturity or release-readiness score.

| Contract | Group | Boundary case | Declared | Supported | Recorded failure | Unknown |
|---|---|---|---|---|---|---|
| SYN-award | RIS | duplicate-award | SYN-RIS-01 |  |  | SYN-RIS-01 |
| SYN-award | RIS | renewal-boundary | SYN-RIS-01 |  |  | SYN-RIS-01 |
| SYN-enrollment | ESS | duplicate-enrollment | SYN-ESS-01 | SYN-ESS-01 |  |  |
| SYN-enrollment | ESS | late-withdrawal | SYN-ESS-01 | SYN-ESS-01 |  |  |
| SYN-enrollment | ESS | unicode-student-key |  |  |  |  |
| SYN-identity | IAM | contractor-expiry | SYN-IAM-01 |  | SYN-IAM-01 |  |
| SYN-identity | IAM | repeated-deprovision | SYN-IAM-01 |  |  | SYN-IAM-01 |
| SYN-identity | IAM | role-change | SYN-IAM-01, SYN-IAM-LEGACY | SYN-IAM-01 |  | SYN-IAM-LEGACY |

## Limitations and maintenance actions

| Fixture / case | Code / evidence state | Testing consequence | Next action | Owner | Estimated hours | Evidence refs |
|---|---|---|---|---|---|---|
| SYN-IAM-01 / contractor-expiry | CASE_FAILURE_RECORDED / RECORDED | Latest supplied case run failed; this does not identify a production defect. | Investigate the failed case and capture the resolution and rerun. | Fictional identity test-data steward | 1.5 | SYNTHETIC-RECEIPT |
| SYN-IAM-01 / repeated-deprovision | CASE_EVIDENCE_LIMITED / UNKNOWN | Declared case lacks usable, current, post-refresh run evidence. | Capture a version-aligned run after the demonstrated refresh and before the cutoff. | Fictional identity test-data steward | 1.5 |  |
| SYN-IAM-LEGACY | OWNER_UNKNOWN / UNKNOWN | Maintenance planning lacks owner. | Assign an accountable team role for refresh and cleanup. | UNKNOWN | UNKNOWN |  |
| SYN-IAM-LEGACY | EFFORT_UNKNOWN / UNKNOWN | Maintenance planning lacks maintenance_hours. | Estimate refresh, review and cleanup effort before prioritizing. | UNKNOWN | UNKNOWN |  |
| SYN-IAM-LEGACY | RECIPE_UNKNOWN / UNKNOWN | Maintenance planning lacks recipe_ref. | Capture a repeatable fixture-generation and refresh recipe. | UNKNOWN | UNKNOWN |  |
| SYN-IAM-LEGACY | VERSION_ALIGNMENT / CONTRADICTED | Fixture metadata does not match the declared current interface. | Version the fixture and reconcile its interface contract before relying on its runs. | UNKNOWN | UNKNOWN |  |
| SYN-IAM-LEGACY | REFRESH_NOT_DEMONSTRATED / RECORDED | A current repeatable refresh has not been demonstrated by the supplied latest record. | Capture a successful, version-aligned refresh receipt; a recipe alone is not a rehearsal. | UNKNOWN | UNKNOWN | SYNTHETIC-RECEIPT |
| SYN-IAM-LEGACY / role-change | CASE_EVIDENCE_LIMITED / UNKNOWN | Declared case lacks usable, current, post-refresh run evidence. | Capture a version-aligned run after the demonstrated refresh and before the cutoff. | UNKNOWN | UNKNOWN | SYNTHETIC-RECEIPT |
| SYN-RIS-01 | REFRESH_OVERDUE / RECORDED | The latest refresh is older than the supplied refresh interval. | Refresh and rerun affected cases, or record a revised service-specific interval. | Fictional research-systems fixture maintainer | 4 | SYNTHETIC-RECEIPT |
| SYN-RIS-01 | CLEANUP_NOT_DEMONSTRATED / UNKNOWN | The supplied cleanup due time has passed without a successful cleanup receipt. | Demonstrate cleanup or document the retention/review decision and next due time. | Fictional research-systems fixture maintainer | 4 |  |
| SYN-RIS-01 / duplicate-award | CASE_EVIDENCE_LIMITED / UNKNOWN | Declared case lacks usable, current, post-refresh run evidence. | Capture a version-aligned run after the demonstrated refresh and before the cutoff. | Fictional research-systems fixture maintainer | 4 |  |
| SYN-RIS-01 / renewal-boundary | CASE_EVIDENCE_LIMITED / UNKNOWN | Declared case lacks usable, current, post-refresh run evidence. | Capture a version-aligned run after the demonstrated refresh and before the cutoff. | Fictional research-systems fixture maintainer | 4 | SYNTHETIC-RECEIPT |

A missing specification is a sampling/design gap, not proof the behavior is untested everywhere.
Failures on one fixture remain visible even when another fixture supplies passing evidence.
