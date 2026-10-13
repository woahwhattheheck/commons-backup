# Paid ERP migration / integration acceptance workshare

**Status:** `PROPOSED_NOT_ACCEPTED`
**Reference carrier:** `woahwhattheheck/commons#14869`
**Commercial hypothesis:** **$24,000 fixed** base sprint + **$8,000 fixed** optional cutover dress rehearsal.

This is a subcontract/workshare concept for a qualified ERP prime. It is not a direct response to Columbia Association RFP 27-05 and does not represent TJLabs as the ERP publisher or implementation prime.

## Outcome

Provide an independent, evidence-bound answer to one narrow question before cutover:

> Did the agreed migration wave and retained interfaces produce the records and behavior the frozen mapping/acceptance contract requires, with every exception surfaced rather than silently overwritten or averaged away?

## Base sprint — $24,000 fixed / proposed

### Included scope

- one frozen migration wave;
- up to **250,000 normalized source records** and corresponding target records supplied by the prime;
- one explicit natural/business-key contract;
- one frozen field/transform comparison contract;
- up to **three retained-system interface** acceptance contracts;
- evidence IDs for the six migration phases: Profile, Cleanse, Map, Transform, Validate, Migrate;
- deterministic source↔target reconciliation;
- duplicate/conflicting-key, missing-row, unexpected-row and field-mismatch detection;
- blocking exception ledger;
- phase/interface evidence map;
- deterministic SHA-256-bound acceptance receipt when and only when all bounded gates pass;
- one technical findings review and one final closeout review.

### Delivery window

**15 business days** beginning only after complete intake, frozen acceptance criteria, usable extracts/fixtures, and authorized access to the agreed non-production evidence surface.

A late/incomplete intake moves the start date; it does not silently consume delivery days.

### Acceptance criteria

Base sprint is deliverable-complete when:

1. the frozen scope and comparison fields are recorded;
2. supplied source and target sets can be deterministically indexed or all blocking input defects are reported;
3. every duplicate, missing, unexpected, and mismatched in-scope record is present in the exception evidence;
4. all six migration-stage evidence slots are either bound to evidence IDs or explicitly blocked;
5. each in-scope interface is `PASS` with evidence or explicitly blocked;
6. a passing bounded scope produces a reproducible integrity receipt;
7. a failing bounded scope cannot produce a passing receipt;
8. the prime receives the exception ledger, evidence map, receipt/hold state, and closeout notes.

The sprint does **not** promise that the whole ERP program is ready merely because one bounded wave passes.

## Optional cutover dress rehearsal — $8,000 fixed / proposed

Available only after the base sprint freezes the acceptance contract.

Includes up to **two** replayed evidence sets against the same migration-wave and interface contract, with:

- regression comparison to the frozen baseline;
- newly introduced/resolved exception delta;
- regenerated phase/interface evidence map;
- receipt/hold result for each rehearsal;
- one go/no-go evidence review with the prime's delivery team.

New interfaces, materially changed mappings, additional migration domains, production operations, or new buyer requirements are out of scope and require a separate quote.

## Proposed payment structure

No payment terms are accepted until a written subcontract/work order exists. Suggested structure for negotiation:

- **30%** at written work authorization and complete intake;
- **40%** at delivery of the first full exception/evidence pack;
- **30%** at bounded closeout acceptance.

Optional cutover rehearsal: **50% / 50%** at authorization and completion.

These are proposal terms only. They are not invoices, receivables, earned revenue, cash, or commitments.

## Required from the prime

Before work begins:

- written scope owner and technical contact;
- frozen mapping / transform contract;
- defined business key and comparison fields;
- redacted, synthetic, or contractually authorized non-production source/target data;
- interface acceptance criteria and evidence locations;
- data handling/security instructions;
- explicit statement of which buyer requirements this workshare supports and which it does not;
- confirmation that subcontracting and required insurance/certification terms permit the workshare.

No production credentials should be placed in Commons or Slack.

## Exclusions

Not included:

- ERP software licensing, selection, hosting, configuration, customization, or warranty;
- buyer portal registration or proposal submission;
- direct mutation of Lawson, Dayforce, Club Automation, Smartsheet, IVR, target ERP, financial ledgers, or production integrations;
- penetration testing, SOC/ISO/PCI certification, legal opinion, tax advice, audit opinion, accounting assurance, or accessibility certification;
- MBE certification or representation;
- creation of past-performance references that do not exist;
- production cutover command authority;
- responsibility for defects outside the frozen bounded contract;
- buyer acceptance, award, payment, savings, or revenue guarantees.

## Change control

A change is commercially material if it adds a migration domain, changes the frozen transformation contract, adds an interface, materially increases record volume/complexity, requires production access, or adds a buyer deliverable not already listed.

Material changes pause the affected lane until both parties record a new scope and price. TJLabs does not absorb unbounded ERP-program scope under this fixed-fee workshare.

## Why a prime should pay for this

ERP migrations often fail at seams rather than at the existence of the platform: key collisions, mapping drift, silently dropped records, last-write-wins behavior, retained-system mismatches, and cutover evidence that cannot be reconstructed after the fact.

This workshare sells a deliberately narrow independent control: **exception-first reconciliation plus evidence-bound acceptance**. The prime keeps ownership of the ERP, architecture, buyer relationship, certifications, implementation, and contractual commitments; TJLabs supplies a bounded proof surface that is useful precisely because it is separate from the implementation team's success narrative.

## Authority / outreach gate

This document can be shown to a prospective prime only after the live anti-collision protocol passes:

- fresh Slack census;
- fresh Gmail census;
- Muse single-writer election for the exact recipient/message;
- no contrary owner or delivery-retry state.

Until then, this file is an internal, reusable commercial artifact.