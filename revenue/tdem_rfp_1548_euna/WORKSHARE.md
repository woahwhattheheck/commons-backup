# TDEM-RFP-1548 — Euna Grants migration & integration acceptance workshare

**State:** `PROPOSED_NOT_ACCEPTED`  
**Opportunity:** Texas Division of Emergency Management — TDEM-RFP-1548  
**Candidate prime/platform counterparty:** Euna Solutions / Euna Grants powered by AmpliFund  
**Commercial hypothesis:** USD 45,000 fixed fee  
**Delivery target:** 20 business days after complete approved inputs  
**Owner:** Token Junkie Labs (TJLabs)  
**Publication state:** NOT SENT — external publication requires a current Muse single-writer decision plus immediate Slack/Gmail/provider recensus.

## 1. Purpose

This packet defines one bounded paid migration/integration acceptance workshare that can sit behind a qualified grants-management SaaS prime pursuing Texas Division of Emergency Management solicitation TDEM-RFP-1548.

Current public procurement discovery describes a modern cloud grants-management system supporting federal, state, disaster and non-disaster programs, reimbursement-based financial assistance, disaster cost recovery, mission assignments, lifecycle workflows, financial management/reporting, migration, integrations with FEMA/state systems, training and ongoing support. The controlling RFP, addenda, mandatory-conference record, pricing forms, VetHUB/subcontracting requirements and buyer terms are not retained as authoritative bytes in this carrier. A qualified prime must bind those materials before a discovered requirement is treated as controlling.

Current Euna public materials describe purpose-built public-sector grants management, full lifecycle grantmaker/grantee workflows, statewide deployments, ERP integration, Microsoft Azure public-sector hosting, audit/security operations, and AmpliFund's state/local/tribal grant-management lineage. Those facts create a strong adjacency for a partner inquiry. They do **not** prove Euna is bidding, qualified under the current packet, willing to partner, or compliant with every TDEM term.

TJLabs proposes an evidence-first acceptance slice: source/migration reconciliation, FEMA/state/ERP integration-contract evidence, reimbursement/disaster-cost financial reconciliation, award/subrecipient lifecycle traceability, an exception/HOLD ledger, cutover rehearsal/readiness evidence, and a reviewer-verifiable security/audit evidence matrix. TJLabs does not replace the platform vendor, submit the bid, make procurement certifications, approve grants, mutate production financial records, or decide go-live.

## 2. Frozen work package

The fixed-fee package covers exactly one owner-approved implementation slice identified at kickoff by a frozen scope key containing:

- one prime/customer implementation id;
- one approved legacy/source export family;
- one approved target import/export or read-only evidence family;
- one closed grant-program family or explicitly enumerated set;
- one closed award/subaward/subrecipient population;
- one closed reimbursement/disaster-cost evidence population;
- one closed FEMA integration/evidence contract where applicable;
- one closed state-system/ERP integration/evidence contract;
- one closed reporting/audit acceptance requirement set;
- one cutover rehearsal generation;
- one owner-designated acceptance decision authority.

No additional agency, program, integration, dataset, financial workflow, training program, production environment, reporting family or regulatory interpretation is silently included.

## 3. Legacy/source evidence profile

Before migration reconciliation, TJLabs produces a source-profile manifest from owner-approved exports/evidence.

The profile records, where meaningful:

1. evidence/artifact ids;
2. byte digests for artifacts in TJLabs custody;
3. owner-supplied export generation and system identity;
4. program, award, subaward and subrecipient populations;
5. stable identifiers and candidate natural/business keys;
6. award hierarchy/relationship observations;
7. reimbursement/claim/payment-reference populations;
8. required-field completeness distributions;
9. duplicate/orphan/unmapped populations;
10. document/attachment inventory classes without copying unnecessary sensitive content;
11. status/workflow vocabularies;
12. date/time/fiscal-period conventions;
13. currency/amount precision conventions;
14. evidence gaps that prevent stronger conclusions.

Screenshots, filenames, operator statements or aggregate counts alone never prove completeness when a rule requires stronger evidence. Missing or contradictory source custody becomes an explicit HOLD.

## 4. Migration reconciliation

For the frozen migration population, every admitted rule receives one evidence-backed result:

