# RACI, security/data boundary, and ROI instrumentation

## RACI boundary

`A` = accountable, `R` = responsible for the bounded work, `C` = consulted, `I` = informed. The table is a proposed allocation only and must be confirmed by the actual prime/TTUHSC before work.

| Area | Eligible prime / Keywell if confirmed | TJLabs technical workstream | TTUHSC owner(s) |
|---|---|---|---|
| Proposal / TechBid submission | A/R | I | I |
| Prime qualifications, references, bidder certifications | A/R | I | I |
| VetHUB subcontracting plan | A/R | C only if TJLabs facts are requested | I |
| Enterprise AI strategy/governance | A/R | C | A/C for institutional decisions |
| Security/privacy architecture approval | R | C/R for test evidence only | A |
| Workflow selection / business priority | R | C | A |
| Workflow contract and acceptance criteria | A | R | A/C |
| Synthetic/sanitized fixture design | A/C | R | A/C for data rules |
| Production data authorization | C | I | A/R |
| Acceptance harness and failure injection | C | A/R | C |
| Human approval policy | C | R to test enforcement | A/R |
| Pilot deployment authorization | R | C | A |
| ROI/adoption metric definitions | R | R for instrumentation | A/C |
| Final program reporting / knowledge transfer | A/R | C/R for workstream artifacts | C |
| Clinical/academic/administrative operational decisions | C | I | A/R |

No row grants TJLabs authority to certify legal compliance, approve patient-care decisions, commit the prime, or access TTUHSC systems/data without an explicit authorized path.

## Security and data-handling boundary

### Default state

Before an approved environment and data path exist, the workstream uses only synthetic or properly sanitized fixtures. Public repository artifacts must contain no PHI, FERPA-protected records, credentials, secrets, proprietary institutional data, or private partner material.

### Requirements to capture before any restricted-data test

- authoritative data classification;
- permitted purpose and minimum necessary fields;
- de-identification/sanitization rules where applicable;
- named data owner and security/privacy owner;
- approved environment and storage locations;
- identity/RBAC/SSO integration path;
- encryption requirements in transit and at rest;
- retention/deletion rules;
- logging/telemetry boundaries and prohibited payload fields;
- incident/escalation path;
- model/provider data-use terms, including the RFP requirement that TTUHSC data not be used to train vendor proprietary models;
- egress/tool/network restrictions;
- approved human-review roles.

The RFP's enterprise requirements are requirements to satisfy, not claims that this package has already implemented or certified them.

## Human authority boundary

Every selected workflow must explicitly classify actions into:

- `AUTOMATED_ALLOWED` — may execute within the approved policy and permission envelope;
- `HUMAN_APPROVAL_REQUIRED` — may be prepared by automation but cannot execute before attributable approval;
- `HUMAN_ONLY` — automation may supply evidence, but cannot make/execute the decision;
- `PROHIBITED` — must stop.

The acceptance harness tests those classifications directly, including negative cases.

## ROI and adoption instrumentation

No baseline number is invented. The prime and TTUHSC define the measurement window and authoritative system of record. TJLabs can instrument the selected workflow with exact event boundaries so before/after comparisons are reproducible.

Recommended metrics:

| Metric | Definition |
|---|---|
| Cycle time | `completed_at - accepted_at` per comparable workflow instance |
| Touch time | measured human-active time attributable to the workflow |
| Exception rate | exceptions / eligible instances |
| Rework rate | instances reopened or materially corrected / completed instances |
| Duplicate-action rate | duplicate external state changes / logical actions; target for retry-safe actions is zero |
| Failure-to-stop rate | unsafe/invalid injected cases that executed an action / unsafe/invalid injected cases; target zero |
| Human-approval fidelity | required gated actions with valid pre-action approval / all gated actions; target 100% |
| Evidence completeness | actions with complete version/provenance/owner receipt / actions |
| Adoption | active eligible users or teams / eligible users or teams during agreed window |
| Utilization | completed assisted workflow instances / eligible workflow instances |
| Unit cost | agreed labor + platform/model/tool cost / successfully completed comparable instances |
| Recovery burden | incidents requiring manual recovery and minutes-to-recover |

### Value statement rule

A financial or operational benefit is publishable only if its numerator/denominator, measurement window, source system, exclusions, and comparison baseline are named. Forecasts must be labeled forecasts. No savings, ROI, adoption, or error-reduction percentage is treated as achieved until measured.

## Partner facts required before a priced subcontract proposal

1. Keywell confirms it is actively pursuing the RFP and is eligible to do so.
2. Any mandatory pre-bid/registration condition is confirmed from the procurement record by the prime.
3. Keywell confirms it is open to a TJLabs technical subcontract/work package.
4. The prime identifies one or more workflows where this evidence layer is useful.
5. Prime/TTUHSC identify environment, security/privacy owner, and data boundary.
6. Prime owns/allocates references, VetHUB, bidder certifications, insurance, Texas/TX-RAMP obligations and proposal submission.
7. Schedule and integration dependencies are known.
8. An authorized party can agree pricing/milestones and contracting path.

Until all eight are evidenced, status remains `HOLD_FOR_PARTNER_FACTS`.