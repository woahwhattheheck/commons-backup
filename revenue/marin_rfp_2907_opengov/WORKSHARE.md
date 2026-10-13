# Marin County RFP 2907 — Tyler / migration / publication acceptance workshare

**State:** `PROPOSED_NOT_ACCEPTED`  
**Buyer opportunity:** County of Marin, RFP 2907 — County Budget Software System  
**Candidate prime/platform counterparty:** OpenGov  
**Commercial hypothesis:** USD 48,000 fixed fee  
**Delivery target:** 20 business days after complete approved inputs  
**Owner:** Token Junkie Labs (TJLabs)  
**External state:** NOT SENT — separate current Muse single-writer clearance and immediate Slack/Gmail recensus required before any contact.

## 1. Purpose

This packet defines a bounded specialist acceptance workshare that can sit behind a qualified software prime responding to Marin County RFP 2907.

The controlling County RFP is publicly retained. It requests a modern cloud budget-development and Capital Improvement Program (CIP) management system integrating with Tyler Enterprise ERP (formerly Munis), including budget/workforce/capital planning, budget/CIP publication, data migration, testing, digital accessibility evidence, training and post-launch support. The final proposal deadline is September 30, 2026 at 5:00 p.m. PT. The County requested a non-binding Declaration of Interest by September 10; this packet has no evidence that OpenGov filed one and does not infer that it did.

Current OpenGov first-party material describes public-sector Budgeting & Performance / Capital Planning products, county and municipal use cases, accessible budget-book use cases, and existing-system integration including Tyler/Munis. That makes OpenGov a plausible prime candidate for a paid specialist inquiry. It does **not** establish that OpenGov is pursuing this RFP, satisfies every requirement, needs TJLabs, or has authorized any representation.

TJLabs proposes an evidence-first implementation-acceptance slice: Tyler interface/import reconciliation, historical migration reconciliation, budget/CIP publication acceptance, SCO/GFOA output evidence, WCAG 2.2 AA implementation-deliverable evidence, SAML/role evidence mapping, UAT/regression evidence, go/no-go readiness and an exception/HOLD ledger. TJLabs does not own the platform, submit the County proposal, make the vendor's corporate/certification representations, or decide production go-live.

## 2. Frozen work package

The fixed-fee package covers one owner-approved implementation slice identified at kickoff by a frozen scope key containing:

- one prime/customer implementation identifier;
- one controlling RFP/addenda generation supplied by the prime;
- one approved legacy budget/CIP source export family;
- one approved target import/export/read-only evidence family;
- one Tyler Enterprise ERP interface/import contract;
- one Tyler position/workforce evidence contract where admitted;
- one approved fund/account/classification mapping generation;
- one budget-book publication template/generation;
- one CIP publication template/generation;
- one SCO Final Budget Book acceptance requirement generation;
- one SAML/role/access configuration generation;
- one WCAG/accessibility evidence generation;
- one UAT/regression requirement set;
- one cutover rehearsal generation;
- one owner-designated acceptance decision authority.

No additional system, interface, department, fiscal year, data family, publication family, certification, onsite obligation, production mutation, or buyer submission is silently included.

## 3. Source and migration profiling

Before migration conclusions, TJLabs produces a source/evidence manifest from owner-approved exports.

Where meaningful it records:

1. evidence/artifact identifiers;
2. byte digests for material in TJLabs custody;
3. source system/export generation supplied by the owner;
4. fiscal years and dataset populations;
5. fund, account, department, program and classification keys;
6. position/workforce keys where in scope;
7. capital-project identifiers and relationships;
8. required-field completeness distributions;
9. duplicate/orphan/unmapped populations;
10. date/fiscal-period/currency/precision conventions;
11. narrative/document/publication content classes;
12. known mapping/transformation rules;
13. evidence gaps that block stronger conclusions.

A filename, screenshot, row count, operator statement, public marketing page or self-described export does not prove completeness by itself. Missing or contradictory evidence becomes `HOLD_SOURCE_EVIDENCE`.

## 4. Migration reconciliation

Every admitted migration rule terminates in exactly one evidence-backed state:

- `PASS_WITH_EVIDENCE`;
- `FAIL_WITH_EVIDENCE`;
- `HOLD_MISSING_OWNER_EVIDENCE`;
- `NOT_TESTABLE_FROM_SUPPLIED_EVIDENCE`.

### 4.1 Budget hierarchy and identity

Reconciliation may cover:

