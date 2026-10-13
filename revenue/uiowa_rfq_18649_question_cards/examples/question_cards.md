# Follow-up interview question cards

**UIOWA-114 preparation artifact. Every observation, source, locator and role below is FICTION** invented for this kit. Nothing here is a University of Iowa finding, document or person, and no interview has been conducted, requested or scheduled.

Cards are grouped by interview session so a reviewer runs one sitting. They are deliberately **not ranked** — request prioritization is UIOWA-113's lane, and two rank orders in front of one reviewer is worse than none.

10 card(s) from 10 unresolved observation(s).

## Session S1 — ESS delivery and incident practice

### QC-ESS-AI-10 · ESS / ai_readiness · No corroborating record

**Ask:** ESS release engineer

**Question.** You've described that an AI coding assistant is in daily use on the ESS team. Is there a record produced by the system itself, rather than by a person describing it, that we could look at?

**Context for the practitioner.** Our only support for this is the ESS engineer interview. A corroborating record would let us state it rather than attribute it to one account.

**What is unresolved.** The claim that an AI coding assistant is in daily use on the ESS team rests on the ESS engineer interview alone; no second, independently produced record was supplied.

**Concrete request.** the licence or subscription record for that assistant, or confirmation of how it was obtained if there isn't one

**Decision this informs.** whether this is recorded as active departmental use or informal individual experimentation

**Where each answer leads:**

| If the answer is | The draft finding becomes |
|---|---|
| A departmental licence exists | Recorded as active use with a known procurement path |
| Obtained individually with no departmental record | Recorded as informal experimentation, kept separate from active use |
| It was trialled and discontinued | Neither active nor informal; recorded with its end date |

**Traceability.** observation `OBS-ESS-AI-10` · open findings `FIND-ESS-11` · sources: `SRC-ESS-INT-ENG` → `fictional-interviews/2026-03-04-ess-engineer.md#tooling`

---

### QC-ESS-SEC-07 · ESS / security · Two sources disagree

**Ask:** ESS incident commander

**Question.** On time to page the on-call engineer for a severity-1 incident: the ESS incident runbook indicates a 15-minute paging target; in the INC-0412 incident timeline, 47 minutes elapsed between detection and the page. Which of those reflects the normal case, and what accounts for the other one?

**Context for the practitioner.** We are working from the ESS incident runbook and the INC-0412 incident timeline only, and we are not assuming either one is wrong.

**What is unresolved.** For time to page the on-call engineer for a severity-1 incident, the ESS incident runbook and the INC-0412 incident timeline do not agree, and no exception record was supplied that would explain the difference.

**Concrete request.** the paging records for INC-0412, and the two most recent severity-1 incidents for comparison

**Decision this informs.** whether INC-0412 is representative of paging practice or a single-incident exception

**Where each answer leads:**

| If the answer is | The draft finding becomes |
|---|---|
| INC-0412 had a known alerting failure since corrected | Single-incident exception with a completed corrective action; strengthens the follow-through finding |
| Recent incidents show similar delays | Paging target is not being met in practice; becomes a priority finding |
| The timeline records detection later than actual detection | Timeline-accuracy issue; the finding is about incident record quality |

**Traceability.** observation `OBS-ESS-SEC-07` · open findings `FIND-ESS-08` · sources: `SRC-ESS-RUNBOOK` → `fictional-repo/ess/runbooks/incident.md#paging`; `SRC-ESS-INC-0412` → `fictional-repo/ess/incidents/INC-0412.md#timeline`

---

### QC-ESS-SW-04 · ESS / software · Only evidence predates a known change

**Ask:** ESS release engineer

**Question.** Our evidence for ESS automated test coverage is the ESS test-coverage report from 2025-12-18, before the March 2026 platform migration. Is there an equivalent record from after that change, or did the practice stay the same through it?

**Context for the practitioner.** We are not assuming the practice changed. We are asking whether the evidence still describes today.

**What is unresolved.** The only evidence for ESS automated test coverage is the ESS test-coverage report dated 2025-12-18, which predates the March 2026 platform migration.

**Concrete request.** a coverage report generated after the March 2026 migration, from the same tool if it is still in use

**Decision this informs.** whether the coverage figure we hold still describes the current codebase

**Where each answer leads:**

| If the answer is | The draft finding becomes |
|---|---|
| A post-migration report exists | Current figure replaces the stale one; finding states observed coverage |
| Coverage tooling was not carried through the migration | Measurement continuity gap; finding addresses the loss of the signal, not the coverage level |
| The codebase was unchanged by the migration | Stale report remains applicable; finding records the basis for accepting it |

**Traceability.** observation `OBS-ESS-SW-04` · open findings `FIND-ESS-05` · sources: `SRC-ESS-COV-RPT` → `fictional-repo/ess/quality/coverage-2025-12.html`; `SRC-ESS-MIG-NOTE` → `fictional-repo/ess/ops/migration-2026-03.md`

---

## Session S2 — Change control across shared services

