# SYNTHETIC AIS practice-improvement roadmap — preparation example

**DRAFT_NON_AUTHORITATIVE · SYNTHETIC=True**

Relative calendar-day planning only; not appointments or commitments. Duration bounds are assumptions, not probabilities. Parallel layers show dependency independence, not available staffing. Capacity and maturity progression must be validated by the assessment team.

Input SHA-256: `2bd2723c8ec6f825095431cad4f04a81ccdd07fa9e407af52ff7247bc740a69d`

## Roadmap

|Recommendation|Group / owner role|Requested start phase|Start range|Finish range|Status / phase|Prerequisites|
|---|---|---|---|---|---|---|
|R01 — Establish service and evidence ownership|DEPARTMENT / Assessment coordinator|0-90|D0–D0|D10–D20|PLANNED / ON_PHASE|None|
|R02 — Pilot requirements-to-test review|ESS / ESS delivery lead|0-90|D10–D20|D25–D45|PLANNED / ON_PHASE|R01|
|R03 — Rehearse release recovery and verification|ESS / ESS service owner|0-90|D25–D45|D45–D80|PLANNED / ON_PHASE|R02|
|R04 — Clarify service-identity lifecycle roles|IAM / IAM service owner|0-90|D10–D20|D20–D40|PLANNED / ON_PHASE|R01|
|R05 — Run a security-event review pilot|IAM / IAM operational reviewer|0-90|D20–D40|D35–D65|PLANNED / ON_PHASE|R04|
|R06 — Adopt and compare the two practice pilots|DEPARTMENT / Practice improvement lead|90-180|D90–D90|D130–D150|PLANNED / ON_PHASE|R03, R05|
|R07 — Evaluate sustained practice and revise the roadmap|DEPARTMENT / Department assessment sponsor|180+|D180–D180|D195–D210|PLANNED / ON_PHASE|R06|
|R08 — Measure the AI workflow baseline|RIS / UNKNOWN|0-90|UNKNOWN|UNKNOWN|MISSING_DURATION / UNKNOWN|None|
|R09 — Evaluate an AI-assisted documentation pilot|RIS / RIS workflow lead|90-180|UNKNOWN|UNKNOWN|BLOCKED_BY_UNSCHEDULED_PREREQUISITE / UNKNOWN|R08|
|R10 — Map an external-interface transition|RIS / RIS integration coordinator|0-90|D0–D0|D80–D110|PLANNED / ON_PHASE|None|
|R11 — Rehearse the mapped interface transition|RIS / RIS release lead|0-90|D80–D110|D105–D145|PLANNED / AT_RISK|R10|
|R12 — Close transition follow-up and capture the outcome|RIS / RIS service owner|0-90|D105–D145|D115–D160|PLANNED / OUTSIDE_PHASE|R11|

## Dependency-independent layers

Same-layer items have no prerequisite path between them. Phases, staffing and budgets may still prevent simultaneous work.

Layer 0: R01, R10
Layer 1: R02, R04, R11
Layer 2: R03, R05, R12
Layer 3: R06
Layer 4: R07

## Outcomes and traceability

### R01
Practice change: Move from informal ownership to a maintained service-to-role register, without inferring a maturity rating.
Observable outcome: Three fictional service records have named accountable roles, supporting artifacts and a review date.
Finding refs: SYN-F-01
Evidence refs: synthetic_evidence.md#baseline
Assumptions: Elapsed days include interviews and review; staffing availability has not been confirmed.
Planning issues: None identified by this model

### R02
Practice change: Make sampled changes traceable from acceptance criteria to executed verification.
Observable outcome: For the next six fictional changes, record coverage and unresolved acceptance criteria; do not count document completion as improved quality.
Finding refs: SYN-F-02
Evidence refs: synthetic_evidence.md#ess-review
Assumptions: Pilot is limited to one release stream; existing delivery work continues.
Planning issues: None identified by this model

### R03
Practice change: Turn a written recovery procedure into a rehearsed, evidence-backed practice.
Observable outcome: One synthetic rehearsal records decision points, recovery elapsed time, business checks and follow-up actions.
Finding refs: SYN-F-03
Evidence refs: synthetic_evidence.md#ess-recovery
Assumptions: No production rollback is performed; the practice rehearsal uses fictional records.
Planning issues: None identified by this model

