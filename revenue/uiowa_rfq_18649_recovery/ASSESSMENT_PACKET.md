# Deployment recovery and rollback — assessment packet

**All scenarios, organizations, roles, times, objectives, records, and outcomes below are fictional preparation material. They are not University findings.** This packet is for discussion and review of supplied records. It does not authorize a deployment, rollback, migration, restoration, access change, or other live-system action.

Work order UIOWA-063 asks for recognizing an unsuccessful release, choosing rollback or forward repair, accounting for data changes, and establishing whether recovery has actually been demonstrated. Use this packet with `example.json` and `recovery.py`; the facilitator's discussion is itself a tabletop, not an executed rehearsal. The JSON fixture represents invented records of an execution solely to exercise the software.

## 1. Reusable interview worksheet

Complete one worksheet per sampled release or rehearsal. Use organizational roles rather than employee ratings. Keep sensitive source material in the engagement's agreed location; record redacted identifiers and precise locators, not credentials or personal data, in working summaries.

### Sample identity and limits

| Field | Entry to complete |
| --- | --- |
| Group and service | ESS / RIS / IAM; service identifier: ___ |
| Sampled release and source revision | ___ |
| Change type | Configuration / application / data migration / combination: ___ |
| Environment and representativeness | ___; differences from the actual service: ___ |
| Assessment cutoff and time zone | ___ |
| Procedure version and evidence locator | ___ |
| Basis for inclusion in the sample | Normal release / urgent change / representative recovery exercise / other: ___ |
| Observed mode | Written procedure only / tabletop discussion / executed rehearsal / recorded production observation |
| Stated recovery objective and its owner | ___; agreed, proposed, or unknown: ___ |
| Known limits | Missing records, inaccessible sources, changed versions, unsampled dependencies: ___ |

### Evidence questions and recording matrix

For each row, record **documented intent**, **what was observed**, **exact source/version/locator**, **unknowns or contradictions**, and **follow-up owner role** separately. A blank observation is not evidence of failure.

| Area | Interview question | Evidence requested | Distinction to preserve |
| --- | --- | --- | --- |
| Failure recognition | What would make this release unsuccessful from a user's or service owner's perspective? Who first recognized it? | Release criteria, incident timeline, service symptoms, affected business flow and timestamp | A green process or a successful command is not the same as correct service behavior. |
| Decision trigger | What caused the team to stop normal rollout and consider recovery? | Recorded trigger, threshold or judgment, affected scope, decision timestamp | A threshold in a document is not proof that anyone acted on it. |
| Decision ownership | Which organizational role could decide and which roles needed consultation? How did the handoff occur? | Role description and actual decision record; escalation/communication receipt | An organizational decision record is assessment evidence, not a new approval mechanism in this kit. |
| Strategy comparison | Why rollback, forward repair, or neither yet? What alternatives were rejected? | Compatibility evidence, known prior version, expected consequences, rationale and uncertainty | Reversibility is a claim requiring context; previous success on another version is not enough. |
| Data changes | What data was changed? Can the old application interpret the new representation? What must be preserved? | Migration description, compatibility test results, reconciliation criteria and data-owner review | Service responsiveness alone cannot establish data correctness. |
| Execution | Was the procedure carried out, or only discussed? What actually ran and in which environment? | Completed execution record, exact version and environment, start/end times, exceptions | A tabletop is useful preparation but not an executed demonstration. |
| Verification | Which business functions and data properties were checked after recovery? Were integrations included? | Dated observations, expected versus observed results, exact evidence references | Command completion, service verification and data verification are separate milestones. |
| Recovery timing | When did the failure begin, get detected, reach a decision, start recovery, finish execution, and pass verification? | A consistent timeline with time zone and known missing endpoints | Unknown timestamps are not zero durations; contradictory timestamps cannot support a precise measurement. |
| Repeatability | When was the latest comparable exercise? What changed since then? | Latest attempt, earlier unsuccessful attempts, version/environment changes, exercise window rationale | Do not select the best historical attempt and conceal a newer failure. |
| Learning and maintenance | What was changed after the exercise, and who keeps the procedure usable? | Follow-up issue, updated procedure, repeat exercise, maintenance role | Closing a task without the relevant verification record does not establish recovery. |

### Observation record to copy for each question

```text
Sample/scenario ID:
Assessment question:
Documented intent:
Observed behavior or result:
Source ID, version, exact locator:
Source supplied? Yes / No / Partially
Observation time and environment:
Contradictory or superseding record:
What remains unknown:
Follow-up owner role:
Requested evidence or next assessment step:
Proposed effort and dependencies (not a commitment):
Reviewer interpretation and its limits:
```

