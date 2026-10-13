# Interview session INT-2026-03-11-ESS — imported evidence records

**FICTION. An invented interview session written for this adapter. No interview has been conducted, requested, or scheduled, and no real person is represented. Participants are ROLES, never named individuals.**

3 participants, 4 questions, 11 records.

| Status | Count | May support a finding |
|---|---|---|
| `CORROBORATED` | 3 | yes |
| `DISPUTED` | 4 | **no** |
| `ILLUSTRATED` | 1 | **no** |
| `STATED` | 3 | **no** |

A participant's statement is testimony. Only a statement backed by a record the practice itself produced is marked as able to support a finding, and a contradicted statement is not promoted even when one side carries an artifact.

**Interpretation limit.** CORROBORATED means a declared document or system-export reference resolves in the supplied register. The adapter does not open it, authenticate it, or establish that its content supports the statement. `supports_finding` is eligibility for assessor review, not a verified finding.

## Q1 — How does a standard change get approved and released?

*Assessment area: deployment*

### EV-INT-2026-03-11-ESS-N1 · ESS release engineer · `DISPUTED`

> Standard changes take two approvals before release.

**Example given.** CR-411 last month went through both the peer approval and the change-manager approval.

**Basis.** contradicted by N2; this side carries artifact SRC-ESS-REL-LOG. Adjudicate against that artifact — the adapter does not decide

**Artifact.** `SRC-ESS-REL-LOG` → `fictional-repo/ess/release/log-2026-q1.csv`

**Contradicted by.** `N2` — both notes retained; not adjudicated here.

### EV-INT-2026-03-11-ESS-N10 · Change manager (shared services) · `CORROBORATED`

> The written change procedure requires two approvals.

**Example given.** Section 4 of the procedure states it.

**Basis.** statement plus artifact SRC-ESS-CHG-PROC resolving to fictional-repo/ess/policy/change-management.md#approvals

**Artifact.** `SRC-ESS-CHG-PROC` → `fictional-repo/ess/policy/change-management.md#approvals`

### EV-INT-2026-03-11-ESS-N2 · Change manager (shared services) · `DISPUTED`

> In practice most standard changes carry one approval; the second is only for high-risk ones.

**Example given.** The March batch of routine schema changes each had a single approval entry.

**Basis.** contradicted by N1; no artifact on this side. Both notes are retained and neither is promoted

**Contradicted by.** `N1` — both notes retained; not adjudicated here.

**Follow-up.** Ask for the standing exception, if one is written down.

## Q2 — What automated testing runs before a release?

*Assessment area: software*

### EV-INT-2026-03-11-ESS-N3 · ESS QA analyst · `CORROBORATED`

> A nightly suite runs against the integration environment.

**Example given.** The 2026-03-28 run is the most recent one we looked at together.

**Basis.** statement plus artifact SRC-ESS-TEST-RUN resolving to fictional-repo/ess/quality/runs-2026-03.json

**Artifact.** `SRC-ESS-TEST-RUN` → `fictional-repo/ess/quality/runs-2026-03.json`

### EV-INT-2026-03-11-ESS-N4 · ESS release engineer · `STATED`

> We also run contract tests against the student-record interface.

**Basis.** testimony only; no artifact and no specific example supplied

**Follow-up.** Ask where contract-test results are retained.

### EV-INT-2026-03-11-ESS-N5 · ESS QA analyst · `STATED`

> Coverage is good across the enrollment module.

**Example given.** We generally keep it high.

**Basis.** testimony only; no artifact and no specific example supplied

**Follow-up.** Ask for a coverage report from after the March migration.

## Q3 — How is access to the release pipeline reviewed?

*Assessment area: security*

### EV-INT-2026-03-11-ESS-N11 · ESS QA analyst · `ILLUSTRATED`

> Access changes for the release group go through a ticket.

**Example given.** The ticket for removing a leaver in February was REQ-7781.

**Basis.** statement plus a specific example, still the participant's own account; no artifact supplied

**Follow-up.** Ask for the ticket export covering the last two quarters.

### EV-INT-2026-03-11-ESS-N6 · Change manager (shared services) · `CORROBORATED`

> Pipeline access is reviewed with the wider access review each quarter.

**Example given.** The Q4 2025 review covered the release group.

**Basis.** statement plus artifact SRC-IAM-REVIEW-Q4 resolving to fictional-repo/iam/reviews/2025-q4.pdf

**Artifact.** `SRC-IAM-REVIEW-Q4` → `fictional-repo/iam/reviews/2025-q4.pdf`

**Follow-up.** Ask whether a Q1 2026 review has been completed.

### EV-INT-2026-03-11-ESS-N7 · ESS release engineer · `STATED`

> Only the release group can deploy to production.

**Basis.** testimony only; no artifact and no specific example supplied

**Follow-up.** Ask for the group membership export.

## Q4 — Are any AI-assisted tools used in this work?

*Assessment area: ai_readiness*

### EV-INT-2026-03-11-ESS-N8 · ESS QA analyst · `DISPUTED`

> No AI tools are used in QA work.

**Basis.** contradicted by N9; no artifact on this side. Both notes are retained and neither is promoted

**Contradicted by.** `N9` — both notes retained; not adjudicated here.

**Follow-up.** Ask whether individually adopted assistants are included in that answer.

### EV-INT-2026-03-11-ESS-N9 · ESS release engineer · `DISPUTED`

> An AI coding assistant is in daily use on the engineering side.

**Example given.** It is used for first-draft unit tests.

**Basis.** contradicted by N8; no artifact on this side. Both notes are retained and neither is promoted

**Contradicted by.** `N8` — both notes retained; not adjudicated here.

**Follow-up.** Ask how it was obtained and whether a licence record exists.

## Coverage

| Question | Area | Answered by | Not covered by |
|---|---|---|---|
| Q1 | deployment | P1, P3 | P2 |
| Q2 | software | P1, P2 | P3 |
| Q3 | security | P1, P2, P3 | — |
| Q4 | ai_readiness | P1, P2 | P3 |

A question a participant did not answer is recorded as not covered. That is absence of evidence about the practice, not evidence of a gap in it.

## Diagnostics

| Severity | Code | Note | Field | Message |
|---|---|---|---|---|
| INFO | `DISAGREEMENT_MADE_MUTUAL` | `N1` | `disagrees_with` | N2 contradicts this note; marking both DISPUTED so the unaware side does not export as settled |
| INFO | `DISAGREEMENT_MADE_MUTUAL` | `N8` | `disagrees_with` | N9 contradicts this note; marking both DISPUTED so the unaware side does not export as settled |
| WARNING | `VAGUE_EXAMPLE` | `N5` | `concrete_example` | the example describes a habit rather than an instance, so it does not raise the note above STATED |
| INFO | `NOT_COVERED` | `Q1` | `P2` | ESS QA analyst did not answer this question; recorded as not covered, which is not a finding about the practice |
| INFO | `NOT_COVERED` | `Q2` | `P3` | Change manager (shared services) did not answer this question; recorded as not covered, which is not a finding about the practice |
| INFO | `NOT_COVERED` | `Q4` | `P3` | Change manager (shared services) did not answer this question; recorded as not covered, which is not a finding about the practice |