- fiscal year;
- fund and fund group;
- department/division/program;
- general-ledger account/classification;
- cost center/project references;
- budget version/scenario identity;
- position/job-classification identity;
- capital-project identity;
- funding-source identity;
- document/narrative references;
- approved identifier remaps.

No identifier remap is interpreted as preservation unless the semantic owner approves it and the mapping is traceable.

### 4.2 Financial values

Where in scope and supported by supplied evidence:

- adopted/revised/requested budget values;
- actual/expenditure/revenue values used by the implementation;
- multi-year projections;
- capital project budgets/funding/expenditures/encumbrances supplied by the owner;
- salary/benefit/position planning values;
- amount/currency precision and rounding;
- fiscal-period semantics;
- positive/negative/adjustment treatment;
- scenario/version semantics.

TJLabs reconciles the admitted evidence contract. It does not approve accounting treatment, certify financial statements, or mutate the County ledger.

### 4.3 History and narrative

Where supplied:

- historical year/version retention;
- change/rationale history;
- budget narratives and executive summaries;
- department/program descriptions;
- capital-project narrative, milestone, location and justification fields;
- attachment/photo/document references.

Sampling is allowed only under a frozen owner-approved rule. A passing sample never silently proves the unsampled population.

## 5. Tyler Enterprise ERP acceptance seam

For the owner-approved Tyler/Munis contract, TJLabs creates reviewer-verifiable acceptance evidence for the admitted interface or file exchange.

Possible scenario families:

- canonical fund/account/classification mapping;
- department/cost-center/project mapping;
- position/workforce mapping where admitted;
- capital project budget/expenditure/encumbrance mapping where admitted;
- fiscal period and amount precision;
- import/export generation identity;
- duplicate/retry/idempotency behavior;
- malformed/invalid record behavior;
- missing-reference behavior;
- partial batch behavior;
- automated import quality-control evidence;
- scheduled/repetitive-process evidence;
- reconciliation from source extract to admitted target representation;
- explicit HOLD where production-only behavior cannot safely be exercised.

TJLabs does not use production Tyler credentials, post journal entries, change financial records, alter positions, or represent County financial close correctness.

## 6. Budget / CIP publication acceptance

For one frozen publication generation, TJLabs constructs a requirement-to-evidence matrix around owner-approved output.

### 6.1 Proposed / public budget evidence

Where admitted:

- County branding/template requirements;
- budget and FTE summaries;
- fund summaries;
- department/program narratives;
- financial schedules;
- performance metrics;
- online/web publication;
- printable/digital PDF publication;
- editability/refresh behavior from source data;
- accessible output evidence.

### 6.2 Final SCO budget evidence

Against the prime-supplied controlling County/SCO requirement set, the harness may check:

- required SCO schedules 1–15;
- financing source/use and fund-balance schedules;
- debt schedules where required;
- position/classification schedules;
- special-district schedules where required;
- statutory deadline/checklist behavior;
- filing-package completeness references;
- source-data lineage into generated schedules;
- output version/generation identity.

TJLabs does not provide legal advice or certify statutory compliance. The prime/County retains interpretation and filing authority.

### 6.3 CIP publication evidence

Where admitted:

- standardized project pages;
- project description/department/location;
- cost/funding source;
- schedule/status/milestones;
- project justification;
- project/funding summary tables;
- maps/charts/images where required;
- planning-year assignment and prioritization output;
- Board-ready printable/web publication evidence.

## 7. Accessibility acceptance evidence

The RFP requires WCAG 2.2 AA evidence for digital content and deliverables and asks detailed product-accessibility questions. TJLabs can provide an implementation-level acceptance evidence matrix, but does not issue a VPAT/ACR or certify the platform.

For owner-approved pages/documents/training/configuration artifacts, the matrix may cover supplied evidence for:

- keyboard-only navigation;
- focus order/visibility;
- semantic headings/landmarks;
- accessible names/labels;
- form error/status behavior;
- color/contrast evidence;
- table semantics;
- charts/data alternatives;
- image alternative text;
- PDF tag/reading-order evidence;
- screen-reader scenarios;
- captions/transcripts for admitted media;
- zoom/reflow/responsive behavior;
- generated document consistency;
- known accessibility defects and remediation retest evidence.

Formal conformance claims, product VPAT/ACR, legal accessibility compliance and roadmap commitments remain with the prime/vendor and qualified assessors.

## 8. SAML / role / security evidence seam

For the supplied non-production or owner-run evidence contract, TJLabs may trace:

- SAML v2 configuration identifiers;
- expected identity/role mappings;
- administrator vs department/fiscal-user roles;
- unauthorized-role negative cases;
- login/logout/session evidence supplied by the owner;
- audit/activity evidence supplied by the platform;
- data/environment separation evidence supplied by the prime;
- secret-handling boundaries;
- unresolved certification/control evidence as HOLDs.

TJLabs does not provision production identities, certify cybersecurity/privacy compliance, or replace the County's security review.

## 9. UAT, regression and go/no-go evidence

TJLabs produces a reviewer-verifiable acceptance plan for the frozen slice.

Each admitted scenario records:

- stable scenario id;
- requirement/rule reference;
- prerequisite/configuration generation;
- input/evidence refs;
- expected behavior;
- observed behavior;
- result state;
- exception id where not PASS;
- retest generation/evidence when fixed.

The regression set includes the material accepted happy paths plus owner-approved negative/boundary cases across migration, Tyler imports, publication generation, access control and accessibility evidence.

The final readiness matrix may emit:

- `READY_FOR_OWNER_REVIEW`;
- `HOLD_OPEN_BLOCKER`;
- `NOT_TESTABLE_FROM_SUPPLIED_EVIDENCE`.

It may **not** emit independent `PRODUCTION_GO` or waive a County/prime blocker.

## 10. Exception / HOLD ledger

Every unresolved item has at minimum:

- stable exception id;
- requirement/rule/scenario reference;
- affected population/object;
- evidence references;
- observed result;
- expected result;
- evidence class;
- owner-approved severity/disposition;
- next owner and action;
- closure evidence required;
- state `OPEN`, `HOLD`, `RETEST_READY`, or `CLOSED_WITH_EVIDENCE`.

No exception disappears because the proposal or go-live deadline arrives.

## 11. Cutover rehearsal / readiness

The package includes one bounded rehearsal on owner-approved safe evidence.

Record:

1. source generation;
2. target/configuration generation supplied by owner;
3. mapping/transformation generation;
4. Tyler interface/import generation;
5. publication template/generation;
6. accessibility evidence generation;
7. preflight gates;
8. migration reconciliation summary;
9. interface acceptance summary;
10. publication/accessibility acceptance summary;
11. unresolved exceptions;
12. rollback/restore prerequisites supplied by the prime/platform;
13. final owner decision evidence.

TJLabs does not execute production cutover or rollback without separate explicit authority and access terms.

## 12. Deliverables

The fixed workshare delivers:

1. frozen scope/input manifest;
2. source/evidence inventory and digests where held;
3. migration source profile;
4. migration reconciliation results;
5. Tyler interface/import acceptance evidence;
6. budget publication acceptance evidence;
7. SCO/GFOA publication requirement-to-evidence results;
8. CIP publication acceptance evidence;
9. WCAG 2.2 AA implementation-deliverable evidence matrix;
10. SAML/role/access evidence matrix;
11. UAT/regression results;
12. exception/HOLD ledger;
13. cutover rehearsal/readiness matrix;
14. retest/closure evidence for fixed defects where supplied;
15. final reviewer handoff separating proven facts, owner assertions and unresolved items.

## 13. Required inputs

The 20-business-day delivery target begins only after the designated prime/customer owner confirms a complete approved input set:

- controlling RFP/addenda/County clarifications;
- prime-approved responsibility matrix;
- approved legacy source exports;
- target evidence/import/export family;
- data dictionary and mapping rules;
- Tyler interface/file/API contract or owner-approved expected behavior;
- position/workforce interface evidence contract where admitted;
- publication templates and owner-approved SCO/GFOA requirement mapping;
- accessibility/VPAT/ACR/audit evidence supplied by the prime where applicable;
- SAML/role configuration evidence contract;
- approved test/replay fixtures or owner-run results;
- UAT requirements;
- known issue/deviation list;
- severity/disposition vocabulary;
- cutover/rollback plan owned by the prime/platform;
- data handling/redaction/environment constraints;
- named reviewers and decision owner.

Missing owner-controlled inputs produce explicit HOLDs and may pause the delivery clock rather than forcing invented evidence.

## 14. Default environment / authority boundary

Default posture:

- no production credentials;
- no standing privileged access;
- no production mutation/deployment;
- no County portal submission;
- no proposal signature;
- no ledger/position mutation;
- no buyer representation;
- no certification issuance;
- no payment movement;
- no secrets in durable artifacts;
- redacted/opaque identifiers preferred;
- owner-approved exports, fixtures, logs and read-only evidence preferred.

## 15. Responsibility split

### Qualified prime / OpenGov retains