## 2. Facilitator setup

Use a facilitator, a release-role participant, a service-role participant, a data/integration-role participant when relevant, and a recorder. These are proposed functions, not assigned people or invitations. Combine functions when appropriate for a small team; do not create a meeting for every role.

Present the fictional records in stages. Ask participants to identify the next question before showing the answer key. Record differing interpretations rather than forcing consensus. No participant needs access to a real environment, a credential, or production data.

Stop the exercise and retain an explicit unknown when a decision depends on compatibility, source authenticity, environment similarity, or a missing check that the supplied packet cannot establish. The useful output is a precise request for evidence, not a guessed operational decision.

## 3. Scenario A — reversible configuration change

### Briefing

A fictional ESS registration service changes a routing configuration. The application and persistent data representation are unchanged. The previous configuration is versioned and the fictional compatibility record says it remains applicable. A request-flow check begins failing after the change.

The invented objective is recovery within **20 minutes from failure onset through successful service verification**. That objective is a tabletop assumption, not a real service commitment.

### Staged records

| UTC time on September 18, 2026 | Fictional record | Evidence ID |
| --- | --- | --- |
| 10:00 | Critical registration request flow begins failing | CFG-01-RUN |
| 10:02 | Service symptom detected | CFG-01-RUN |
| 10:04 | Release lead records rollback rationale; prior configuration compatible | CFG-01-DEC |
| 10:05 | Isolated rehearsal execution starts | CFG-01-RUN |
| 10:12 | Configuration recovery execution completes | CFG-01-RUN |
| 10:15 | Critical request flow and integration response pass | CFG-01-SERVICE |

Procedure `CFG-01-PROC` is an invented version-3 record dated September 17. These identifiers resolve to the ledger in `example.json`.

### Prompts before the answer key

What establishes that the release is unsuccessful? What evidence supports reversibility? Is 10:12 the endpoint of verified recovery? What would be different if a data transformation had accompanied the configuration change? Does a current successful observation establish that the next release will recover successfully?

### Expected interpretation

The supplied metadata supports the configuration example's recorded demonstration. Detection takes 2 minutes; detection-to-decision takes 2; execution takes 7. Failure-to-command-completion is 12 minutes, but failure-to-verified-recovery is **15 minutes**. The latter meets the fictional 20-minute objective. Neither a command log nor this toy calculation independently authenticates the source records or certifies future readiness.

The expected assessor state is `evidence_supported`, with an explicit synthetic banner. A claim of only 12 minutes to verified recovery is not supported by this timeline.

### Challenge cards

**A1 — written-only substitution.** Replace the attempt's mode with `tabletop` while retaining the invented times. Expected result: `discussion_only`, no verified-recovery duration. A facilitator reading a successful script is not an execution.

**A2 — new information.** Add a later dated service check reporting failure, with its own supplied verification record. Expected result: the latest service observation is not passed; the case cannot remain affirmative by relying on the earlier success. Preserve both observations and ask whether the later failure is related to the recovered change.

**A3 — missing timestamp.** Make detection time unknown. Expected result: detection and detection-to-decision durations are unknown, not zero. The incomplete chronology prevents a complete demonstration claim, even though some other durations remain measurable.

**A4 — objective sensitivity.** Change only the fictional target to 14 minutes. The documented demonstration remains supported, while target attainment becomes `missed`. Evidence completeness and speed are different questions.

## 4. Scenario B — data migration and forward repair

### Briefing

A fictional RIS service changes stored project summaries. The previous application cannot interpret the converted summary representation. Durable project identifiers and relationships must remain intact. The service becomes unreliable after the change.

The invented release lead selects forward repair rather than assuming that restoring the old application would also restore a compatible data state. The fictional objective is 45 minutes from failure onset to both service and data verification. This is an assumption for discussion, not an operational instruction or an agreed University objective.

### Staged records

| UTC time on September 18, 2026 | Fictional record | Evidence ID |
| --- | --- | --- |
| 11:00 | Project-summary workflow fails | MIG-01-RUN |
| 11:03 | Symptom detected | MIG-01-RUN |
| 11:10 | Forward-repair rationale recorded; rollback compatibility explicitly false | MIG-01-DEC |
| 11:12 | Isolated repair rehearsal starts | MIG-01-RUN |
| 11:30 | Repair execution completes | MIG-01-RUN |
| 11:36 | Service request flow and integration response pass | MIG-01-SERVICE |
| 11:37 | Data-reconciliation record requested, but not supplied | MIG-01-DATA |

The ledger marks `MIG-01-DATA.available=false` and the data verification result `unknown`. Do not silently convert that request into a completed check.

### Prompts before the answer key