### R04
Practice change: Attach lifecycle responsibility and successor roles to documented service identities.
Observable outcome: Each fictional identity has an owner, purpose, renewal/retirement decision and continuity dependency.
Finding refs: SYN-F-04
Evidence refs: synthetic_evidence.md#iam-lifecycle
Assumptions: This models documentation work only; it does not change access or credentials.
Planning issues: None identified by this model

### R05
Practice change: Connect selected operational evidence to review ownership and documented follow-through.
Observable outcome: Two synthetic review cycles show selected events, dispositions, escalation rationale and actions still open.
Finding refs: SYN-F-05
Evidence refs: synthetic_evidence.md#iam-review
Assumptions: Review time is an elapsed-duration estimate; actual recurring staff effort remains to collect.
Planning issues: None identified by this model

### R06
Practice change: Extend demonstrated practices only after reviewing each pilot and preserving cross-group differences.
Observable outcome: Compare baseline and follow-up using equivalent windows; retain disagreements and reject unsupported improvement claims.
Finding refs: SYN-F-06
Evidence refs: synthetic_evidence.md#adoption
Assumptions: Dependency-only earliest-start bounds assume suitable staff can work after the pilot reviews.
Planning issues: None identified by this model

### R07
Practice change: Review whether practices remain used and produce the intended outcomes before proposing another maturity step.
Observable outcome: Retain sustained-use evidence, outcome trends, counterexamples and a revised prioritization rationale.
Finding refs: SYN-F-07
Evidence refs: synthetic_evidence.md#sustain
Assumptions: A one-to-two-level progression is a proposed assessment goal, not a predicted score or guaranteed result.
Planning issues: None identified by this model

### R08
Practice change: Replace an assumed productivity benefit with a comparable baseline measurement design.
Observable outcome: Identify comparable tasks, repair effort, outcome criteria and a collection owner before estimating a pilot.
Finding refs: SYN-F-08
Evidence refs: synthetic_evidence.md#ai-unknown
Assumptions: Duration and ownership are deliberately unknown; no productivity multiplier is assumed.
Planning issues: owner_role_unknown; duration_unknown

### R09
Practice change: Compare a bounded assisted workflow with its measured baseline using the same acceptance criteria.
Observable outcome: Report accepted outputs, checking and rework time, unresolved cases and recurring maintenance separately.
Finding refs: SYN-F-09
Evidence refs: synthetic_evidence.md#ai-pilot
Assumptions: The pilot cannot receive start/finish estimates until R08 is estimated; no model service is called.
Planning issues: unscheduled_prerequisite:R08

### R10
Practice change: Turn an uncertain external change window into an explicit dependency and evidence collection plan.
Observable outcome: Document the interface version, owner, transition window and compatibility evidence needed for a rehearsal.
Finding refs: SYN-F-10
Evidence refs: synthetic_evidence.md#external-interface
Assumptions: The 80–110 day range is wholly synthetic and intentionally crosses the phase boundary.
Planning issues: work_may_span_phase_boundary

### R11
Practice change: Test the documented transition after the dependency mapping is available.
Observable outcome: A fictional compatibility rehearsal records failures, mitigations and pending external inputs.
Finding refs: SYN-F-11
Evidence refs: synthetic_evidence.md#transition-rehearsal
Assumptions: The requested first-phase start is at risk; the predecessor may not finish until day 110.
Planning issues: requested_start_phase_at_risk; work_may_span_phase_boundary

### R12
Practice change: Use rehearsal results to choose follow-up work rather than asserting completion from a planned date.
Observable outcome: Link each mitigation to a verification record and explain changed or unresolved actions.
Finding refs: SYN-F-12
Evidence refs: synthetic_evidence.md#transition-closeout
Assumptions: The first-phase request is demonstrably infeasible even at the optimistic bound; it is not silently rephased.
Planning issues: requested_start_phase_outside_phase; work_may_span_phase_boundary

## Document assumptions

All groups, findings, service facts, timings and outcomes in this collection are fictional; none are University findings.
Day zero is a hypothetical planning origin, not a booked kickoff or a calendar date.
A phase is a requested start horizon: [0,90), [90,180), [180,infinity). Work may finish in a later phase.
Elapsed duration is not staff effort. Parallel dependency layers are not evidence of available capacity.
Recommendations and priorities require professional review. This planner does not compute maturity or select products.
