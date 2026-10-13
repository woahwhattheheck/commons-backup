# Review sampling worksheet and behavior-anchored rubric

**UIOWA-044 / proposed assessment method / synthetic worked examples.**

This instrument evaluates the practice using process records and review metadata. It does not review application code line by line and does not infer code quality from clicks, comment counts or elapsed time. Use the same outcomes for manual, paired and asynchronous workflows; an automated export is not intrinsically better evidence than a well-bounded manual record.

## 1. Establish the sampling frame before looking at favorable cases

| Field | Fill in for the actual assessment |
|---|---|
| Group / service / relevant assessment area | [Unfilled; do not infer the University inventory from this kit.] |
| Source owner and evidence location | [Owner role, system/document and exact version or export identifier.] |
| Observation window / time convention | [Start, end, timezone, calendar or working-time interpretation.] |
| Population definition | [Which delivered and still-open changes count? Include excluded channels explicitly.] |
| Selection method | [Bounded census, randomly drawn records, stratified sample or purposive cases; state limitations.] |
| Strata / dependencies | [Routine, emergency, configuration, shared service; identify correlated changes.] |
| Planned / obtained / excluded counts | [Counts and reasons; absence from the export is not automatically absence from the population.] |
| Source completeness and capture time | [Pagination/end marker, manual reconciliation or authoritative report definition; unresolved coverage gaps.] |
| Local review expectation | [What review is proportionate for this change class? Include synchronous/paired practices.] |
| Team context | [Service criticality, change size, availability, dependencies, tenure mix and shared-team constraints.] |
| Interview / artifact linkage | [Evidence IDs, precise locators, note author and observation date.] |

Choose examples that reveal different operating conditions, not only successes or failures. A small purposive sample can explain mechanisms but cannot estimate organizational prevalence. Shared reviewers, releases and inherited services are dependent observations; do not triple-count one shared practice because three group labels use it.

## 2. Per-change evidence worksheet

| Review question | Record and locator | Interpretation / alternative explanation | Remaining question |
|---|---|---|---|
| What was requested, and which revision was reviewed? | [Change ID, head, request and review times.] | [Final head, earlier head, undated or unknown.] | [What changed after the reviewed head?] |
| What context did the reviewer have? | [Requirement, service context, risk, test summary, paired-session note.] | [Context linked / context asserted / unknown.] | [What could another reviewer reconstruct?] |
| What does the feedback actually discuss? | [Source-linked question, change request, tradeoff, test evidence.] | [Approval only is not evidence of no work; substantive-looking text still needs inspection.] | [Did the discussion influence the decision or clarify intent?] |
| How were comments handled? | [Dated resolution, explained deferral, disagreement or reopened point.] | [At delivery cutoff versus after delivery; keep unresolved disagreement.] | [Who accepted a deferral and where is the rationale?] |
| Where did elapsed time arise? | [Initial request, actual feedback event, known constraints.] | [Calendar/working time; missing initial request; open/right-censored work.] | [Was the delay capacity, dependency, request quality or a re-request artifact?] |
| Was this an emergency exception? | [Rationale, expected follow-through, due date and later review evidence.] | [Exception handled / completion unverified / unknown export window.] | [Did follow-through close every relevant point, not just the newest thread?] |

The executable contract maps consciously deferred work into a resolved disposition only when a dated source explains that disposition. The worksheet retains the defer/accept/reject rationale. A simple “resolved” flag is insufficient. Code changes are not required for a defensible response to every comment.

## 3. Behavior anchors — a profile, not a score

Apply these anchors independently to each dimension. `Unknown` is an evidence state, not a low maturity rating. The other columns are descriptive anchors rather than a numeric ordinal scale; do not average them or map them automatically into the separate engagement maturity framework.

| Dimension | Unknown / not assessable | Stated expectation only | Observed practice in a bounded sample | Evidence of maintained practice |
|---|---|---|---|---|
| Coverage and revision fit | Export population or review timing cannot be established. | A team describes when review should occur. | Change classes and revision identities can be traced to proportionate review evidence, including documented exceptions. | Repeated windows retain coverage evidence and reveal how intervening edits or exceptions are reconciled. |
| Reviewer context | Metadata does not show available context. | Guidance asks authors to provide context. | Sample reviews link service/requirement/test context sufficient to explain the decision. | The team checks context usefulness and updates the preparation template or knowledge handoff when gaps recur. |
| Feedback and disposition | Approvals, missing discussion or uncertain chronology cannot establish the handling of substantive points. | Procedure describes responding to comments. | Questions/tradeoffs and dated accept/change/defer decisions are source-linked; disagreement remains visible. | Recurring unresolved themes lead to specific process improvements whose later use is documented. |
| Turnaround and flow | Start/end events or open-work handling are unknown. | A target is stated without corresponding data. | Bounded samples separate observed response intervals, missing times and still-open work; operating constraints are explained. | The team tests a flow improvement and compares appropriately matched windows without rewarding superficial approvals. |
| Emergency follow-through | Exception population, due date or follow-up window is unknown. | An emergency procedure is written. | Sample exceptions have rationale, accountable roles and evidenced post-change dispositions. | Missed follow-through is detected, addressed and checked again; maintained evidence is not just an incident narrative. |