### QC-ESS-DEP-01 · ESS / deployment · Two sources disagree

**Ask:** Change manager (shared services)

**Question.** On approvals on standard ESS changes: the ESS change procedure indicates two approvals are required; in the sampled ESS change records, only one approval appears on 7 of 12 sampled changes. Which of those reflects the normal case, and what accounts for the other one?

**Context for the practitioner.** We are working from the ESS change procedure and the sampled ESS change records only, and we are not assuming either one is wrong.

**What is unresolved.** For approvals on standard ESS changes, the ESS change procedure and the sampled ESS change records do not agree, and no exception record was supplied that would explain the difference.

**Concrete request.** the change records for CR-411 through CR-413 including their approval entries, and any standing exception that applies to them

**Decision this informs.** whether the two-approval control is operating, is documented-only, or has a standing exception we have not been shown

**Where each answer leads:**

| If the answer is | The draft finding becomes |
|---|---|
| A documented standing exception covers those seven changes | Control operates as written, with a scoped exception; finding becomes a validated strength with the exception noted |
| No exception exists; single approval is the normal practice | Documented control is not the operating control; finding becomes a policy-versus-practice gap |
| The sampled records are incomplete and the second approval lives elsewhere | Evidence-location gap rather than a control gap; request the second system's records |

**Traceability.** observation `OBS-ESS-DEP-01` · open findings `FIND-ESS-03` · sources: `SRC-ESS-CHG-PROC` → `fictional-repo/ess/policy/change-management.md#approvals`; `SRC-ESS-CHG-REC` → `fictional-repo/ess/change/records/2026-Q1-sample.csv`

---

## Session S3 — RIS reporting and data practice

### QC-RIS-AI-08 · RIS / ai_readiness · Nothing supplied

**Ask:** RIS data lead

**Question.** We did not receive a data inventory for the reporting warehouse. Does one exist, and where is it kept? If there isn't one, how is the outcome it would evidence achieved instead?

**Context for the practitioner.** The material we were given does not include a data inventory for the reporting warehouse. We are asking where it lives, not assuming it is absent.

**What is unresolved.** No data inventory for the reporting warehouse was supplied, although the RIS AI-readiness questionnaire, which refers to one indicates one would be expected.

> Absence in the material supplied to us is not evidence that no inventory exists.

**Concrete request.** the data inventory or catalogue the questionnaire refers to, in whatever form it exists, even a spreadsheet

**Decision this informs.** whether data readiness can be assessed at all for this group, or stays unassessed

**Where each answer leads:**

| If the answer is | The draft finding becomes |
|---|---|
| An inventory exists in some form | Data readiness becomes assessable; coverage and freshness can be examined |
| No inventory exists | Absence of a data inventory is itself the finding for AI readiness |
| An inventory exists but is maintained by another department | Ownership becomes the finding; request routed to the owning group |

**Traceability.** observation `OBS-RIS-AI-08` · open findings `FIND-RIS-09` · sources: `SRC-RIS-AI-QUES` → `fictional-interviews/2026-03-07-ris-ai-questionnaire.md`

---

### QC-RIS-DEP-05 · RIS / deployment · Window or subset may not generalize

**Ask:** RIS data lead

**Question.** The records we have for RIS deployment frequency cover three weeks in February 2026. Is that a typical period, and if not, which window would be?

**Context for the practitioner.** We would rather widen the sample than generalize from three weeks in February 2026.

**What is unresolved.** Evidence for RIS deployment frequency covers three weeks in February 2026; two of those weeks fall inside a published change freeze means it may not describe ordinary operation.

**Concrete request.** the deployment log for a twelve-week period that does not include a freeze, or confirmation of which weeks were frozen

**Decision this informs.** whether the observed deployment rate can be described as ordinary operation

**Where each answer leads:**

| If the answer is | The draft finding becomes |
|---|---|
| A longer log is available | Rate is measured over a representative window and can be stated |
| The three weeks are typical; the freeze affected other teams | Sample accepted with the basis recorded |
| Longer history is not retained | Measurement window becomes a stated limitation on the finding, not a performance claim |

**Traceability.** observation `OBS-RIS-DEP-05` · open findings `FIND-RIS-04` · sources: `SRC-RIS-DEP-LOG` → `fictional-repo/ris/deploy/log-2026-02.csv`

---

### QC-RIS-SW-02 · RIS / software · No corroborating record

**Ask:** RIS data lead

**Question.** You've described that every RIS change is peer reviewed before merge. Is there a record produced by the system itself, rather than by a person describing it, that we could look at?

**Context for the practitioner.** Our only support for this is the RIS team lead interview. A corroborating record would let us state it rather than attribute it to one account.

**What is unresolved.** The claim that every RIS change is peer reviewed before merge rests on the RIS team lead interview alone; no second, independently produced record was supplied.

**Concrete request.** a merge history export for the RIS reporting repository covering any four-week period, showing reviewer and approval state per change