- decision whether to pursue RFP 2907;
- evidence of Declaration of Interest, if any;
- official RFP/addenda interpretation;
- bidder eligibility/corporate representations;
- product/platform ownership, configuration and licensing;
- Tyler/provider commercial relationships;
- customer references/past performance;
- VPAT/ACR and security/compliance representations;
- implementation staffing/project management;
- onsite support commitments;
- training/support/SLA/account-management commitments;
- customer pricing and contract terms;
- County forms, exceptions, signatures and proposal submission;
- production access/deployment/go-live;
- invoicing, receivable, payment and revenue authority.

### TJLabs owns inside the frozen slice

- evidence inventory/traceability structure;
- deterministic migration reconciliation;
- admitted Tyler acceptance harness/evidence analysis;
- publication requirement-to-evidence acceptance;
- implementation-deliverable accessibility evidence matrix;
- SAML/role evidence mapping;
- UAT/regression evidence analysis;
- exception/HOLD ledger;
- cutover/readiness evidence;
- final technical reviewer handoff.

## 16. Explicit exclusions

The USD 48,000 hypothesis excludes unless separately contracted:

- platform license/subscription;
- core product development;
- whole RFP authorship/submission;
- legal advice;
- formal accessibility certification/VPAT/ACR issuance;
- formal security/privacy certification;
- production Tyler/County mutation;
- County financial/position posting;
- production identity administration;
- onsite deployment/support;
- broad end-user training;
- 24x7 support/managed services;
- interfaces outside the frozen set;
- additional fiscal years/datasets outside frozen scope;
- post-go-live operations;
- travel.

## 17. Acceptance criteria

TJLabs delivery is complete when:

1. scope and evidence generations are frozen;
2. every material retained artifact has a stable evidence ref and digest where TJLabs has byte custody;
3. every admitted migration rule has a terminal evidence state or explicit HOLD;
4. every admitted Tyler scenario has an evidence-backed result or explicit HOLD;
5. budget/SCO/CIP publication checks link requirement to generation-specific evidence;
6. accessibility conclusions remain bounded to supplied/tested evidence and do not overclaim certification;
7. SAML/role conclusions remain bounded to supplied/tested evidence;
8. every non-PASS result remains represented in the exception ledger;
9. cutover/readiness evidence exposes residual blockers;
10. final reviewer pack separates retained/provider evidence, owner assertions, public first-party evidence and unresolved items;
11. all external/commercial/production/payment/revenue authority remains false absent separate evidence.

Delivery-complete is an evidence-product state, not County acceptance, prime acceptance, bid submission, production go-live, invoice acceptance, payment, booked revenue or recognized revenue.

## 18. Schedule

Target: 20 business days after complete approved inputs.

Typical sequence:

- days 1–3: scope/input verification, source profiling, traceability skeleton;
- days 4–8: migration and Tyler interface reconciliation;
- days 7–11: budget/SCO/CIP publication acceptance;
- days 9–13: accessibility + SAML/role evidence;
- days 12–15: UAT/regression and first exception closure;
- days 16–18: owner-approved retests + cutover rehearsal;
- days 19–20: reviewer pack, evidence-link correction, handoff.

Changed data generations, interface contracts, publication requirements, additional systems/data, new onsite/production duties, missing owner decisions, or material new requirements are change-control/HOLD events rather than silent fixed-fee expansion.

## 19. Commercial truth

Current state is exactly:

- `proposed_price_usd = 48000`;
- `delivery_target_business_days = 20`;
- `commercial_state = PROPOSED_NOT_ACCEPTED`;
- `counterparty_interest = UNKNOWN`;
- `prime_pursuit = UNKNOWN`;
- `declaration_of_interest_filed = UNKNOWN`;
- `contract_exists = false`;
- `work_authorized = false`;
- `invoice_exists = false`;
- `receivable_exists = false`;
- `payment_received = false`;
- `booked_revenue = false`;
- `recognized_revenue = false`.

Repository publication changes none of those facts.

## 20. External-contact gate

No OpenGov email/form/message may be sent merely because this packet exists. A send requires:

1. current all-access Slack census for Marin/RFP 2907/OpenGov collision and DNR state;
2. current Gmail census for exact organization/domain/route and purpose;
3. exact current Muse single-writer SELECT/CLEAR for one recipient, route and purpose;
4. immediate second Slack/Gmail census after Muse clearance and immediately before send;
5. one plain-text message to the selected route only;
6. provider send receipt;
7. hard DNR for the exact organization × route × purpose pending a genuine human/provider event.

Any conflict or uncertainty stops the send.