# Environment consistency assessment

SYNTHETIC REHEARSAL — no University evidence or findings

Supplied-record consistency only; not live-environment verification, a maturity score, a deployment decision, or a University finding.

As of 2026-09-19; baseline: production.
Canonical-input SHA-256: `b771a8c32ec0bb5c6af306105eb7e4989571b897215e4c0e63654f371603d37f`

## Coverage (counts, not a readiness score)

{&quot;comparable&quot;:9,&quot;not_applicable&quot;:2,&quot;not_comparable&quot;:1,&quot;total_comparisons&quot;:21,&quot;unknown&quot;:9}

## Environment comparison matrix

| Check / service | Environment | Recorded value | Baseline value | Status | Evidence |
|---|---|---|---|---|---|
| ESS-database / ESS fictional service | development | 15 | 16 | UNEXPLAINED_DIFFERENCE | E-current |
| ESS-database / ESS fictional service | staging | 15 | 16 | EXPLANATION_REVIEW_DUE | E-current, E-rationale |
| ESS-database / ESS fictional service | test | 16 | 16 | ALIGNED | E-current |
| ESS-reference-gap / ESS fictional service | development | 1 | MISSING | UNKNOWN | E-current |
| ESS-reference-gap / ESS fictional service | staging | 2 | MISSING | UNKNOWN | E-current |
| ESS-reference-gap / ESS fictional service | test | 2 | MISSING | UNKNOWN | E-current |
| ESS-runtime / ESS fictional service | development | 2 | 3 | INTENTIONAL_DIFFERENCE | E-current, E-rationale |
| ESS-runtime / ESS fictional service | staging | MISSING | 3 | UNKNOWN | E-current |
| ESS-runtime / ESS fictional service | test | 3 | 3 | ALIGNED | E-current |
| IAM-reference-na / IAM fictional service | development | &quot;mock&quot; | not_applicable: Mock only used in development | NOT_COMPARABLE | E-current |
| IAM-reference-na / IAM fictional service | staging | MISSING | not_applicable: Mock only used in development | UNKNOWN | E-current |
| IAM-reference-na / IAM fictional service | test | not_applicable: Mock only used in development | not_applicable: Mock only used in development | NOT_APPLICABLE | E-current |
| IAM-runtime / IAM fictional service | development | 2 | 3 | INTENTIONAL_DIFFERENCE | E-current, E-rationale |
| IAM-runtime / IAM fictional service | staging | not_applicable: Fictional topology has no staging provisioner | 3 | NOT_APPLICABLE | E-current |
| IAM-runtime / IAM fictional service | test | 3 | 3 | UNKNOWN | E-current, E-old |
| RIS-provisioning / RIS fictional service | development | &quot;r2&quot; | &quot;r2&quot; | UNKNOWN | E-current, E-not-supplied |
| RIS-provisioning / RIS fictional service | staging | &quot;r2&quot; | &quot;r2&quot; | ALIGNED | E-current |
| RIS-provisioning / RIS fictional service | test | &quot;r2&quot; | &quot;r2&quot; | UNKNOWN | E-current, E-statement |
| RIS-queue / RIS fictional service | development | 1 | true | UNEXPLAINED_DIFFERENCE | E-current |
| RIS-queue / RIS fictional service | staging | true | true | ALIGNED | E-current |
| RIS-queue / RIS fictional service | test | unknown: Export not supplied | true | UNKNOWN | E-current |

## Follow-up worksheet

Effort ranges and impacts are input assumptions, not measured costs or established consequences.

| Check / environment | Diagnostic / question | Impact hypothesis | Proposed owner role | Hours range |
|---|---|---|---|---|
| ESS-database / development | no_current_supported_rationale — Is this difference necessary, and what evidence establishes its effect on test representativeness? | Hypothesis: this difference may limit the represented test behavior. | Service maintainer | [1, 4] |
| ESS-database / staging | rationale_review_overdue — Who will review the dated explanation and confirm or revise both expected values? | Hypothesis: this difference may limit the represented test behavior. | Service maintainer | [1, 4] |
| ESS-reference-gap / development | baseline_missing_observation — Which current artifact or clarification would resolve the diagnostic without guessing? | Hypothesis: this difference may limit the represented test behavior. | Service maintainer | [1, 4] |
| ESS-reference-gap / staging | baseline_missing_observation — Which current artifact or clarification would resolve the diagnostic without guessing? | Hypothesis: this difference may limit the represented test behavior. | Service maintainer | [1, 4] |
| ESS-reference-gap / test | baseline_missing_observation — Which current artifact or clarification would resolve the diagnostic without guessing? | Hypothesis: this difference may limit the represented test behavior. | Service maintainer | [1, 4] |
| ESS-runtime / staging | target_missing_observation — Which current artifact or clarification would resolve the diagnostic without guessing? | Hypothesis: this difference may limit the represented test behavior. | Service maintainer | [1, 4] |
| IAM-reference-na / development | baseline_not_applicable — Which alternative reference or behavior-based check makes this environment comparable? | Hypothesis: this difference may limit the represented test behavior. | Service maintainer | [1, 4] |
| IAM-reference-na / staging | target_missing_observation — Which current artifact or clarification would resolve the diagnostic without guessing? | Hypothesis: this difference may limit the represented test behavior. | Service maintainer | [1, 4] |
| IAM-runtime / test | target_stale_evidence — Which current artifact or clarification would resolve the diagnostic without guessing? | Hypothesis: this difference may limit the represented test behavior. | Service maintainer | [1, 4] |
| RIS-provisioning / development | target_missing_evidence — Which current artifact or clarification would resolve the diagnostic without guessing? | Hypothesis: this difference may limit the represented test behavior. | Service maintainer | [1, 4] |
| RIS-provisioning / test | target_statement_only — Which current artifact or clarification would resolve the diagnostic without guessing? | Hypothesis: this difference may limit the represented test behavior. | Service maintainer | [1, 4] |
| RIS-queue / development | no_current_supported_rationale — Is this difference necessary, and what evidence establishes its effect on test representativeness? | Hypothesis: this difference may limit the represented test behavior. | Service maintainer | [1, 4] |
| RIS-queue / test | target_declared_unknown — Which current artifact or clarification would resolve the diagnostic without guessing? | Hypothesis: this difference may limit the represented test behavior. | Service maintainer | [1, 4] |

## Intentional-difference record worksheet

| Check / environment | Rationale ID | Reason | Owner role | Valid from / review on | Used in decision |
|---|---|---|---|---|---|
| ESS-database / staging | R-db-expired | Fictional compatibility exercise; isolated reduced environment. | Test-environment maintainer | 2026-07-01 / 2026-09-01 | True |
| ESS-runtime / development | R-runtime | Fictional compatibility exercise; isolated reduced environment. | Test-environment maintainer | 2026-07-01 / 2026-10-01 | True |
| IAM-runtime / development | R-iam | Fictional compatibility exercise; isolated reduced environment. | Test-environment maintainer | 2026-07-01 / 2026-10-01 | True |

## Supplied evidence register

| ID | Kind | Captured | Locator (not fetched) |
|---|---|---|---|
| E-current | artifact | 2026-09-18 | synthetic/environment-export#current-table |
| E-old | artifact | 2026-08-01 | synthetic/environment-export#current-table |
| E-rationale | artifact | 2026-07-01 | synthetic/change-record#intentional-differences |
| E-statement | statement | 2026-09-18 | synthetic/environment-export#current-table |
