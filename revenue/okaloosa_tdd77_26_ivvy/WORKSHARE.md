# Okaloosa TDD 77-26 — iVvy migration & integration acceptance workshare

**State:** `PROPOSED_NOT_ACCEPTED`  
**Opportunity:** Okaloosa County Tourism Department — RFP TDD 77-26  
**Candidate prime/platform counterparty:** iVvy  
**Commercial hypothesis:** USD 35,000 fixed fee  
**Delivery target:** 15 business days after complete approved inputs  
**Owner:** Token Junkie Labs (TJLabs)  
**Publication state:** NOT SENT — external publication requires a separate current Muse single-writer decision and last-inch Slack/Gmail/provider recensus.

## 1. Purpose

This packet defines one bounded paid migration/integration acceptance workshare that can sit behind a qualified venue-management SaaS prime responding to Okaloosa County Tourism Department RFP TDD 77-26.

Current public discovery material describes an enterprise venue/event-management procurement spanning multiple venues, sales/booking/contract/event operations, financial tracking/reporting, integrations with Workday, DocuSign and Bluepay, and migration of ten years of historical event data from Ungerboeck/Momentus. The controlling buyer packet has not been retained in this carrier. Those discovery facts therefore identify a plausible work seam; they do not establish complete buyer requirements, bidder eligibility, submission authority, or compliance.

iVvy's current public materials describe cloud venue/event-management software, 55+ integrations, accounting/payment/CRM/POS connectivity, a documented API, and migration support from Momentus. That evidence supports asking iVvy whether it is pursuing the opportunity and whether a specialist acceptance workshare is useful. It does **not** establish that iVvy is bidding, qualified, willing to partner, compliant with every County requirement, or authorized to make any County representation.

The proposed TJLabs role is deliberately downstream of the prime's platform and customer authority: independently traceable migration reconciliation, integration-contract acceptance evidence, cutover rehearsal/readiness evidence, and an exception/HOLD ledger. TJLabs does not replace the platform vendor, submit the County bid, certify the vendor, or make production/release decisions.

## 2. Frozen work package

The fixed-fee package covers exactly one owner-approved Okaloosa implementation slice identified at kickoff by a frozen scope key containing:

- one prime/customer implementation identifier;
- one approved legacy export family from the incumbent environment;
- one approved target import/export or read-only evidence family;
- one closed historical migration population;
- one closed Workday integration contract;
- one closed DocuSign integration contract;
- one closed Bluepay/payment integration contract or owner-approved replacement if the controlling buyer packet differs;
- one closed UAT/acceptance requirement set;
- one cutover rehearsal generation;
- one acceptance decision owner designated by the prime/customer.

No additional venue, dataset, interface, payment processor, financial process, customer workflow, integration, training program, or production mutation is silently included.

## 3. Migration source profiling

Before migration reconciliation begins, TJLabs produces a source-profile manifest for the approved historical export family.

The manifest records, where available and meaningful:

1. artifact/evidence identifiers;
2. byte digests for material under TJLabs custody;
3. export generation/timestamp supplied by the owner;
4. table/object/file populations;
5. stable source identifiers and candidate natural/business keys;
6. required-field completeness distributions;
7. relationship/cardinality observations;
8. duplicate/orphan/unmapped populations;
9. attachment/document inventory classes without copying unnecessary sensitive content;
10. known legacy encodings/time zones/currency conventions;
11. evidence gaps that prevent a stronger conclusion.

A filename, screenshot, operator statement, row count, or self-described export label never proves completeness by itself. Missing or contradictory custody becomes `HOLD_SOURCE_EVIDENCE`.

## 4. Ten-year migration reconciliation

For the owner-approved historical population, TJLabs creates a deterministic requirements-to-evidence matrix. Each admitted rule receives one of:

- `PASS_WITH_EVIDENCE`;
- `FAIL_WITH_EVIDENCE`;
- `HOLD_MISSING_OWNER_EVIDENCE`;
- `NOT_TESTABLE_FROM_SUPPLIED_EVIDENCE`.

The default reconciliation families are:

### 4.1 Population and identity

- expected object/row population by admitted class;
- stable identifier preservation or explicit owner-approved remapping;
- duplicate and collision behavior;
- orphan detection;
- cross-object relationship preservation;
- event-to-account/contact/venue/space relationship checks where represented in the supplied model.

### 4.2 Required business fields

- required-field completeness;
- enum/status normalization evidence;
- date/time/time-zone transformation rules;
- numeric/currency precision and rounding rules;
- archival/closed-event preservation rules;
- document/attachment reference preservation where admitted.

### 4.3 Historical sampling

Sampling is permitted only from an owner-approved, predeclared rule. The pack records the selection method, sampled population, evidence references, and observed result. A successful sample never silently upgrades an untested population to full equivalence.

### 4.4 Exception ledger

Every mismatch has a stable id, source/target evidence refs, rule id, observed result, expected result, owner-approved severity/disposition, next owner/action, retest requirement, and status.

No exception disappears because a deadline arrives.

## 5. Integration acceptance harnesses

