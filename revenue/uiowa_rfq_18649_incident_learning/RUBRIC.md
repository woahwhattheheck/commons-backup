# Incident-learning interview and artifact-review rubric

**UIOWA-067 · preparation instrument · all worked examples are synthetic.** Use alongside the executable packet and source appendix. Do not grade individual responders or infer a group's maturity from one incident.

## Session method

Ask the group to select one incident with consequential user impact and one contrasting event. Obtain the incident census or describe how the sample was selected. Include a recently closed corrective action and an older unresolved or replaced action. A service owner, practitioner and relevant shared-service role can discuss the same event together; record differing accounts rather than scheduling one interview per person. These are proposed participation roles, not invitations or availability commitments.

Read the timeline and the actual change/verification records before concluding that an action is complete. Capture the source version, exact locator, period, service and coverage. Ask what information was available at each decision point. Replace “Who made the mistake?” with “What conditions made this outcome possible, and what supported or constrained the response?”

## Seven evidence dimensions

| Dimension | Questions and artifact request | Supported characterization | Unknown or weak support | Practical follow-through |
|---|---|---|---|---|
| Impact and timeline | What failed for users? When did it begin, become known, recover and pass a business check? Request incident record, event locators and timezone/clock interpretation. | Events and elapsed intervals connect to retained records with explicit definitions. | Reconstructed recollection only; missing start or verification; ambiguous clocks. | Retain a few defined milestones and user-visible checks rather than increase narrative length. |
| Coordination | Which service and dependency roles exchanged what information? What handoff changed the response? Request coordination notes and role ownership. | Records connect coordination to a decision and preserve handoffs. | A role list or a generic escalation policy with no example. | Clarify role handoff and dependency contacts; rehearse one representative scenario. |
| Restoration | What business function proved usable again? What remained degraded? Request representative transaction or service-verification evidence. | Restoration declaration is distinguished from demonstrated business recovery and residual limitations. | Infrastructure green, ticket closed, or verbal assurance alone. | Add a small repeatable business check and retain its result. |
| Postmortem quality | What contributing conditions and alternative explanations were considered? How were disagreements and limitations treated? | Supported conditions, impact, response tradeoffs and unresolved questions remain traceable. | Long narrative, polished causal claim, personal blame, or one unsupported root-cause assertion. | Preserve evidence for the important conditions and keep focused unanswered questions. |
| Action design | Which condition does this action address, who owns its continuation, and what observable result would count? | A clear condition-to-action link, role, expected result, due/revisit point and reasonable dependencies. | “Improve monitoring” or “train everyone,” absent ownership, undefined completion. | Rewrite the action around a verifiable behavior and adoption effort, not a tool purchase. |
| Completion and changed approach | What changed? Where is implementation evidence and the subsequent verification? Why was an alternative chosen? | Implementation and verification link to the action; replacement decision retains rationale and successor conditions. | Closure click; source type mismatch; missing verification; replacement that hides unfinished work. | Recover the missing evidence, re-demonstrate the behavior where appropriate, or document the justified successor and residual work. |
| Learning effectiveness | Was exposure observed after implementation? Are event rules, cohort, unit and coverage comparable? Was learning shared? | Descriptive outcomes with explicit denominator and limits, plus evidence of knowledge sharing. | No further incident without a census; activity counts treated as reliability gains; different cohorts silently combined. | Choose a modest follow-up observation window and retain its denominator; distinguish a useful observation from causal proof. |

These are evidence anchors, not a numeric scale. Use `unknown`, `described`, `demonstrated in the supplied case`, and `observed follow-through` in the narrative with source support. Policy-only descriptions and interview-only examples can be useful discovery inputs without becoming measured practice. The overall assessment framework should determine maturity separately.

## Worked postmortem-to-backlog trace

### ESS: one evidenced implementation, shared work still outstanding

`INC-ESS-1 → COND-QUEUE → ACT-01 → EV-IMPL → EV-VERIFY` shows a bounded-retry change and a subsequent business-function rehearsal. `EV-BEFORE` and `EV-AFTER` supply a comparable fictional descriptive rate of 6 versus 1 retry storms per 1,000 registration attempts. This supports “the supplied change was demonstrated and the sampled rate was lower,” not “the system is now permanently reliable.”