What makes application rollback an insufficiently supported choice here? What distinguishes preserving data from merely making a page load? Which evidence would establish project counts, durable IDs, relationships and aggregate totals? How should the report describe a check whose record was requested but not supplied? Can the 45-minute objective be called met?

### Expected interpretation

The observed metadata gives 3 minutes to detection, 7 from detection to decision, and 18 for execution. Failure-to-command-completion is 30 minutes. Service verification at 36 minutes alone does **not** establish verified recovery of the migration. The data result, total verified-recovery duration and objective attainment remain unknown. The expected state is `gaps_in_supplied_records`, not an assertion that the organization lacks a recovery practice.

The proposed follow-up is precise: request the dated reconciliation record covering expected and observed project counts, durable identifiers, relationships, aggregate totals, discrepancies and disposition. Also inspect whether those checks adequately cover the particular migration; the toy engine cannot decide that from a `pass` label.

### Challenge cards

**B1 — supplied follow-up.** In a copy of the fictional packet, mark `MIG-01-DATA` available and change the data result to `pass`, preserving its 11:37 timestamp. This simulates receiving the missing record, not discovering real evidence. The expected supported recovery duration becomes **37 minutes** and meets the fictional 45-minute objective.

**B2 — remove the inconvenient row.** Delete the data verification entry. Expected result: data verification stays unknown because `change_kind=data_migration` independently requires it. Removing a row cannot improve the result.

**B3 — substitute an unrelated record.** Point the migration's execution at CFG-01-RUN. Expected result: `wrong_scope_or_kind` and an unverified attempt. A successful record from another scenario does not support this one.

**B4 — conflicting observations.** Add a second data result at the same timestamp with `fail`. Expected result: conflict is explicit and the result remains unknown, not whichever value appeared last in the input.

## 5. Improvement register and proportionate next steps

These are **illustrative options**, not findings about University teams or accepted delivery commitments. Select an option only when the reviewed evidence supports its relevance. Estimate effort with the responsible organizational roles after examining their workflow.

| Observed condition in a future assessment | Proportionate option | Accountable role to discuss | Dependencies | Initial effort hypothesis | Outcome evidence |
| --- | --- | --- | --- | --- | --- |
| Procedure exists, no comparable execution record supplied | Locate an existing exercise first; if none is established, propose a bounded isolated rehearsal | Service owner and release lead | Representative environment, agreed success criteria, safe sample data | Small discovery effort; rehearsal scope estimated separately | Dated execution plus service/data checks, not meeting notes alone |
| Command completion is used as recovery completion | Add a separate verification milestone to the existing release record | Release lead | Identified critical business flows and integration checks | Small record/process adjustment, then one observed use | Distinct command and verification timestamps |
| Migration repair has service checks but missing data evidence | Define and retain migration-specific reconciliation results | Data owner and application lead | Agreed invariants, representative fixtures, interpretation of discrepancies | Medium, depending on migration complexity | Expected-versus-observed data results and disposition |
| Latest exercise is not comparable with current versions | Preserve the prior result and identify the changed assumptions before proposing a new exercise | Application lead | Version/environment difference review | Small review; further work sized from differences | Compatibility rationale or a new appropriately scoped demonstration |
| Newer failures are obscured by a successful historical example | Retain all attempts and show the latest comparable attempt with unresolved follow-ups | Release/process owner | Stable attempt IDs, consistent time zone, existing issue tracking | Small metadata/workflow change | Report shows newer failure and subsequent resolution without deleting history |

### Blank recommendation row

```text
Recommendation ID:
Supporting sample/evidence IDs and exact locators:
Observed condition (not an inference from missing material):
Practice change proposed:
Expected service consequence or reduction in friction:
Organizational owner role:
Dependencies and constraints:
Effort range and basis; unknowns:
Verification/outcome measure:
Reason to act now, defer, or request more evidence:
Review disposition and unresolved disagreement:
```

## 6. Completion checklist for the assessment deliverable

The facilitator packet is complete when both configuration and migration scenarios have been considered; procedure/discussion/execution are separately described; the record supports the chosen strategy or explains the remaining unknown; service and relevant data verification are distinguished; timing has explicit endpoints and unknowns; the latest attempt has not been hidden by older success; and proposed improvements identify roles, dependencies, effort assumptions and outcome evidence.

The engagement's reviewer decides whether the supplied evidence supports an actual finding. Do not convert the software's metadata-consistency state directly into a maturity score, compliance verdict, service approval, or individual performance rating.

Operation: `uiowa-063-quartz17-20260919`. Builder: ZZ-QUARTZ-17 / GPT-6 Astra Pro. Companion contract and commands: `README.md`.
