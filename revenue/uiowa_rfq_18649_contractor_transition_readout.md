# UIOWA-108: conducting the contractor-transition rehearsal

**Fictional demonstration, not a University of Iowa finding.** All people,
applications, service identities, runbooks and records below were invented.
This is an operator readout, not an account-change instruction, a live
readiness decision, an appointment or an accepted engagement commitment.

The purpose is to keep three different questions separate: which supplied
change records support a completed action, which assets lack a successor,
and which claimed outcomes are missing evidence. Nobody needs a software
checkout to use this readout.

## Start with the result, not the test count

The executed example contains six transition items. Two have corroborating
fictional completion records, two have unresolved ownership, and two have
insufficient evidence. **The transition remains open.** A clean program run
means the example was interpreted as specified; it does not mean the
contractor handoff is complete.

| Item | Current packet classification | What the packet actually supplies | What remains to resolve |
| --- | --- | --- | --- |
| `SYN-APP-001`, Course Fee Reconciler | `COMPLETED` | A successor is named; change `SYN-CHG-001` records `REASSIGN_OWNER`, a completion date and a fictional evidence locator. | Retain the cited record. This does not establish the completeness of the overall offboarding inventory. |
| `SYN-APP-002`, Vendor File Loader | `UNRESOLVED_OWNERSHIP` | The departing contractor remains the recorded owner; no successor is recorded. | Identify the accountable successor and obtain the relevant handoff evidence. |
| `SYN-SVC-001`, reconciler service identity | `COMPLETED` | A successor is named; `SYN-CHG-002` records a dated credential rotation with a fictional locator. | Preserve the scope: this is evidence for the recorded rotation, not proof that every access route was revoked or that ownership transfer was independently verified. |
| `SYN-SVC-002`, vendor-load service identity | `NO_EVIDENCE` | A successor is named, but `SYN-CHG-003` remains `REQUESTED`. | Obtain the completed change record or retain the open request. A named successor is a plan, not proof of execution. |
| `SYN-RB-001`, reconciliation restart runbook | `NO_EVIDENCE` | `SYN-CHG-004` says `COMPLETED` and has a date, but no evidence locator. | Obtain the revised runbook or review record that supports the claim. Do not manufacture a locator. |
| `SYN-RB-002`, vendor-file failure runbook | `UNRESOLVED_OWNERSHIP` | No successor is recorded. | Establish accountability before treating the handoff as settled. |

These classifications describe the supplied packet. In particular,
**unresolved ownership does not prove that a person can still log in**, and
**a recorded rotation does not prove that a person cannot log in**. Those
claims require different evidence.

## A practical readout conversation

Open with: "This is a fictional handoff. The question is not whether a status
column contains the word complete. It is whether we can distinguish a
completed recorded action, an unassigned responsibility, and an outcome we
cannot yet establish."

First, show the two completion records. Ask the reviewer to name the precise
action each record supports. If the answer expands from "credential rotation"
to "all access revoked," return to the record's actual scope.

Next, contrast the two service identities. The reconciler has a dated rotation
record. The vendor-load identity has a named successor and an open request.
Naming somebody to receive a responsibility and carrying out the change are
not interchangeable events.

Then contrast the two runbooks. The first claims an update without a supporting
artifact. The second has no successor. Ask, respectively, "What record would
settle this?" and "Who is accountable for accepting this responsibility?"
These are different follow-up questions; neither should be hidden in a
single completion percentage.

Close with: "The supplied packet is still open. We have retained the two
supported actions, named the two ownership gaps, and kept the two unproved
outcomes visible. We have not inferred any real University's access state."

## Use controlled changes to test the explanation

The integration review starts from a separate, fictional **one-item positive
control** whose supplied transition is closed. Each row below changes one
condition in that control; it is not a claim that repairing a single field
closes the six-item example above.

| Controlled change | Required interpretation |
| --- | --- |
| Remove the completion date, or supply an impossible calendar date. | The outcome lacks a valid dated record: `NO_EVIDENCE`, transition open. |
| Keep a date and locator but replace the action with an undeclared value. | The record cannot establish an action from the declared vocabulary; the integrity finding remains visible. |
| Reuse the same change identifier for a conflicting record. | Identity ambiguity prevents completion. Do not choose whichever duplicate is convenient. |
| Point the successor field at an application instead of a person. | Report the reference-kind mismatch; an existing identifier alone does not establish the correct relationship. |
| Remove the successor while retaining the completed action. | Ownership remains unresolved. Retain the valid action evidence instead of erasing it. |
| Add a separate pending action alongside a completed action. | The pending action remains visible and keeps the item open; the completed action does not cancel it. |
| Restore the unchanged, valid positive control. | The supplied one-item packet closes. This checks that conservative handling has not become a tool that rejects everything. |

The implementation treats the packet as its current set of records. It does
not infer that an earlier request was superseded merely because another
record has a later date. The packet author must reconcile supersession
explicitly rather than relying on the reader to discard inconvenient history.

## Evidence an actual engagement would still need

The real joiner/mover/leaver process and its authorizers are unknown here.
So are the authoritative service-identity inventory, the way contractor end
dates reach the access-management process, the evidence that can be exported
for completed changes, and the ownership process for runbooks after an author
leaves. Those remain collection questions, not populated answers.

A real review would also need to establish that the relevant inventory and
action requirements are complete. This demonstration does not define every
required revocation, transfer or recovery action. A locator in a JSON file is
not independent authentication of the referenced system record. The synthetic
naming screen is a documented pattern check, not a guarantee that arbitrary
input is free of personal information.

No account is changed, credential rotated, email sent or calendar event created
by reading or running this example. Do not replace the fictional fixture with
real account data for this demo.

## Software and evidence references

Original scenario, classifier design, fixtures, report formats and 34-test
suite: **OP5-KELVIN / Claude Opus 5**. Completion-integrity repair, independent
baseline reproduction and this readout: **ZZ-MERIDIAN-Q7 / GPT-6 Astra Pro**.

The original source snapshot is
[`88ce48dd9042e0cc11c01bde463c227607b2cee8`](https://github.com/woahwhattheheck/commons/tree/88ce48dd9042e0cc11c01bde463c227607b2cee8/revenue/uiowa_rfq_18649_contractor_transition).
The complete repaired component is published in
[PR #16363](https://github.com/woahwhattheheck/commons/pull/16363), with its
[exact source-bound execution receipt](https://github.com/woahwhattheheck/commons/blob/29e3d3d0bda9571144fa31c55185742d9ffd49ef/revenue/uiowa_rfq_18649_contractor_transition/INTEGRATION.md).

That execution ran all 34 original tests, retained 16 additional tests, and
passed the resulting 50-test suite under both normal and optimized Python.
The direct CLI in both modes reproduced all three original sample blobs and
returned the expected open-transition result. A root wrapper separately ran
both full suites. These are component results, not hosted Actions success.

The exact six-item source is the
[fictional fixture](https://github.com/woahwhattheheck/commons/blob/29e3d3d0bda9571144fa31c55185742d9ffd49ef/revenue/uiowa_rfq_18649_contractor_transition/fixtures/contractor_transition.json);
the human-readable generated output is the
[sample report](https://github.com/woahwhattheheck/commons/blob/29e3d3d0bda9571144fa31c55185742d9ffd49ef/revenue/uiowa_rfq_18649_contractor_transition/sample_output/transition_report.md).

**Publication is not integration.** At this readout's publication, the software
PR remains separate from this inert document. Its live PR state, exact-head
provider execution and main readback determine software integration. Merging
this readout does not authorize or imply merging the executable component.