`ACT-02` covers the same contributing condition across ESS and RIS and remains nine days overdue unresolved at the packet's as-of time. Do not count it twice or claim that completing the ESS client change fixed all consumers of the shared queue. Ask for cross-consumer exercise evidence and the resource needed to complete it.

### RIS: detailed review and a closure label, missing restoration proof

`INC-RIS-1` has a retained narrative and restoration declaration but no retained business-verification milestone. `ACT-03` is reported closed, yet no implementation or verification source establishes that its intended record-retention improvement occurred. The output is `closure_unverified`, not a claim of dishonest reporting or failed engineering. Ask whether the artifact exists under another version/locator, whether the completion definition changed, or whether a representative re-demonstration is needed.

### IAM: a justified change in approach does not finish the replacement

`INC-IAM-1 → COND-TIMEOUT → ACT-04 → EV-DECISION → ACT-05` preserves a decision to replace a broad platform rewrite with focused timeout behavior and verification. The hypothetical rationale is lower adoption effort and a testable response to the observed condition. The original action is `replacement_documented`; `ACT-05` remains open and two days overdue unresolved. `ACT-06`, dependency-map work, has neither established owner role nor due/revisit point. The analyst should not present these as a completed resilience improvement.

`COND-MAP` has no supporting source yet. Its presence in the packet represents an issue to investigate, not a proven deficiency. The unsupported impact-start milestone means IAM impact duration stays unknown even though a plausible timestamp was written down.

## Improvement options for a multi-application team

| Option | Proposed effort assumption | Dependency | Observable progress | Tradeoff |
|---|---|---|---|---|
| Retain canonical milestones and source locators for the next selected incidents | 2–4 role-hours to agree fields, then 10–20 minutes per selected incident | Common event definitions and accessible existing records | Another practitioner can reconstruct a case without asking its original author | Adds record-keeping; keep only fields needed for decisions. |
| Link corrective actions to conditions and business checks | 4–8 role-hours for the initial backlog sample, then part of the existing work review | Owner roles and a usable backlog | Each sampled closure has implementation and appropriate verification evidence | Avoid creating a duplicate tracking system. |
| Reconcile overdue and replaced work | 2–6 role-hours with service/dependency roles | Evidence of decisions and successor actions | No abandoned action disappears; justified alternatives retain conditions and next steps | Re-scoping can be more valuable than mechanically closing the original task. |
| Compare selected outcomes with exposure | 4–12 analyst/service role-hours for a first measure | A complete-enough measurement source and stable definitions | Before/after rates retain numerator, denominator, cohort and uncertainty | Collection may cost more than a rare-event comparison is worth; a targeted rehearsal can be more useful. |

All effort ranges are illustrative planning assumptions, not University staffing facts or committed dates. Start with the least record-keeping that answers the relevant operational question. Broader shared-service improvements can proceed when their prerequisites and evidence justify them; this is not a mandate for universal automation.

## Discussion record template

```text
Incident / group / service:
Sampling period and selection rationale:
Available records, versions and exact locators:
Known user impact and unresolved impact questions:
Timeline definitions / clock uncertainty:
Coordination decisions and role handoffs:
Business restoration evidence and residual limitations:
Supported contributing conditions / competing explanations:
Corrective action IDs and intended observable change:
Implementation evidence / verification evidence:
Replacement rationale, decision source and successor:
Before/after event rule, windows, cohort and exposure:
Shared-learning evidence:
Unresolved disagreement and smallest factual follow-up:
Proposed practice change, effort range and organizational role:
```

## Source use

The blameless, evidence-linked approach draws on Google SRE [Chapter 15](https://sre.google/sre-book/postmortem-culture/), accessed September 19, 2026. The seven dimensions, examples, state names and effort assumptions are this preparation kit's design, not a mandated university policy or an empirical peer benchmark. The full engagement's evidence, scope and assessment framework remain necessary.
