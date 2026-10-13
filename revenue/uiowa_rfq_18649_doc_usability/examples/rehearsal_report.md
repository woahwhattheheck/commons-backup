# Documentation usability — SYNTHETIC

As of 2026-09-19. No scores or approval decisions.

- Supplied-record analysis; authenticity and export completeness are not established.
- Recorded walkthrough means the evidence type supplied, not human research executed by this tool.
- Review age is not content correctness; availability is not usability.
- No maturity score, person rating, University finding, compliance or release approval.

## Document signals

| Document | Group | Located state | Maintainer role | Review recency | Source locator |
|---|---|---|---|---|---|
| D01 | ESS | available | architect | WITHIN_WINDOW | REF-001 |
| D02 | RIS | available | UNKNOWN | REVIEW_DUE | REF-002 |
| D03 | IAM | not_located | UNKNOWN | UNKNOWN |  |
| D04 | ESS | available | service_support | UNKNOWN | REF-004 |

## Recorded task evidence

| Task | Group | Task name | Evidence type | Supplied result | As-of interpretation |
|---|---|---|---|---|---|
| T01 | ESS | Locate the upstream enrollment dependency | observed_walkthrough | completed | RECORDED_COMPLETED |
| T02 | RIS | Interpret the reporting format for run 17 | observed_walkthrough | blocked | RECORDED_BLOCKED |
| T03 | IAM | Find the contractor onboarding steps | not_observed | unknown | NOT_OBSERVED |
| T04 | RIS | Interpret the reporting format for run 17 | interview_report | completed | REPORTED_COMPLETED |
| T05 | ESS | Recover the fictional cache | observed_walkthrough | assisted | RECORDED_ASSISTED |
| T06 | ESS | Check dependency diagram readability | artifact_review | completed | ARTIFACT_REVIEW_ONLY |
| T07 | ESS | Repeat the dependency task after assessment | observed_walkthrough | completed | AFTER_AS_OF |
| T08 | IAM | Use a shared recovery note | interview_report | completed | DATE_UNKNOWN |
| T09 | IAM | Find account-retirement guidance | not_observed | unknown | NOT_OBSERVED |

## Follow-up questions

- D02 — MAINTAINER_UNRECORDED: Which role maintains this aid after a change?
- D02 — REVIEW_AGE_PROMPT: Check this aid against a current task. Age alone does not establish stale content.
- D03 — DOCUMENT_NOT_LOCATED: Locate the current task aid or record its scope; do not infer the practice is absent.
- D03 — MAINTAINER_UNRECORDED: Which role maintains this aid after a change?
- D03 — REVIEW_DATE_UNKNOWN: Find the last review or an event-triggered review record.
- D04 — REVIEW_DATE_UNKNOWN: Find the last review or an event-triggered review record.
- FORMAT-17 \[T02, T04\] — DIVERGENT_TASK_ACCOUNTS: Confirm the same bounded occurrence and explain the different accounts; do not pick a preferred narrative.
- T02 — TASK_FRICTION_RECORDED: Capture the dead end, assistance and task consequence; improve the aid and repeat this task.
- T03 \[D03\] — DOCUMENT_SUPPORT_UNRESOLVED: Reconcile task outcome with unavailable, superseded or unknown support.
- T03 — EXPECTED_SUPPORT_NOT_LINKED: Locate support for these kinds or document an effective alternative: onboarding_guide
- T04 — INTERVIEW_NEEDS_CORROBORATION: Retain the account and request a bounded walkthrough or concrete delivery example.
- T05 — TASK_FRICTION_RECORDED: Capture the dead end, assistance and task consequence; improve the aid and repeat this task.
- T06 — TASK_EXECUTION_NOT_OBSERVED: Can another practitioner complete the task using the aid?
- T07 — OBSERVATION_AFTER_AS_OF: Retain this later account separately from the as-of assessment.
- T08 \[D04\] — CROSS_GROUP_REFERENCE: Confirm the declared shared-service context; do not count this aid as independent group evidence.
- T08 — OBSERVATION_DATE_UNKNOWN: Establish when this account applies before using it as current evidence.
- T09 — DOCUMENT_LINKS_UNKNOWN: Which exact aids were used or sought for this task?
- T09 — EXPECTED_SUPPORT_UNKNOWN: Define the document types, if any, this bounded task needs.

## Preserved evidence

report.json retains every original worksheet field, extra named column, source locator,
task account and disagreement. The tables above are a view, not replacement evidence.
