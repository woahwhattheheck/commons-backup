# Representative lesson segments — internal draft

These segments demonstrate a common responsible-AI teaching pattern across the five required occupational pathways plus career readiness. They are not a claim that any proposed partner or instructor has adopted them. Final curricula require partner/instructor and SCWDB review.

## Shared teaching pattern (45–60 minute segment)

1. **Scenario and authoritative evidence (5 min):** identify the work product, authoritative system/document, and the decision that remains human-owned.
2. **Data boundary (5 min):** separate public/synthetic/approved information from restricted data; redact or replace restricted fields before any exercise.
3. **Prompt contract (10 min):** state objective, allowed source material, output schema, uncertainty instruction, and prohibited actions.
4. **Hands-on generation (10 min):** participant uses an approved tool against synthetic or approved material.
5. **Verification pass (10 min):** participant traces claims to source facts, detects omissions/hallucinations, and corrects the output.
6. **Operational handoff (5 min):** export a checklist/template with source pointers and human approval field.
7. **Learning check (5 min):** participant explains one failure mode, one data rule, and one verification step.

A completed exercise is evidence of training activity—not authorization for the AI system to make consequential decisions.

---

## Manufacturing — shift quality / maintenance handoff

**Objective:** turn a synthetic shift log and maintenance note into a structured exception summary without letting the model decide disposition or equipment safety.

**Exercise:** Participants receive synthetic production notes containing three confirmed facts, two ambiguous observations, and one deliberately conflicting timestamp. They prompt an approved AI tool to produce a table with `fact`, `source`, `uncertainty`, and `recommended human follow-up` columns.

**Verification:** Participants must catch the timestamp conflict, reject any invented root cause, and link every retained fact to a source line.

**Boundaries:** no live control commands, no machine set-point changes, no safety bypass, no proprietary production data in unapproved tools. Maintenance/quality staff retain decision authority.

**Completion evidence:** corrected table + participant explanation of why the generated root-cause claim was rejected.

---

## Construction — specification / field-question preparation

**Objective:** use AI to organize a synthetic specification excerpt and field observation into questions for a qualified reviewer, not to make code/compliance/engineering decisions.

**Exercise:** Participants receive a short synthetic specification, drawing notes, and a fictional field condition. They request a comparison matrix: `requirement`, `observed condition`, `source`, `unresolved question`.

**Verification:** Participants identify one intentionally missing dimension and one conflict between notes. The correct output escalates them rather than choosing a design interpretation.

**Boundaries:** no representation that AI output is stamped engineering, code compliance, safety approval, change order, or legal interpretation. Do not upload confidential plans without authorization.

**Completion evidence:** source-linked matrix + two properly framed RFIs/questions requiring human resolution.

---

## Logistics — shipment exception triage

**Objective:** summarize synthetic shipment events into a replayable exception packet while preserving source events and human routing authority.

**Exercise:** Participants receive a small event log with a duplicate scan, delayed departure, and missing proof-of-delivery. They ask AI to draft an exception summary and a sequence of questions for the operations owner.

**Verification:** Participants must deduplicate without deleting source history, distinguish confirmed delay from inferred cause, and flag the missing proof-of-delivery.

**Boundaries:** no autonomous dispatch, carrier commitment, customs declaration, payment/refund, or customer promise. Use synthetic identifiers during training.

**Completion evidence:** exception packet with event IDs, explicit unknowns, and human disposition field.

---

## Healthcare — administrative workflow clarity

**Objective:** use AI on synthetic, nonclinical scheduling/referral-administration text to identify missing administrative fields while avoiding diagnosis, treatment, eligibility, or clinical prioritization.

**Exercise:** Participants receive a fully synthetic referral-administration form with missing contact/authorization metadata. They ask the tool to return only a completeness checklist and questions for staff.

**Verification:** Participants must reject any generated clinical recommendation and confirm that the output contains no invented patient facts.

**Boundaries:** no PHI in unapproved tools; no diagnosis, treatment, medical advice, utilization decision, triage, benefit determination, or clinical prioritization. Qualified humans retain all care decisions.

**Completion evidence:** administrative completeness checklist + identification of the prohibited clinical suggestion.

---

## Business operations — policy-to-process handoff

**Objective:** translate a synthetic internal policy into a draft operating checklist while preserving approvals and exceptions.

**Exercise:** Participants receive a fictional expense/requisition policy with thresholds, required documentation, and one ambiguous exception. They ask AI for a checklist that cites the governing clause for each step.

**Verification:** Participants must identify the ambiguous exception, prevent the tool from fabricating approval authority, and keep the original policy as the authoritative source.

**Boundaries:** no autonomous financial approval, signing, HR determination, legal conclusion, or external communication. Do not paste confidential employee/customer information into unapproved systems.

**Completion evidence:** clause-linked checklist with an explicit escalation for the ambiguous exception.

---

## Service B — AI-powered career readiness

**Objective:** improve a job application using only truthful participant-provided experience and public job information.

**Exercise:** Participant receives a synthetic resume and job posting. They prompt the tool to create (a) a gap checklist and (b) a draft bullet revision that may reorganize or clarify existing facts but may not invent experience, credentials, metrics, or employers.

**Verification:** The fixture includes a tempting missing certification and an unsupported performance metric. Participants must reject both if the model invents them and explain how to verify employer/company facts before use.

**Privacy / fairness boundaries:** avoid unnecessary sensitive personal data; never ask the tool to infer protected traits; use accessibility-friendly materials; participant approves every external representation; practice recognizing stereotyped or biased wording.

**Completion evidence:** corrected resume excerpt + a short verification log naming every changed claim and its source.

---

## Instructor guide notes

For every pathway, the final instructor guide should record:

- approved tool(s), version/access assumptions, and fallback if unavailable;
- exact synthetic/approved exercise fixture;
- expected failure injected into the exercise;
- observable completion evidence;
- accessibility accommodations and alternative interaction path;
- privacy/security reminder before tool use;
- prohibited decision boundary;
- answer key and debrief prompts;
- revision date and curriculum owner.