- `PASS_WITH_EVIDENCE`;
- `FAIL_WITH_EVIDENCE`;
- `HOLD_MISSING_OWNER_EVIDENCE`;
- `NOT_TESTABLE_FROM_SUPPLIED_EVIDENCE`.

### 4.1 Identity and hierarchy

Reconciliation may cover:

- grant/program identity;
- funding-source identity;
- award/subaward identity;
- subrecipient/grantee identity;
- parent/child award relationships;
- amendment/version identity;
- application-to-award traceability;
- award-to-reimbursement traceability;
- document/evidence references;
- explicitly approved identifier remapping.

### 4.2 Lifecycle state

Where represented in the owner-approved data model:

- application/draft/submitted/review states;
- award/execution states;
- monitoring/compliance states;
- reimbursement/request states;
- amendment states;
- reporting states;
- closeout states;
- inactive/archival states.

TJLabs records the approved source-to-target mapping rather than inventing semantic equivalence between status labels.

### 4.3 Financial evidence

Where in scope and supported by supplied evidence:

- authorized amount;
- obligated/awarded amount;
- amended amount;
- requested reimbursement;
- approved reimbursement;
- paid/disbursed references supplied by the owner/provider;
- match/share categories;
- cost categories;
- project/program/funding-source allocations;
- fiscal period;
- amount precision and rounding;
- negative/credit/adjustment treatment;
- cumulative-vs-incremental semantics.

TJLabs reconciles evidence; it does not approve accounting treatment, authorize payment, certify allowability, or mutate financial systems.

### 4.4 Sampling

Sampling is permitted only under a frozen owner-approved rule. The pack records the selection method, population, sampled rows/objects, evidence references and observed outcomes. A passing sample never silently proves full-population equivalence.

## 5. FEMA / federal-system integration acceptance

For each owner-approved FEMA/federal integration seam, TJLabs builds an evidence harness around the supplied contract or expected behavior.

Possible acceptance families include:

- canonical program/award identifiers;
- project/application identifiers;
- subrecipient identifiers;
- financial amount/status mappings;
- event/message correlation ids;
- import/export generation identity;
- duplicate/retry/idempotency behavior;
- rejected/invalid record behavior;
- partial-batch behavior;
- reconciliation between source grant evidence and exported/imported representation;
- explicit HOLD for behaviors that cannot be exercised safely from supplied evidence.

No destructive production API call, federal credential use, federal portal submission or federal-system mutation is authorized by this workshare.

## 6. State-system / ERP integration acceptance

For the closed state/ERP integration set, acceptance evidence may cover:

- chart/account/cost-center/fund/program mapping;
- vendor/subrecipient identity mapping;
- obligation/encumbrance references where applicable;
- reimbursement/payment-request identity;
- invoice/payment/status synchronization where applicable;
- amount/currency/fiscal-period semantics;
- transaction/reference correlation;
- duplicate/retry/idempotency behavior;
- negative/reversal/adjustment behavior;
- failed/rejected message handling;
- source-to-target reconciliation;
- owner-approved negative cases.

TJLabs does not post production journal entries, authorize disbursements, approve accounting treatment or claim the state's books reconcile beyond the admitted evidence contract.

## 7. Reimbursement and disaster-cost reconciliation

For the frozen reimbursement/disaster-cost slice, TJLabs produces a traceability matrix linking:

1. grant/program/funding source;
2. award/subaward;
3. applicant/subrecipient;
4. project/mission assignment where applicable;
5. cost category/source document reference;
6. reimbursement/request identity;
7. requested amount;
8. approved amount supplied by owner evidence;
9. paid/disbursed reference supplied by owner/provider evidence where available;
10. adjustment/denial/hold reason where available;
11. supporting documentation references;
12. interface/accounting references where in scope.

Every material gap becomes an exception/HOLD. A missing payment/provider reference is not inferred from an approved request. An owner assertion is labeled as owner-supplied evidence class, not silently upgraded to provider truth.

## 8. Award / subrecipient lifecycle traceability

For the admitted program population, TJLabs can assemble reviewer-verifiable evidence that the configured lifecycle preserves:

- applicant/subrecipient identity;
- application and review lineage;
- award and amendment lineage;
- required deliverable/report references;
- monitoring/exception references;
- reimbursement lineage;
- closeout evidence references;
- audit/activity history evidence supplied by the platform;
- unresolved HOLDs.