Maintained practice may be supported by manual records. A single excellent example does not establish recurrence, and a sophisticated platform does not establish use. Conversely, missing tool comments do not disprove paired review. Record the channel where the team actually works and the evidence needed to understand that channel.

## 4. Facilitator walkthrough — fictional cases

### Case A: the approval looks complete, the evidence does not

Use ESS-102. Its final-head peer approval is dated and the export is complete, but no structured feedback is supplied. The executable result is `approval_only_recorded`, not “unreviewed code.” Ask whether a paired conversation or external document carries the reasoning. A useful improvement might be a short decision/context link in the existing workflow, not adding another approval layer. Completion evidence for that experiment is a future bounded sample in which another reviewer can reconstruct the decision.

### Case B: a real discussion covers a different revision

Use RIS-201. There is a peer discussion, but it identifies `old-v1`, not `final-v2`. Preserve the existing work and ask what intervened. A formatting-only edit, a new behavior change and a merge-resolution change may require different treatment. The result identifies a revision-evidence gap; it does not universally prescribe a complete rereview. An improvement option is recording the intervening-change rationale and linking the actual follow-up when material.

### Case C: follow-through exists after an emergency

Use IAM-301. The fictional service change merged at 09:15Z; a peer review at 10:00Z and documented resolution at 10:10Z precede its stated 11:00Z follow-up deadline. This supports on-time post-change follow-through in the supplied complete snapshot, not pre-merge review coverage. In a second pass add another open point to a later review. The tool must change the completion result rather than let the newest resolved item conceal it. Discuss how the actual team sees all outstanding points together.

### Case D: unknown is not a worse team

Compare RIS-202 and ESS-104. The former has a partial export; the latter has an undated review. Both are unassessable for a negative pre-merge coverage assertion. Neither demonstrates absence of review. Complete the observation boundary or recover the timestamp before comparing groups. As an assessment action, correcting evidence extraction is separate from improving the delivery practice itself.

### Case E: a late resolution cannot rewrite history

Use RIS-204. Its feedback was posted at 09:45Z, the change merged at 10:00Z, and the resolution was recorded at 10:30Z. Report the point as unresolved at delivery, then record the later closure. Ask whether deferral was explicit at 10:00Z and what it meant for the service. Do not say the point was open forever, and do not backdate the final disposition.

## 5. Proposed finding format

**Observation:** [Describe the bounded records, not a judgment about people.]

**Evidence:** [Source IDs, exact revisions/locators and observation window. Separate current artifact, interview explanation and missing material.]

**Context and competing explanations:** [Manual/paired channels, service criticality, staffing coverage, dependencies, timing gaps and sample selection.]

**Supported implication:** [State only the practice implication supported by those records. No code-defect claim without relevant evidence.]

**Proposed improvement:** [One practical workflow change, responsible role to confirm, implementation effort range to estimate with the team, dependency and potential burden.]

**How to test usefulness:** [A bounded future sample and observable outcome, e.g. decision reconstructability or fewer unresolved substantive points; not simply more comments or faster approval clicks.]

**Uncertainty / unresolved dissent:** [Record the alternative explanation and evidence that could change the conclusion.]

### Worked synthetic observation

In this constructed packet, three of eight assessable merged changes carry structured final-head peer feedback before delivery. Two of the ten merged cases remain unassessable for a negative statement. One of the three structured-feedback cases has an open point and another resolves only after merge. These facts support several different interview questions; they do not combine into a maturity score or establish that 70% of delivered changes lacked meaningful review.

A proportionate proposed experiment is to make review context and disposition links reconstructable in the workflow the team already uses. The delivery lead could estimate the burden with reviewers, trial the approach on an agreed bounded sample, and inspect whether later readers can explain decisions and exceptions. This is a proposal, not a scheduled activity, staffing assignment, or agreed University commitment.