The workshare supplies acceptance harnesses and reviewer-verifiable evidence for the three buyer-named external systems in the current discovery record. Final interface semantics are controlled by the prime and official buyer packet.

### 5.1 Workday seam

For the approved Workday contract, test/evidence families may include:

- canonical account/cost-center/reference mappings;
- invoice or financial-export mapping as applicable;
- cents/currency/tax precision where applicable;
- status transition mapping;
- duplicate/retry/idempotency behavior;
- rejected/invalid payload behavior;
- correlation identity and traceability;
- reconciliation from source event/booking evidence to admitted financial output;
- owner-approved negative cases;
- explicit HOLD where production-only behavior cannot be safely exercised.

TJLabs does not post to production Workday, alter financial records, approve accounting treatment, or assert financial close correctness.

### 5.2 DocuSign seam

For the approved DocuSign contract, acceptance evidence may include:

- document/template identity binding;
- signer/role mapping from owner-approved fixtures;
- envelope/request correlation ids;
- expected state-transition evidence;
- duplicate/retry behavior;
- cancellation/void/error evidence where owner-approved;
- source contract/event linkage;
- returned signed-document/evidence reference linkage;
- explicit separation between technical delivery evidence and legal/contract acceptance.

TJLabs does not sign County/vendor documents, select legal signatories, determine legal sufficiency, or represent an envelope as contractually binding.

### 5.3 Bluepay/payment seam

For the approved payment contract, acceptance evidence may include:

- canonical payment/reference identity;
- amount/currency minor-unit handling;
- authorization/capture/refund/status mapping where in scope;
- duplicate/retry/idempotency behavior;
- processor error/rejection mapping;
- reconciliation to the admitted booking/event/invoice evidence;
- no plaintext secret/payment-card custody in durable test artifacts;
- owner-approved sandbox/non-production execution or owner-supplied provider evidence.

TJLabs does not create processor accounts, handle cardholder data beyond separately approved compliant boundaries, move funds, settle transactions, or claim PCI compliance for the prime.

## 6. Cutover rehearsal and rollback/readiness evidence

The fixed package includes one bounded cutover rehearsal on owner-approved non-production or otherwise safe evidence.

The rehearsal pack records:

1. frozen source generation;
2. frozen target/configuration generation supplied by owner;
3. transformation/import version identity;
4. migration start/end checkpoints;
5. preflight gates;
6. reconciliation outcomes;
7. interface smoke/acceptance outcomes;
8. unresolved exceptions;
9. go/no-go owner questions;
10. rollback/restore prerequisites supplied by the platform/prime;
11. final owner decision evidence.

TJLabs may produce a `READY_FOR_OWNER_REVIEW` evidence state. It may not independently emit `PRODUCTION_GO`, deploy production, or waive unresolved owner-controlled blockers.

## 7. Audit/security acceptance evidence

Within supplied evidence and the prime's approved responsibility boundary, TJLabs can assemble an acceptance matrix for technical controls such as:

- role/access evidence;
- audit-event/logging evidence;
- transport/security configuration evidence supplied by the owner;
- retention/export behavior;
- administrator/action traceability;
- integration credential handling boundaries;
- data-at-rest/in-transit evidence supplied by the platform;
- processor/payment-boundary evidence supplied by the prime/provider;
- disaster-recovery/backup evidence supplied by the platform;
- unresolved certification/control evidence as explicit HOLDs.

TJLabs does **not** certify SOC 2, PCI DSS, legal compliance, cybersecurity adequacy, privacy compliance, or County policy conformance. Certification and attestation remain with the qualified prime and relevant assessor/provider.

## 8. Deliverables

The fixed-fee work package delivers:

1. frozen scope/input manifest;
2. source-profile/evidence inventory;
3. migration reconciliation specification;
4. migration reconciliation results;
5. Workday acceptance harness/results;
6. DocuSign acceptance harness/results;
7. Bluepay/payment acceptance harness/results;
8. exception/HOLD ledger;
9. cutover rehearsal/readiness record;
10. technical audit/security acceptance matrix;
11. requirements-to-evidence traceability matrix;
12. retest/closure evidence for fixed defects where supplied;
13. final owner-review handoff separating proven facts, owner assertions and unresolved items.

The final pack is evidence-first: every material conclusion links to retained or owner-supplied evidence strong enough for that conclusion.

## 9. Required inputs

The 15-business-day delivery target starts only after the designated prime/customer owner confirms a complete approved input set, including:

- controlling RFP/addenda applicable to the workshare;
- prime-approved responsibility matrix;
- approved historical export family and data-handling instructions;
- target import/export/read-only evidence family;
- mapping/transformation rules;
- Workday contract/specification or owner-approved expected behavior;
- DocuSign contract/specification or owner-approved expected behavior;
- Bluepay/payment contract/specification or owner-approved expected behavior;
- approved replay fixtures or owner-run evidence;
- UAT/acceptance requirements;
- known issue/deviation list;
- severity/disposition vocabulary;
- cutover/rollback plan owned by the prime/platform;
- named reviewers/decision owners.

