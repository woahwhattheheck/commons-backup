# Kalleid LIMS implementation acceptance workshare

**State:** `PROPOSED_NOT_ACCEPTED`  
**Counterparty:** Kalleid, Inc.  
**Commercial hypothesis:** USD 18,000 fixed fee  
**Delivery target:** 15 business days after complete, approved inputs  
**Owner:** Token Junkie Labs (TJLabs)  
**Publication state:** NOT SENT — external publication requires a separate current Muse single-writer decision plus last-inch provider/relationship recensus.

## 1. Purpose

This packet defines one bounded paid overflow / second-source quality-assurance workshare for a laboratory-informatics implementation. It is deliberately adjacent to Kalleid's published services rather than a platform-replacement proposal.

Kalleid's current public materials describe support for scientific-software implementations, chemistry data migration, testing and validation, user/functional requirements, IQ/OQ/PQ scripts and results, release documentation, project management, documentation/training, and scientific/technical staffing. This proposal therefore focuses on an independently reviewable acceptance slice that can plug into a Kalleid-led customer implementation without displacing Kalleid's customer, solution, regulatory, deployment, or commercial authority.

This document does **not** assert that Kalleid has a backlog, defect, staffing shortage, active opportunity, customer need, or obligation to use TJLabs.

## 2. Bounded work package

TJLabs proposes to own exactly one owner-approved migration/integration acceptance slice. The slice is identified at kickoff by a frozen scope key containing:

- one implementation / project identifier;
- one approved legacy/source export family;
- one approved target-system export or read-only evidence family;
- one closed set of interfaces or transfer paths;
- one closed UAT/validation requirement set;
- one acceptance decision owner designated by Kalleid/customer.

No additional system, business process, interface, dataset, location, or validation family is silently included.

### A. Migration evidence reconciliation

TJLabs will reconcile owner-supplied before/after evidence for the approved migration slice and produce:

1. deterministic row/object population counts where meaningful;
2. key/identifier preservation or explicitly approved remapping evidence;
3. required-field completeness checks;
4. duplicate/orphan/unmapped-object findings;
5. bounded field-level spot checks selected from a documented sampling rule;
6. exception classification with source evidence references;
7. explicit `PASS`, `HOLD`, or `NOT_TESTABLE_FROM_SUPPLIED_EVIDENCE` outcomes per acceptance rule.

TJLabs will not infer successful migration from screenshots, filenames, operator assurances, or aggregate counts alone when the acceptance rule requires stronger evidence.

### B. Interface replay and idempotency evidence

For the closed interface set, using approved non-production inputs and owner-supplied logs/exports where required, TJLabs will produce evidence for:

- one successful-path replay per admitted interface scenario;
- duplicate/retry behavior where the interface contract makes retries possible;
- stable correlation identifiers or an owner-approved equivalent;
- expected rejection / negative-path behavior for the agreed cases;
- source-to-target payload or semantic reconciliation at the agreed evidence depth;
- an exception ledger for mismatches, missing evidence, and ambiguous outcomes.

No destructive production replay is authorized by this workshare.

### C. Exception / HOLD ledger

Every unresolved item is recorded with, at minimum:

- stable exception id;
- requirement / test / interface / migration reference;
- evidence references;
- observed result;
- expected result;
- severity / disposition class supplied or approved by the owner;
- owner / next action;
- closure evidence requirement;
- state: `OPEN`, `HOLD`, `RETEST_READY`, or `CLOSED_WITH_EVIDENCE`.

A missing artifact, ambiguous observation, source contradiction, failed replay, or unapproved assumption remains a HOLD. TJLabs does not convert uncertainty into acceptance.

### D. Reviewer-verifiable UAT / validation acceptance pack

The final pack contains:

1. frozen scope and input manifest;
2. source/evidence digest inventory where byte custody exists;
3. requirements-to-evidence matrix;
4. migration reconciliation results;
5. interface replay results;
6. exception/HOLD ledger;
7. rerun/retest evidence for closed exceptions;
8. acceptance checklist with explicit evidence references;
9. residual-risk / unresolved-item list;
10. a concise reviewer handoff identifying what is proven, what is owner-asserted, and what remains unproven.

The pack is designed so a Kalleid/customer reviewer can trace every material conclusion back to the supplied or generated evidence rather than relying on a narrative status claim.

## 3. Required inputs

The 15-business-day target starts only after the designated owner confirms a complete approved input set. Expected inputs are:

- approved scope key and acceptance owner;
- current requirement / test / validation references applicable to the slice;
- approved legacy/source evidence export;
- approved target evidence export or read-only evidence;
- interface specifications or owner-approved expected-behavior statements;
- approved replay fixtures or owner-run replay outputs;
- existing issue/deviation/defect references relevant to the slice;
- data-handling instructions, redaction rules, and environment constraints;
- owner-approved severity/disposition vocabulary;
- named reviewers for ambiguity and final acceptance decisions.

If a required input is unavailable, TJLabs records the dependency as a HOLD and identifies the exact acceptance statement that cannot yet be demonstrated.

## 4. Data and environment boundary

Default delivery posture:

- no production credentials;
- no standing privileged account;
- no production mutation;
- no production deployment;
- no direct database writes;
- no independent regulatory certification;
- no legal/compliance representation on behalf of Kalleid or its customer;
- no need for learner/patient/subject identity when opaque identifiers or redacted evidence are sufficient;
- owner-approved exports, replay fixtures, logs, screenshots, or read-only evidence only unless a separately approved access protocol is executed.

If regulated or sensitive data is unavoidable, the work does not begin on that material until the owner supplies the governing data-handling terms and approved transfer/access path.

