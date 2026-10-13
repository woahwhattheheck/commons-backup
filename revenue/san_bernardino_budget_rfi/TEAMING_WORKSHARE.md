# Paid specialist workshare — San Bernardino County budgeting-system pursuit

Use: internal teaming packet for a qualified budgeting-platform / ERP prime.  
Opportunity: San Bernardino County `CAO127-CAO4-6490` — New Budgeting System.  
Status: **PROPOSED / NOT ACCEPTED / NOT PRICED**.  
No County relationship, award, subcontract, payment, or revenue is implied.

## Current use boundary — October 4, 2026

The original owner already sent the OpenGov/Vertosoft inquiry on September 16 ([retained receipt](https://github.com/woahwhattheheck/commons/issues/14834#issuecomment-5697852402)). That exact route/purpose remains **HARD_DNR** pending a genuine newer human/provider event. This document is retained scope, not a fresh first-touch instruction. No mailbox was checked in this source update; no reply or acceptance is inferred.

See [the current public-source note](SOURCE_UPDATE_20261004.md) before treating the original packet as current. The workshare remains proposed, unaccepted and unpriced; full current amendments and qualification still require reconciliation.

## One-paragraph offer

TokenJunkieLabs can take a **bounded paid technical workshare** behind an established public-sector budgeting platform for San Bernardino County's budgeting-system pursuit. The seam is deliberately outside core budgeting-product ownership: we build the integration, migration, reconciliation, AI-grounding, workflow-audit, and acceptance evidence that makes a prime's platform easier to demonstrate, implement, test, and defend. The work can begin against synthetic/de-identified fixtures and a prime-provided interface contract, with production/customer access gated separately.

## Why this seam exists

The County's underlying RFI asks vendors to address all of the following in one program:

- SAP S/4HANA and Oracle Fusion HCM interoperability;
- interface monitoring, troubleshooting, and reconciliation;
- version/scenario and complete change history;
- workflow/approval controls;
- AI source grounding, permissions, human review, auditability, and correction;
- post-adoption amendment lineage;
- system exit and data portability;
- realistic demonstrations of those capabilities.

A platform vendor owns the core product. TJLabs can own the **evidence and acceptance layer across those boundaries**.

## Workstream 1 — ERP/HCM integration acceptance

### Inputs

Prime-supplied, non-secret interface descriptions for selected SAP S/4HANA and Oracle Fusion HCM flows, approved sample/synthetic records, mapping rules, and expected controls.

### Deliverables

- interface/source/target inventory;
- versioned schema + transform contract;
- replayable fixtures for selected inbound/outbound flows;
- record-count and control-total reconciliation;
- duplicate/null/type/reference exception checks;
- expected-vs-observed receipt per replay;
- retry/idempotency classification where the prime exposes those semantics;
- operator-facing exception pack.

### Acceptance

For every in-scope fixture the harness emits exactly one deterministic result state:

- `PASS` — all required bindings and reconciliations hold;
- `EXCEPTION` — enumerated mismatch with source/rule identity;
- `UNTESTED` — required interface evidence was not supplied.

Missing evidence cannot silently produce PASS.

## Workstream 2 — migration and data-quality proof

### Inputs

Approved source extracts or synthetic equivalents, mapping/version information, expected destination extracts, and required control totals.

### Deliverables

- source snapshot manifest;
- transform/mapping identity;
- before/after row and control-total reconciliation;
- rejected-record ledger;
- historical/version lineage checks where provided;
- attachment/document inventory parity checks if in scope;
- repeatable migration rehearsal receipt.

### Acceptance

Two runs over byte-identical evidence and mapping inputs yield the same normalized receipt. Any missing/mismatched source identity, transform identity, required control total, or record set yields a non-PASS state.

## Workstream 3 — AI grounding and review evidence

### Inputs

Prime-defined AI use case(s), authorized evidence sources, user/role permission model, generated output schema, and human-review flow.

### Deliverables

- evidence/source-set manifest per AI result;
- permission/source binding;
- unsupported-claim state for assertions lacking required evidence;
- mechanical prohibition on treating generated narrative as budget-record approval/mutation authority;
- reviewer identity + disposition record;
- correction/rejection/revision lineage;
- hostile fixtures for missing provenance, stale source identity, duplicate evidence IDs, and unreviewed promotion.

### Acceptance

An AI result cannot be promoted to an accepted analytical artifact when its required evidence, permission scope, or human-review state is missing or contradictory. The evidence layer reports the failure rather than manufacturing support.

## Workstream 4 — workflow/version/audit acceptance

### Inputs

Prime-approved workflow state model, roles, baseline/version semantics, selected change types, and expected audit fields.

### Deliverables

- role-transition fixtures;
- authorized/unauthorized transition tests;
- adopted-baseline vs revised-budget lineage checks;
- snapshot/lock/version comparison checks;
- `who / what / when / reason` change-history assertions;
- rollback/recovery history preservation checks;
- concurrent-edit collision fixtures if supported;
- late-cycle change propagation checks into selected calculations/reports.

### Acceptance

The harness distinguishes valid transition, rejected transition, evidence gap, and inconsistent history. Rollback cannot erase required audit evidence in a passing fixture.

## Workstream 5 — County demo / UAT evidence pack

### Inputs

Prime-selected County demonstration scenarios, product build/version identity, approved data fixtures, and expected outputs.

### Deliverables

For each selected scenario:

- exact product/build identifier;
- fixture/source manifest;
- scenario steps;
- expected result;
- observed result;
- evidence links/identifiers;
- exception/unresolved list;
- rerun receipt.

Candidate scenarios from the County RFI include:

1. annual budget cycle;
2. reduction-target plus enhancement-request workflow;
3. SAP/Oracle interface and reconciliation;
4. AI-assisted budget analysis with grounding and human review;
5. administrator self-service configuration;
6. post-adoption amendment preserving adopted baseline;
7. system exit/data portability.

### Acceptance

No scenario is labeled passed merely because the UI reached a final screen. Required source, state, reconciliation, audit, and version evidence must be present for the scenario's declared acceptance contract.

## Delivery sequence

### Phase A — seam lock

- select exact workstreams;
- lock prime/customer authority boundaries;
- identify systems/interfaces and fixture strategy;
- freeze acceptance criteria and non-goals;
- identify security/data handling restrictions.

Exit: signed/approved statement of work or equivalent written agreement before paid delivery begins.

### Phase B — evidence contract + synthetic proof

- implement the acceptance model against synthetic/de-identified fixtures;
- prove fail-closed behavior and deterministic receipts;
- review exceptions with the prime;
- revise only by versioned contract change.

Exit: prime accepts the evidence contract and fixture proof.

### Phase C — approved environment binding

Only when authorized:

- bind actual schemas/interfaces/extracts;
- run selected acceptance rehearsals;
- triage exceptions;
- preserve environment/build/source identity in receipts.

Exit: agreed in-scope acceptance states produced; unresolved items enumerated rather than suppressed.

### Phase D — handoff / UAT support

- package repeatable runbook;
- deliver evidence/exception outputs;
- support selected demo/UAT reruns;
- transfer operating knowledge to prime/customer staff as agreed.

## Commercial structure

This workshare is intentionally flexible for a prime's procurement strategy.

Supported shapes:

- **T&M specialist workstream** with role/rate/hour ceilings supplied under commercial authority;
- **fixed-scope sprint** after the exact interface/scenario/data boundary is known;
- **phased NTE** where synthetic acceptance design is Phase 1 and environment binding is a separately authorized Phase 2.

No rate, total price, discount, hours, or buyer budget is asserted in this public packet.

The commercial agreement should define at minimum:

- in-scope workstreams;
- data/access assumptions;
- deliverables and acceptance criteria;
- prime/customer dependencies;
- roles and rates or fixed fee;
- not-to-exceed limit if used;
- schedule;
- expense/travel terms;
- IP/license treatment;
- security/confidentiality requirements;
- invoice/payment terms;
- change-control process.

## What TJLabs is **not** offering in this workshare

Unless separately evidenced and agreed, this offer does not claim or include:

- ownership of a complete enterprise budgeting COTS platform;
- County procurement/submission authority;
- SAP/Oracle product licensing;
- prime-contractor status;
- production credentials or administrator access;
- final security/compliance attestation for the prime's platform;
- County references or prior County work;
- actuarial/accounting/legal advice;
- autonomous approval or mutation of County budget records;
- free custom production implementation before agreement.

## Historical first-touch framing

The original ask concerned whether a qualified platform vendor was evaluating the opportunity and whether a bounded paid workshare would help. The OpenGov/Vertosoft first touch has already been sent; do not repeat it or switch routes based on this retained copy. Any later scope handoff requires actual interest and existing owner authority. Do not invent a price or perform free buyer-specific engineering to earn a reply.

## Single-writer and authority rule

Every outbound is one route / one sender / one purpose. Fresh Slack + Gmail collision census and explicit Muse arbitration are required immediately before send/form submission. No Muse response, ambiguous response, or conflicting owner means HOLD.

Any County ePro action is a separate provider/account authority gate and is not created by a teaming email.