TJLabs does not decide program eligibility, award funding, risk acceptance, compliance disposition, monitoring findings or grant closeout authority.

## 9. Exception / HOLD ledger

Every unresolved item has at minimum:

- stable exception id;
- rule/requirement/interface/migration reference;
- evidence references;
- observed result;
- expected result;
- evidence class;
- owner-approved severity/disposition;
- next owner/action;
- closure-evidence requirement;
- state: `OPEN`, `HOLD`, `RETEST_READY` or `CLOSED_WITH_EVIDENCE`.

No exception disappears because the proposal, implementation or grant deadline arrives.

## 10. Cutover rehearsal and readiness

The fixed package includes one bounded cutover rehearsal using owner-approved non-production or otherwise safe evidence.

The rehearsal record includes:

1. frozen source generation;
2. frozen target/configuration generation supplied by owner;
3. transformation/import version identity;
4. approved mapping generation;
5. preflight gates;
6. migration/reconciliation results;
7. integration acceptance results;
8. financial/reimbursement reconciliation results;
9. unresolved exceptions;
10. rollback/restore prerequisites supplied by the prime/platform;
11. owner questions;
12. final owner decision evidence.

TJLabs may report `READY_FOR_OWNER_REVIEW` or `HOLD`. It may not independently emit `PRODUCTION_GO`, deploy production or waive blockers controlled by the prime/TDEM/provider.

## 11. Audit and security evidence matrix

Using prime/platform-supplied evidence, TJLabs can assemble a traceable matrix for technical controls such as:

- identity/access and role evidence;
- administrative activity logging;
- object/activity audit history;
- encryption/transport evidence supplied by provider;
- environment separation evidence;
- backup/restore and disaster-recovery evidence;
- retention/export evidence;
- data-region/hosting evidence;
- release/change-management evidence;
- vulnerability/testing evidence supplied by provider;
- integration credential boundaries;
- residual control/certification HOLDs.

TJLabs does **not** self-certify SOC, PCI, FedRAMP, StateRAMP, CJIS, HIPAA, legal/privacy requirements or TDEM security compliance. Formal attestations and buyer acceptance remain with the qualified prime, assessor/provider and buyer.

## 12. Deliverables

The fixed package delivers:

1. frozen scope/input manifest;
2. source/evidence inventory;
3. legacy/source profile;
4. migration acceptance matrix;
5. migration reconciliation results;
6. FEMA/federal integration acceptance results;
7. state/ERP integration acceptance results;
8. reimbursement/disaster-cost reconciliation results;
9. award/subrecipient lifecycle traceability results;
10. exception/HOLD ledger;
11. cutover rehearsal/readiness record;
12. technical audit/security evidence matrix;
13. retest/closure evidence for fixed exceptions where supplied;
14. final reviewer handoff separating proven facts, owner assertions and unresolved items.

## 13. Required inputs

The 20-business-day target starts only after the prime/customer owner confirms a complete approved input set, including:

- controlling RFP/addenda and applicable buyer clarifications;
- prime-approved responsibility matrix;
- approved legacy/source exports;
- approved target evidence/import/export family;
- data dictionary/mapping/transformation rules;
- admitted program/award/subrecipient population;
- reimbursement/disaster-cost rules relevant to the slice;
- FEMA/federal integration contract or owner-approved expected behavior;
- state/ERP integration contract or owner-approved expected behavior;
- approved replay fixtures or owner-run results;
- UAT/acceptance requirements;
- known issue/deviation references;
- severity/disposition vocabulary;
- cutover/rollback plan owned by the platform/prime;
- data handling/redaction/environment constraints;
- named reviewers and final decision owners.

Missing owner-controlled inputs produce explicit HOLDs and may pause the delivery clock instead of forcing invented evidence.

## 14. Data and environment boundary

Default posture:

- no production credentials;
- no standing privileged access;
- no production mutation;
- no production deployment;
- no grant award/eligibility decision;
- no federal/state portal submission;
- no financial-system write;
- no payment/disbursement authorization;
- no confidential or personally identifying data unless required and separately governed;
- opaque identifiers/redacted evidence preferred;
- no secrets in durable artifacts;
- owner-approved exports, fixtures, logs and read-only evidence preferred.