## 5. Responsibility split

### Kalleid / customer retains

- customer relationship and prime engagement responsibility;
- solution architecture and platform selection;
- system configuration and implementation authority;
- regulatory interpretation and compliance ownership;
- validation strategy approval;
- requirement approval;
- data-access approval;
- production access and deployment;
- deviation/CAPA or equivalent formal quality decisions;
- risk acceptance;
- final UAT / validation / release approval;
- commercial pricing to the end customer;
- signatures, contractual commitments, and submission authority.

### TJLabs owns inside the frozen slice

- evidence inventory and traceability structure;
- deterministic reconciliation rules agreed for the slice;
- migration evidence reconciliation;
- interface replay evidence analysis;
- duplicate/retry/idempotency observations where applicable;
- exception/HOLD ledger maintenance;
- requirements-to-evidence mapping;
- reviewer-verifiable acceptance pack assembly;
- concise handoff identifying proven vs owner-asserted vs unresolved claims.

## 6. Acceptance criteria

The fixed-fee work package is delivery-complete when all of the following are true:

1. **Scope frozen:** the admitted implementation slice, interface set, requirements set, and evidence families are enumerated.
2. **Input manifest complete:** every artifact used in a material conclusion is identified; retained bytes are digested where byte custody exists.
3. **Migration reconciliation complete:** every agreed migration rule has `PASS`, `HOLD`, or `NOT_TESTABLE_FROM_SUPPLIED_EVIDENCE` with evidence.
4. **Interface evidence complete:** each admitted scenario has replay evidence or an explicit HOLD explaining the missing owner-controlled action/evidence.
5. **Exceptions closed or explicit:** every finding is either `CLOSED_WITH_EVIDENCE` or remains visible as an unresolved HOLD; nothing is silently waived.
6. **Traceability complete:** each acceptance conclusion links to requirement/test evidence and any relevant exception.
7. **Reviewer pack reproducible:** a reviewer can follow the pack from frozen scope to the evidence supporting each material conclusion.
8. **Authority truth preserved:** the pack does not represent TJLabs as the final regulatory, quality, production-release, customer, or contractual authority.

A project can be delivery-complete while still containing owner-visible HOLDs if the owner-controlled inputs or decisions needed to clear those HOLDs were not supplied. In that case the deliverable truthfully reports readiness and residual blockers; it does not fabricate a clean validation result.

## 7. Schedule

Target delivery is 15 business days after complete approved inputs.

A typical sequence is:

- business days 1–2: input verification, scope freeze, traceability skeleton;
- days 3–7: migration reconciliation + first interface evidence pass;
- days 8–10: exception triage, owner questions, approved reruns/retests;
- days 11–13: closure evidence + UAT/validation pack assembly;
- days 14–15: reviewer walk-through, correction of evidence-link defects, final handoff.

Owner-caused access delays, missing source evidence, changing requirements, new interfaces, new datasets, or materially expanded validation obligations pause the affected acceptance item and may require a separately approved change in scope.

## 8. Commercial assumptions

The commercial hypothesis is **USD 18,000 fixed / PROPOSED_NOT_ACCEPTED** for one slice meeting the bounds above.

The fixed fee assumes:

- one project/slice;
- one closed source/target evidence family;
- a bounded interface set agreed at kickoff;
- owner-provided approved inputs;
- no production operations;
- no travel;
- no end-customer procurement response authored or signed by TJLabs;
- no software license or infrastructure spend borne by TJLabs;
- no unbounded manual remediation/data-cleaning program;
- no independent regulated-system certification.

Material expansion requires an explicit written scope change before work is represented as included.

## 9. Out of scope

Unless separately agreed, this workshare excludes:

- platform implementation ownership;
- system administration;
- production deployment;
- master-data remediation at scale;
- custom application development unrelated to acceptance evidence;
- end-user training delivery;
- regulatory/legal advice;
- formal quality-unit approval;
- customer contracting/procurement response;
- 24x7 support;
- open-ended defect remediation;
- penetration testing;
- performance/load testing beyond explicitly admitted scenarios.

## 10. Kickoff decisions

A productive first scoping call can be reduced to six decisions:

1. What exact implementation/migration slice needs independent acceptance evidence?
2. Which requirements and validation artifacts control that slice?
3. What source/target evidence can be supplied without production credentials?
4. Which interfaces/retry scenarios are in scope?
5. Who owns ambiguity, severity, and final acceptance decisions?
6. What existing deadline or review event should the 15-business-day pack support?

## 11. Public-source provenance used for fit qualification

Current public Kalleid materials used only to establish topical adjacency:

- `https://kalleid.com/about/` — laboratory IT consulting/scientific staffing; software implementation support; technical writing/documentation; business analysis; testing/validation; project management.
- `https://kalleid.com/services/testing-validation/` — testing/validation; user and functional requirements; IQ/OQ/PQ scripts/results; validation report; release documentation; risk-based validation; ongoing validation; chemistry data migration and technical staffing service adjacency.

These sources establish what Kalleid publicly says it does. They do not establish a current need for TJLabs, a customer opportunity, a budget, or acceptance of this workshare.

## 12. Authority / truth ledger

At publication of this repository artifact:

- `external_send_authorized = false`
- `muse_selected = false` unless a later provider receipt proves otherwise
- `counterparty_interest = unknown`
- `proposal_delivered = false`
- `proposal_accepted = false`
- `contract_exists = false`
- `work_authorized = false`
- `invoice_exists = false`
- `payment_received = false`
- `receivable_exists = false`
- `booked_revenue = false`
- `recognized_revenue = false`

A repository merge is product/readiness evidence only. It is not commercial acceptance or revenue.