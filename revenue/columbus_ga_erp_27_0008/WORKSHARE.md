# Columbus GA ERP 27-0008 — specialist implementation-evidence workshare

Status: **PROPOSED_NOT_ACCEPTED**  
Reference price: **USD 28,000 fixed**  
Reference delivery window: **15 business days after agreed input readiness**  
Operation: `COLUMBUS-GA-ERP-27-0008-TYLER-WORKSHARE-SWARMZ-20260917`

## Purpose

This packet defines a bounded specialist subcontract that a qualified ERP prime may use if it is pursuing Columbus Consolidated Government RFP 27-0008. It is not an ERP-software proposal and does not represent that Tyler Technologies, or any other target, is currently bidding.

The buyer's original RFP permits a prime to identify subcontractors and makes the prime responsible for their compliance. Addendum No. 1 extends the proposal deadline to October 14, 2026 at 5:00 PM. The qualified prime remains the sole interface to Columbus for solicitation correspondence and submission.

## Workshare

### 1. Legacy-data conversion reconciliation

**Inputs from prime**
- one frozen, buyer-authorized source-generation manifest;
- source/target entity and field mappings for the agreed modules;
- transformation rules and canonical identifiers;
- target-load evidence or synthetic/de-identified extracts suitable for the agreed acceptance exercise.

**Outputs**
- source/target inventory and mapping matrix;
- count/hash/semantic reconciliation ledger;
- duplicate, conflict, missing-target, unexpected-target and transformation-exception register;
- deterministic evidence receipt per agreed migration slice;
- unresolved-HOLD register with owner and required next evidence.

**Acceptance**
- every admitted source row maps to exactly one terminal reconciliation disposition;
- aggregate counts reconcile or a named exception explains the delta;
- no duplicate/conflicting canonical identity is silently accepted;
- same evidence generation reproduces the same receipt.

### 2. Integration contract acceptance

**Inputs from prime**
- bounded interface inventory;
- owner, source, target and transport contract for each admitted interface;
- retry/idempotency/duplicate-effect policy;
- prime-owned success/failure evidence.

**Outputs**
- interface acceptance matrix;
- retry/replay/duplicate-effect evidence ledger;
- dependency and rollback map;
- unresolved assumption/HOLD list.

**Acceptance**
- every admitted interface has an owner and explicit source/target contract;
- retries cannot produce an unrecorded duplicate effect in the agreed fixture/evidence set;
- failure and rollback expectations are explicit rather than inferred;
- unsupported interfaces remain HOLD.

### 3. Requirement → configuration → test → UAT evidence

**Inputs from prime**
- prime-selected RFP requirements within this workshare;
- prime-owned configuration/design references;
- test/UAT cases and observed artifacts;
- explicit human acceptance state where it exists.

**Outputs**
- requirement-to-evidence trace matrix;
- gap and exception ledger;
- retest lineage;
- acceptance-state register that distinguishes machine evidence from human authority.

**Acceptance**
- every admitted requirement has an owner and an evidence pointer or explicit gap;
- no machine-generated receipt can mint buyer acceptance;
- changed evidence produces a new receipt generation rather than silently mutating history.

### 4. Cutover / rollback / replay assurance

**Inputs from prime**
- cutover plan and freeze boundaries;
- migration/interface dependencies;
- rollback conditions;
- prime-owned go/no-go criteria.

**Outputs**
- cutover readiness evidence matrix;
- migration/interface receipt set;
- rollback/replay checklist;
- exception/HOLD ledger and post-cutover handoff.

**Acceptance**
- every critical dependency is evidence-backed or explicitly HOLD;
- rollback criteria are testable and owner-bound;
- replay produces deterministic evidence for the same admitted inputs;
- TJLabs evidence does not make the prime's or buyer's go-live decision.

### 5. Proposal / implementation evidence support

TJLabs may normalize evidence the prime already possesses into concise technical exhibits for migration, interfaces, testing, cutover and acceptance. TJLabs will not manufacture or certify product functionality, public-sector references, staff resumes, financials, insurance, security/compliance claims, corporate forms, legal exceptions, pricing to Columbus, SLAs, signatures or bidder status.

## Delivery sequence

- **Days 1–2:** evidence/source inventory, exact scope freeze, gap ledger.
- **Days 3–7:** migration and interface acceptance matrices + deterministic receipt generation.
- **Days 8–11:** requirement/test/UAT traceability and hostile/exception passes.
- **Days 12–13:** cutover/rollback/replay evidence pack.
- **Days 14–15:** prime review, gap closeout, final evidence binder and handoff.

The clock starts only after the agreed input-readiness gate passes. Missing or contradictory evidence creates HOLD rather than a fabricated PASS.

## Commercial boundary

Reference price is a commercial hypothesis only. It becomes a receivable only after an authorized counterparty accepts a work order or other valid agreement. No free buyer-specific implementation is promised by this packet.

The prime retains ERP product/configuration decisions, Columbus/OpenBids communication, vendor registration and forms, references, staffing, security/compliance, insurance, proposal pricing, legal exceptions, submission, signatures, production/customer-data authority, go-live decision, award/contract/payment and revenue authority.

TJLabs does not contact Columbus under this workshare unless the prime separately authorizes a solicitation-compliant route and the governing procurement rules permit it.
