# Proposed UAT, cutover and recovery plan

Status: **PROPOSED_NOT_ACCEPTED**. This is an editable plan for a qualified
implementation team. No test below represents a live SMART observation, accepted
bid, scheduled appointment, or authorization to deploy.

## Acceptance evidence to collect

Every test record should identify the requirement, source/configuration revision,
environment, synthetic or approved test data, expected result, actual result,
operator, unresolved discrepancy and reviewer. Preserve raw result files alongside
the readable report. A report's digest binds content; it does not authenticate
the person who approved it.

| Area | Required test evidence for the proposed implementation | Current lab boundary |
| --- | --- | --- |
| Contract and mapping | Approved endpoint/schema examples; required, empty and malformed fields; error and pagination behavior | No SMART endpoint catalog recovered; outer lab scenarios are proposed contracts |
| Ordinary operation | Expected and observed business identity, amount and outcome agree | Existing read-only synthetic reconciliation can be exercised |
| Duplicate delivery | Same operation adds no duplicate effect; a changed payload under the same key stays visible | Deterministic outer acceptance scenario; production key/store behavior unproven |
| Before-dispatch retry | Bounded logical retry sequence and explicit exhausted-budget outcome | Offline schedule observation only; no network timings or service SLA |
| Uncertain commit | Lost acknowledgement does not trigger blind resend; matching status evidence resolves or retains the hold | Injected observations; no real status-query capability established |
| Financial discrepancy | Each signed discrepancy retains its operation identity even when totals cancel | Synthetic integer-unit comparison; actual currencies, precision and ledger rules unconfirmed |
| Access and audit | Approved role/scope matrix, denied access without protected effect, retained redacted audit trail | Existing unauthorized synthetic cases; no real identity-provider or security assessment |
| Concurrency | Competing requests, locks/versions, ordering and replay behavior under the agreed data model | Single-process deterministic lab is not a concurrency proof |
| Failure and restart | Actual journal/service/database crash boundaries, backup recovery and resumed processing | Transcript reconstruction is not proof of production durability |
| AWS/pipelines | Approved extraction, checkpointing, monitoring, backup/restore, error and cost behavior | No AWS deployment or provider execution |
| Documents | Supported metadata, indexing, routing, permission and retention behavior | Document integration remains outside the implemented lab |
| Performance and coverage | Agreed load model and measured latency/throughput; measured code coverage | Case counts alone satisfy neither performance nor coverage targets |
| Operations and handover | Demonstrated runbook use, editable documentation, walkthroughs, ownership and support handoff | Internal guide only; no client attendance or acceptance recorded |

## Release prerequisites

Before any production cutover, the implementation team would need the current
solicitation package, an accepted scope, a qualified contracting party, approved
interfaces and data handling, controlled access to a representative environment,
measured UAT results, and explicit client release authority. Current missing items
are tracked in [SUBMISSION_READINESS.md](SUBMISSION_READINESS.md).

Assign named owners for the change, business validation, data/platform operations,
security, communications, rollback and post-release support. These roles are
currently unassigned. The authority to review a local result does not imply
authority to change SMART, send a customer notice or initiate a financial action.

## Cutover rehearsal

1. Freeze the reviewed source/configuration and record the approved release scope.
   Confirm that backups are usable through an actual restore exercise; a backup
   filename alone is not a recovery result.
2. Capture baseline control totals, unresolved work and current interface state
   using client-approved data handling. Define where in-flight operations will be
   observed and how their uncertainty is retained.
3. Rehearse deployment and a bounded canary in the agreed non-production
   environment. Check contract compatibility, permissions, observability and the
   disposition of each uncertain request before increasing scope.
4. Compare operation-level results and control totals. Investigate missing,
   duplicate or inconsistent effects individually; do not mask opposing variances
   by netting them to zero.
5. Demonstrate stopping new dispatch, preserving the journal, restoring approved
   configuration and reconciling in-flight work. Record elapsed recovery and all
   unresolved transactions for the actual environment.
6. Obtain the designated client's explicit go/no-go decision. Keep the decision,
   supporting evidence and any accepted exceptions with the release record.

These steps are a plan only. No step has been performed on Wayne RESA systems by
this lab, and no real cutover window is scheduled.

## Rollback and post-release decisions

Rollback should stop further unverified effects and recover an approved operating
state. It must not pretend a committed financial operation never happened. Whether
a reversal or compensating operation is allowed is a client business-rule decision,
with its own authorization and audit record. Preserve uncertain operations across
rollback and resolve them through the agreed status/reconciliation process.

Proposed pause triggers include an unexplained financial discrepancy, duplicate
business effects, unauthorized access, lost journal history, or inability to
classify an in-flight operation safely. Exact thresholds and operational owners
must be agreed for the real service; illustrative values are not a contractual SLA.

The RFP's documentation, coverage and handover obligations remain requirements to
demonstrate. The source crosswalk records the stated walkthrough, handover and
warranty terms; this lab does not mark them delivered or substitute synthetic
tests for client acceptance.