**Decision this informs.** whether peer review can be stated as observed practice or must stay attributed to one account

**Where each answer leads:**

| If the answer is | The draft finding becomes |
|---|---|
| A merge history export is available | Claim moves from attributed to evidenced; strength can be stated directly |
| No tool record exists because review happens verbally | Practice is real but unevidenced; finding notes the corroboration limit rather than a gap in the practice |
| Review is applied to some repositories only | Scope becomes the finding; request the repository list and its basis |

**Traceability.** observation `OBS-RIS-SW-02` · open findings `FIND-RIS-01` · sources: `SRC-RIS-INT-LEAD` → `fictional-interviews/2026-03-05-ris-lead.md#code-review`

---

## Session S4 — IAM access administration

### QC-IAM-AI-06 · IAM / ai_readiness · True statement, unclear boundary

**Ask:** IAM administrator

**Question.** You've described that the team reports not using AI tools in its work. Does that cover assistants an individual engineer might have adopted without a departmental decision? If it differs case by case, what decides it?

**Context for the practitioner.** This is a scope question, not a challenge to the practice — the IAM administrator interview is clear that the team reports not using AI tools in its work.

**What is unresolved.** The material establishes that the team reports not using AI tools in its work (the IAM administrator interview), but does not establish whether that includes assistants an individual engineer might have adopted without a departmental decision.

**Concrete request.** a list of any AI-assisted tools currently in use by anyone on the team, however they were obtained, or confirmation that there are none

**Decision this informs.** whether the AI-use inventory records zero use or unknown use for this group

**Where each answer leads:**

| If the answer is | The draft finding becomes |
|---|---|
| Nobody uses any such tool | Inventory records a true zero for this group, which is a finding, not a blank |
| Some individual use exists outside a departmental decision | Inventory records informal use; separate from active and planned use |
| Nobody has asked, so it isn't known | Stays UNKNOWN in the inventory rather than becoming a zero |

**Traceability.** observation `OBS-IAM-AI-06` · open findings `FIND-IAM-07` · sources: `SRC-IAM-INT-ADMIN` → `fictional-interviews/2026-03-06-iam-admin.md#ai-tools`

---

### QC-IAM-SEC-03 · IAM / security · Nothing supplied

**Ask:** IAM administrator

**Question.** We did not receive a completed access-review record. Does one exist, and where is it kept? If there isn't one, how is the outcome it would evidence achieved instead?

**Context for the practitioner.** The material we were given does not include a completed access-review record. We are asking where it lives, not assuming it is absent.

**What is unresolved.** No completed access-review record was supplied, although the IAM access standard indicates one would be expected.

> Absence in the material supplied to us is not evidence that the review did not happen.

**Concrete request.** the most recent completed access review for one application of your choosing, including its date, reviewer, and the accounts it covered

**Decision this informs.** whether the annual review is performed and simply not in the supplied material, or is not currently performed

**Where each answer leads:**

| If the answer is | The draft finding becomes |
|---|---|
| A completed review exists and can be produced | Control evidenced; finding becomes a validated strength for the reviewed scope |
| Reviews happen informally without a retained record | Practice exists without durable evidence; finding addresses record retention, not the control |
| No review has been performed in the current cycle | Gap against the organisation's own standard; becomes a priority finding |

**Traceability.** observation `OBS-IAM-SEC-03` · open findings `FIND-IAM-02` · sources: `SRC-IAM-STD-ACC` → `fictional-repo/iam/policy/access-review.md`

---

### QC-IAM-SW-09 · IAM / software · True statement, unclear boundary

**Ask:** IAM administrator

**Question.** You've described that code review is mandatory before merge. Does that cover infrastructure and configuration repositories as well as application code? If it differs case by case, what decides it?

**Context for the practitioner.** This is a scope question, not a challenge to the practice — the IAM review standard is clear that code review is mandatory before merge.

**What is unresolved.** The material establishes that code review is mandatory before merge (the IAM review standard), but does not establish whether that includes infrastructure and configuration repositories as well as application code.

**Concrete request.** the list of repositories the review standard applies to, or the setting that enforces it, for one infrastructure repository

**Decision this informs.** whether the review control's scope includes the repositories that carry access configuration

**Where each answer leads:**

| If the answer is | The draft finding becomes |
|---|---|
| All repositories including infrastructure are covered | Scope confirmed; strength stated across both code and configuration |
| Application repositories only | Scope gap on the repositories that carry access configuration; becomes a specific, actionable finding |
| It varies by repository and is not centrally set | Consistency rather than existence is the finding |

**Traceability.** observation `OBS-IAM-SW-09` · open findings `FIND-IAM-10` · sources: `SRC-IAM-REV-STD` → `fictional-repo/iam/policy/code-review.md#scope`

---

## Coverage — nothing dropped silently

- Observations in register: **10**
- Cards built: **10**
- Suppressed with a stated reason: **0**
- Rejected with an error: **0** (none)
- Accounted for: **10 of 10**

## Diagnostics

None.
