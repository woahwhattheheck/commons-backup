# Ingham 112-26 — opportunity decision and paid acceptance workshare

## Decision state

**Current state: `BUILD_READY / CONTACT_HOLD / PROPOSAL_HOLD`.**

The opportunity is worth preparing for because the County has a live software procurement, a mandatory September 17 meeting, and documented operational pain around QA coverage, training, supervisor workload and workforce stability. It is not yet defensible to bid or contact externally from this lane because the controlling packet is inaccessible here and Gmail/Slack collision checks are rate-limited.

## Commercial role

TJLabs should not present itself as a turnkey NG9-1-1/CAD/telephony vendor on the evidence currently available. The strongest bounded role is:

> **Independent acceptance and evaluation workshare for an eligible 112-26 software vendor / integrator:** build reproducible evidence that the proposed software improves the agreed QA, training, hiring and operational workflows without silently losing, duplicating, corrupting or overstepping emergency-communications actions.

A buyer-side independent-evaluation role is also possible only if the controlling packet and County procurement path permit it.

This is a **paid specialist work package**. If an eligible vendor wants it, the next commercial artifact is a priced milestone SOW/subcontract after scope, environment, security, procurement role and authority are known. No free indefinite implementation is offered.

## Proposed milestones

### M0 — acceptance contract and environment boundary

Inputs:
- selected product/workflow(s);
- authoritative process/policy definitions;
- current integration map supplied by the authorized party;
- allowed data classes and de-identification rules;
- named operational, security/privacy and acceptance owners;
- existing buyer/vendor success criteria.

Outputs:
- testable workflow contracts;
- event/action taxonomy;
- human-authority boundary;
- fixture/data plan;
- evidence/retention plan;
- explicit out-of-scope/live-system constraints.

Acceptance: every tested behavior has a named expected disposition, permitted side effect, required human authority, evidence requirement and failure disposition.

### M1 — offline known-answer and failure corpus

Build synthetic/de-identified cases representing normal and stressed conditions relevant to the selected product, such as:
- representative QA-review cases;
- training/simulation cases;
- incomplete/malformed/stale/contradictory metadata;
- duplicate/replayed events;
- partial transcripts or recording references;
- delayed/unavailable integrations;
- permissions/role failures;
- changed policy/rubric versions;
- ambiguous cases requiring supervisor review.

Acceptance: corpus is versioned, provenance is explicit, restricted production content is absent, and expected outcomes are independently reviewable.

### M2 — deterministic acceptance harness

Execute the agreed vendor surface in an authorized non-production environment and emit durable receipts for inputs, versions, model/config state, outputs, side effects, human decisions and failures.

Acceptance: normal-path and hostile-path results are reproducible; unsafe/ambiguous cases stop or escalate as contracted; duplicates do not create duplicate state changes; evidence lineage is complete.

### M3 — operational-quality / workforce measurement

Instrument the agreed pilot without inventing baselines. Candidate measures include:
- QA coverage and sampling distribution;
- reviewer minutes per evaluated interaction;
- disagreement/escalation rate;
- false-positive / false-negative rate where a review gold set exists;
- coaching actions generated and closed;
- training-simulation throughput and retry patterns;
- policy/rubric adherence;
- hiring/onboarding assessment throughput where the product actually includes that scope;
- analyst/supervisor manual workload;
- exception/rework/rollback burden;
- availability/latency metrics appropriate to the product's non-dispatch or approved operational role.

Acceptance: every reported delta has a named source, window, denominator and exclusions. Forecasts are labeled forecasts.

### M4 — pilot-readiness / acceptance report

Deliver:
- pass/fail matrix;
- unresolved defects and operational risks;
- change/regression record;
- security/data boundary findings;
- human-override evidence;
- KPI evidence;
- explicit `ACCEPT / ACCEPT WITH CONDITIONS / DO NOT ACCEPT YET` recommendation for the tested scope.

Acceptance: recommendation is traceable to the agreed criteria and does not imply legal, regulatory, CJIS, medical or procurement certification.

## Binary technical acceptance criteria

For the contracted fixture set:

1. Every case has an attributable input/version/expected-disposition record.
2. Every output/score/classification can be tied to the exact rubric/policy/config/model/tool versions used.
3. Missing or invalid mandatory input causes an explicit fail/hold/escalation—not silent best-effort invention.
4. Retry/replay does not create a duplicate external state change.
5. Human-gated decisions prove human approval before the gated effect.
6. A vendor result cannot silently alter the source emergency record used for testing.
7. A dropped/unprocessed case is visible as a failure, not omitted from denominator metrics.
8. Integration timeout/partial failure leaves a visible recoverable state and owner.
9. Rubric/policy/model/tool changes invalidate stale acceptance evidence until regression rerun.
10. Rollback/reset is proven for every agreed reversible test side effect.
11. Restricted data does not appear in public logs/fixtures/repository artifacts.
12. Measured benefit claims resolve to observed evidence; invented savings/coverage/accuracy claims fail review.

## Explicit exclusions

Without separate authorization/evidence, TJLabs does **not** provide or claim:
- 9-1-1 call-taking or dispatch authority;
- CAD/CHE/telephony replacement;
- autonomous emergency triage or resource dispatch;
- modification of live emergency records;
- production credentials or unrestricted network access;
- CJIS/HIPAA/legal certification;
- buyer procurement advice as legal counsel;
- vendor qualification, insurance or references it does not actually possess;
- attendance at the mandatory meeting;
- prime-bidder status;
- proposal submission authority;
- an agreed price, teaming relationship, award, payment or revenue.

## Go / no-go gates before external pursuit

External pursuit becomes worth considering only if all are true:

- mailbox + Slack single-writer checks are complete and no prior owner has the route;
- the 112-26 packet and Addendum 1 are recovered and reviewed;
- the mandatory-meeting registration/eligibility path is still satisfiable;
- the packet permits the intended prime/subcontract or evaluator role;
- there is a qualified entity willing to own prime obligations if TJLabs cannot;
- the desired workshare matches actual packet scope;
- production/public-safety boundaries are documented;
- an authorized person can negotiate price and contracting terms.

If any hard procurement gate is already missed, the lane can still be useful as a **partner/subcontract opportunity** only if an eligible attending prime can legally add the workshare.