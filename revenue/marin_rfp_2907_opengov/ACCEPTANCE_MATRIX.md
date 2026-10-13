# Marin RFP 2907 — implementation acceptance matrix

This is a reusable evidence skeleton for the proposed TJLabs specialist workshare. It is not populated with County production data and does not prove OpenGov pursuit, qualification, County acceptance, production readiness, or commercial acceptance.

## Result vocabulary

Every executable row terminates in one of:

- `PASS_WITH_EVIDENCE`
- `FAIL_WITH_EVIDENCE`
- `HOLD_MISSING_OWNER_EVIDENCE`
- `NOT_TESTABLE_FROM_SUPPLIED_EVIDENCE`

Every material result must identify its evidence class and references.

## Evidence classes

| Code | Meaning |
|---|---|
| `BUYER_CONTROLLING` | retained County RFP/addendum/clarification bytes |
| `BYTE_CUSTODY` | TJLabs retained exact artifact bytes and digest |
| `OWNER_EXPORT` | prime/County supplied export; provenance recorded separately |
| `PROVIDER_RECEIPT` | provider-generated execution/status receipt |
| `OWNER_ASSERTION` | named owner statement; never silently upgraded |
| `PUBLIC_FIRST_PARTY` | vendor/platform public first-party capability context |
| `PUBLIC_DISCOVERY` | public discovery context that is not controlling buyer evidence |

## A. Opportunity / input authority

| Rule | Required evidence | PASS condition | HOLD / failure |
|---|---|---|---|
| RFP generation | County RFP bytes + digest | exact controlling generation identified | only discovery summary available |
| addenda | County addenda/clarification evidence | current set enumerated | unknown current addenda |
| DOI status | prime evidence if relevant | explicit filed/not-filed/prime disposition | no inference from public silence |
| scope owner | prime/customer designation | named decision owner | no accountable owner |
| source generation | approved export evidence | one frozen generation | mixed/unknown generations |
| target generation | owner/provider evidence | target config/import generation identified | target state ambiguous |

## B. Source population profile

For each admitted fiscal/data family record:

- fiscal year/version;
- funds/fund groups;
- departments/divisions/programs;
- GL accounts/classifications;
- cost centers/projects;
- positions/job classifications where in scope;
- capital projects and funding sources;
- budget scenarios/versions;
- publication/narrative/document classes;
- row/object population;
- required-field completeness;
- duplicate/orphan/unmapped counts;
- source evidence refs.

Unknown populations remain HOLD; aggregate counts alone do not prove relationship integrity.

## C. Identity and hierarchy reconciliation

| Rule family | Source | Target | Required evidence | Result |
|---|---|---|---|---|
| fund identity | source fund key | target fund key | mapping + before/after evidence | pending |
| account identity | source account/classification | target account/classification | mapping + before/after | pending |
| department/program | source org keys | target org keys | mapping + hierarchy evidence | pending |
| position identity | position/job key | target workforce key | mapping where admitted | pending |
| capital project | source project key | target project key | mapping + relationship evidence | pending |
| funding source | source funding key | target funding key | mapping + relationship evidence | pending |
| scenario/version | source version | target version | version lineage | pending |

Identifier remapping is accepted only when explicitly owner-approved and traceable.

## D. Financial/value reconciliation

For each admitted population reconcile, as applicable:

- requested/adopted/revised budget values;
- revenues/expenditures/actuals used by the implementation;
- multi-year projections;
- salary/benefit/position values;
- capital budget values;
- capital expenditure/encumbrance values supplied by the owner;
- funding allocation values;
- fiscal period/year semantics;
- precision and rounding;
- negative/reversal/adjustment semantics;
- scenario/version semantics.

A matching aggregate total does not prove row-level or dimensional equivalence. TJLabs does not certify accounting treatment.

## E. Tyler Enterprise ERP import/API contract

Create one row per admitted scenario:

| Scenario family | Required input evidence | Expected behavior | Output evidence | Result |
|---|---|---|---|---|
| canonical import | approved fixture/export | owner-approved map | target/import report | pending |
| duplicate | duplicated record/batch | owner-approved duplicate policy | provider/target evidence | pending |
| retry | repeated request/batch | idempotent/retry behavior per contract | provider/target evidence | pending |
| invalid key | malformed/unmapped key | reject/HOLD per contract | error/QC evidence | pending |
| invalid amount/period | negative fixture | reject/HOLD per contract | error/QC evidence | pending |
| partial batch | mixed valid/invalid | owner-approved partial behavior | import/QC evidence | pending |
| scheduled process | owner-approved schedule | expected generation/run | run/provider evidence | pending |

For every scenario record:

- interface/file/API version;
- source generation;
- target/config generation;
- correlation/batch identity;
- expected mapping;
- automated QC/reporting output;
- observed result;
- exception id if non-PASS.

No production Tyler credentials or financial mutation are required by this matrix.

## F. Position / workforce planning seam

Where admitted:

- position/job-classification identity;
- department/cost-center relation;
- salary/benefit inputs;
- COLA/assumption generation;
- vacancy/filled status semantics;
- effective dates;
- projection horizon;
- scenario/version identity;
- reconciliation to owner-approved source evidence.

TJLabs tests evidence and mappings; it does not change HR records or approve compensation assumptions.

## G. Budget publication acceptance

For one frozen proposed/public budget generation verify, where applicable:

- County-approved template/branding generation;
- budget/FTE summaries;
- fund summaries;
- department/program narratives;
- financial schedules;
- performance metrics;
- source-data lineage;
- online/web output generation;
- printable/PDF generation;
- authorized edit/refresh behavior;
- accessibility evidence refs;
- generation/version identity.

Every displayed or published material value sampled for reconciliation links back to an admitted source or derived-rule evidence chain.

## H. Final SCO publication evidence

Against the prime-supplied controlling requirement map:

| Requirement | Source rule/data | Generated evidence | Result |
|---|---|---|---|
| SCO schedules 1–15 | owner-approved mapping | publication pages/data | pending |
| financing source/use | owner-approved mapping | schedule evidence | pending |
| fund balance | owner-approved mapping | schedule evidence | pending |
| debt | owner-approved mapping | schedule evidence where required | pending |
| position/classification | owner-approved mapping | schedule evidence | pending |
| special districts | owner-approved mapping | schedule evidence where required | pending |
| statutory checklist/deadlines | County requirement map | system/checklist evidence | pending |
| filing package | County requirement map | package inventory | pending |

TJLabs does not interpret law or certify legal compliance. `PASS_WITH_EVIDENCE` means only that the admitted owner-approved requirement has matching evidence.

## I. CIP acceptance

Where admitted, reconcile/test:

- project identity;
- department/location;
- scope/description/justification;
- budget/expenditures/funding sources;
- schedule/milestones/status;
- priority/scoring inputs and results;
- planning-year assignment;
- attachments/photos/maps refs;
- project update/change history;
- standardized project-page output;
- summary/funding/schedule output;
- web and printable publication generation.

## J. WCAG 2.2 AA implementation evidence

This section is not a VPAT/ACR and not a certification.

For each owner-approved representative page/document/training artifact, record evidence for applicable checks:

- keyboard navigation;
- focus order and focus visibility;
- headings/landmarks/semantics;
- accessible name/label;
- input instructions/error/status behavior;
- contrast evidence;
- non-color-only communication;
- table headers/associations;
- chart/data alternatives;
- image alt text;
- link purpose;
- screen-reader scenarios;
- zoom/reflow;
- motion/timing concerns where applicable;
- PDF tags/reading order/bookmarks where applicable;
- captions/transcripts where applicable;
- generated-output consistency;
- remediation/retest evidence.

Each test records user agent/assistive technology or test method, artifact generation, observed result and evidence refs. Vendor-wide conformance remains prime/assessor authority.

## K. SAML / role / access evidence

Where safely testable from supplied evidence:

| Scenario | Expected behavior | Evidence | Result |
|---|---|---|---|
| authorized admin | mapped admin role | owner/provider evidence | pending |
| department/fiscal user | scoped role | owner/provider evidence | pending |
| peer-review user | approved scoped access | owner/provider evidence | pending |
| unauthorized role | deny/restrict | negative evidence | pending |
| missing/invalid assertion | deny/fail closed per contract | negative evidence | pending |
| role change | owner-approved transition | before/after audit evidence | pending |

No production identity mutation is authorized.

## L. UAT / regression scenarios

Every scenario includes:

```text
scenario_id
requirement_or_rule_ref
config_generation
input_evidence_refs
expected_behavior
observed_behavior
result
evidence_refs
exception_id_if_any
retest_generation_if_any
```

Regression must include the material accepted paths plus owner-approved negative/boundary cases across migration, Tyler exchange, budget/CIP publication, access-control and accessibility evidence.

## M. Exception / HOLD row

Every unresolved item includes:

```text
exception_id
rule_or_scenario_ref
affected_population_or_artifact
evidence_refs
observed
expected
evidence_class
severity_or_disposition_owner
next_owner
next_action
closure_evidence_required
state = OPEN | HOLD | RETEST_READY | CLOSED_WITH_EVIDENCE
```

No deadline converts a HOLD to PASS.

## N. Cutover rehearsal

Record:

- source generation;
- target/configuration generation;
- mapping/transformation generation;
- Tyler interface/import generation;
- publication template/generation;
- accessibility evidence generation;
- preflight outcome;
- migration reconciliation summary;
- Tyler acceptance summary;
- publication/accessibility summary;
- UAT/regression summary;
- unresolved exceptions;
- rollback/restore prerequisites supplied by prime/platform;
- owner decision.

Allowed TJLabs terminal readiness state: `READY_FOR_OWNER_REVIEW`, `HOLD_OPEN_BLOCKER`, or `NOT_TESTABLE_FROM_SUPPLIED_EVIDENCE`. Production go-live remains owner authority.

## O. Commercial/authority closeout

Before any narrative calls the lane commercially successful, verify separately:

- `prime_pursuit = UNKNOWN` unless prime evidence proves otherwise;
- `declaration_of_interest_filed = UNKNOWN` unless prime/buyer evidence proves otherwise;
- `counterparty_interest = UNKNOWN` unless a human reply proves otherwise;
- `proposal_accepted = false` unless counterparty evidence proves otherwise;
- `contract_exists = false` unless executed-contract evidence proves otherwise;
- `work_authorized = false` unless authorization evidence proves otherwise;
- `invoice_exists = false` unless invoice evidence proves otherwise;
- `receivable_exists = false` unless contract/accounting evidence proves otherwise;
- `payment_received = false` unless provider evidence proves otherwise;
- `booked_revenue = false` and `recognized_revenue = false` unless accounting evidence/policy independently supports those states.

Repository merge, email send, reply, demo, proposal submission, contract execution, work authorization, invoice and payment are distinct evidence states.