Missing required inputs produce explicit HOLDs and may pause the delivery clock rather than forcing invented evidence.

## 10. Data and environment boundary

Default posture:

- no production credentials;
- no standing privileged access;
- no production mutation;
- no production deployment;
- no direct financial-system writes;
- no payment movement;
- no live contract signature;
- no buyer portal submission;
- no County representation;
- opaque identifiers/redacted evidence preferred where personal or payment data is unnecessary;
- secrets excluded from durable artifacts;
- owner-approved exports, fixtures, logs and read-only evidence preferred.

Any material requiring regulated, confidential, cardholder, contractual or personally identifying data remains blocked until the prime/customer provides the governing approved access/transfer terms.

## 11. Responsibility split

### Qualified prime / iVvy retains

- decision to pursue the County opportunity;
- bidder eligibility and corporate representations;
- official RFP/addenda interpretation;
- SaaS ownership/operation and product roadmap;
- platform architecture/configuration;
- licensing/subscriptions;
- County references and past performance;
- security certifications and compliance representations;
- PCI/SOC/legal/privacy representations;
- Workday/DocuSign/Bluepay commercial/provider relationships;
- customer support/SLA/maintenance commitments;
- implementation governance and production access;
- end-customer pricing;
- County forms, bonds/insurance if required;
- signatures and proposal submission;
- final cutover/release/go-live authority;
- payment/invoice/revenue authority.

### TJLabs owns inside the frozen slice

- evidence inventory/traceability structure;
- approved source-profile analysis;
- deterministic migration reconciliation rules and results;
- integration acceptance harness design for admitted contracts;
- evidence analysis for owner-approved replays;
- exception/HOLD ledger;
- cutover rehearsal evidence pack;
- requirements-to-evidence mapping;
- technical owner-review handoff.

## 12. Explicit exclusions

The USD 35,000 fixed hypothesis excludes unless separately contracted:

- platform licensing;
- platform product development;
- County proposal writing/submission ownership;
- legal review;
- security certification;
- PCI assessment;
- formal SOC examination;
- production deployment;
- production data repair/mutation;
- payment processing/settlement;
- Workday tenant administration;
- DocuSign account/legal-signatory administration;
- Bluepay merchant administration;
- broad end-user training;
- 24x7 operations/support;
- new interfaces beyond the frozen set;
- new datasets/venues outside the frozen scope;
- travel/onsite work unless explicitly added;
- hardware/network installation;
- post-go-live managed services.

## 13. Acceptance criteria

TJLabs delivery is complete when:

1. the workshare scope and input generation are frozen;
2. every material retained artifact has an evidence reference and digest where TJLabs has byte custody;
3. every admitted migration rule has an evidence-backed terminal result or explicit owner-controlled HOLD;
4. every admitted integration scenario has evidence-backed result or explicit owner-controlled HOLD;
5. every exception remains visible until closed with evidence;
6. cutover rehearsal inputs/results/remaining blockers are traceable;
7. audit/security evidence is separated from certifications/claims TJLabs cannot make;
8. the final reviewer pack can be followed from requirement to evidence to result;
9. unresolved owner-controlled items remain explicit rather than being converted to PASS;
10. all external/commercial/payment/revenue authority remains false absent separate evidence.

Delivery-complete is an evidence-product state, not County acceptance, prime acceptance, production go-live, invoice acceptance, payment, booked revenue, or recognized revenue.

## 14. Schedule

Target: 15 business days after complete approved inputs.

Typical sequence:

- days 1–2: scope/input verification, source profiling, traceability skeleton;
- days 3–6: migration reconciliation + exception generation;
- days 5–9: Workday/DocuSign/payment acceptance harness execution/evidence review;
- days 10–11: approved retests and exception triage;
- days 12–13: cutover rehearsal/readiness evidence;
- days 14–15: reviewer pack, evidence-link correction, handoff.

Owner-caused access delays, changed source generations, changed interface contracts, new requirements, new venues/datasets, or missing owner decisions are change-control/HOLD events, not silent fixed-fee expansion.

## 15. Commercial truth

Current state is exactly:

- `proposed_price_usd = 35000`;
- `delivery_target_business_days = 15`;
- `commercial_state = PROPOSED_NOT_ACCEPTED`;
- `counterparty_interest = UNKNOWN`;
- `prime_pursuit = UNKNOWN`;
- `contract_exists = false`;
- `work_authorized = false`;
- `invoice_exists = false`;
- `receivable_exists = false`;
- `payment_received = false`;
- `booked_revenue = false`;
- `recognized_revenue = false`.

Repository publication changes none of those facts.

## 16. External-contact gate

No iVvy email may be sent merely because this packet exists. A send requires all of:

1. exact current Muse single-writer selection for recipient + purpose;
2. immediate Slack/provider recensus with no conflicting writer/send/DNR/human reply;
3. immediate Gmail recensus with no conflicting send/reply/bounce;
4. one plain-text message to the selected route only;
5. provider send receipt;
6. hard DNR for the exact org × route × purpose pending a genuine human/provider event.

Any conflicting evidence stops the send.