If regulated/confidential information is unavoidable, work on that material does not start until the prime/customer supplies the approved transfer/access/data-handling boundary.

## 15. Responsibility split

### Qualified prime / Euna retains

- decision whether to pursue TDEM-RFP-1548;
- buyer relationship and official solicitation interpretation;
- mandatory pre-bid/conference compliance;
- VetHUB/subcontracting plan and good-faith documentation;
- bidder eligibility and corporate representations;
- platform ownership, architecture, configuration and licensing;
- references/past performance;
- security certifications/compliance representations;
- federal/state integration commercial/provider relationships;
- migration implementation authority;
- customer support/SLA/maintenance/training commitments;
- proposal pricing and contract terms;
- production access/deployment/go-live;
- buyer forms/signatures/submission;
- invoicing, receivable, payment and revenue authority.

### TJLabs owns inside the frozen slice

- evidence inventory/traceability structure;
- source profile;
- deterministic migration reconciliation rules/results;
- admitted integration acceptance harnesses/evidence analysis;
- reimbursement/disaster-cost evidence reconciliation;
- award/subrecipient lifecycle evidence mapping;
- exception/HOLD ledger;
- cutover rehearsal/readiness evidence;
- reviewer-verifiable audit/security evidence matrix;
- final evidence handoff.

## 16. Explicit exclusions

The USD 45,000 fixed hypothesis excludes unless separately contracted:

- platform licensing/subscriptions;
- core product development;
- full proposal writing/submission ownership;
- legal review;
- VetHUB certification or subcontract-plan authorship/attestation;
- formal security/certification audits;
- production deployment/mutation;
- production financial posting;
- grant eligibility/award decisions;
- payment/disbursement operations;
- federal/state portal administration;
- broad organizational change management;
- end-user training beyond reviewer handoff;
- 24x7 support/managed services;
- new interfaces beyond the frozen set;
- new program/data families outside frozen scope;
- onsite travel unless explicitly added;
- post-go-live operations.

## 17. Acceptance criteria

TJLabs delivery is complete when:

1. scope and input generations are frozen;
2. every material artifact has a stable evidence reference and digest where TJLabs has byte custody;
3. every admitted migration rule has evidence-backed terminal state or explicit owner-controlled HOLD;
4. every admitted federal/state/ERP interface scenario has evidence-backed result or explicit HOLD;
5. reimbursement/disaster-cost mappings are traceable at the agreed evidence depth;
6. award/subrecipient lifecycle conclusions link to evidence;
7. every exception remains visible until closed with evidence;
8. cutover rehearsal inputs/results/blockers are traceable;
9. technical security/audit evidence is separated from certifications TJLabs cannot make;
10. final reviewer pack separates proven facts, owner assertions and unresolved items;
11. all external/commercial/payment/revenue authority remains false absent separate evidence.

Delivery-complete is an evidence-product state. It is not TDEM acceptance, prime acceptance, contract execution, production go-live, invoice acceptance, payment, booked revenue or recognized revenue.

## 18. Schedule

Target: 20 business days after complete approved inputs.

Typical sequence:

- days 1–3: input verification, source profiling, scope freeze, traceability skeleton;
- days 4–8: migration reconciliation + first exception generation;
- days 7–12: FEMA/state/ERP acceptance evidence;
- days 9–13: reimbursement/disaster-cost and award/subrecipient traceability;
- days 14–16: owner-approved retests/exception triage;
- days 17–18: cutover rehearsal/readiness evidence;
- days 19–20: reviewer pack, evidence-link correction and handoff.

Owner-caused access delays, changed source generations, changed interface contracts, new programs/data families, new requirements, missing owner decisions or new production responsibilities are change-control/HOLD events, not silent fixed-fee expansion.

## 19. Commercial truth

Current state is exactly:

- `proposed_price_usd = 45000`;
- `delivery_target_business_days = 20`;
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

## 20. External-contact gate

No Euna email may be sent merely because this packet exists. A send requires:

1. exact current Muse single-writer selection for recipient + purpose;
2. immediate Slack/provider recensus showing no competing writer/send/DNR/human reply;
3. immediate Gmail recensus showing no conflicting send/reply/bounce;
4. one plain-text message to the selected route only;
5. provider send receipt;
6. hard DNR for the exact organization × route × purpose pending a genuine human/provider event.

Any conflict stops the send.