# Proposed specialist workshare — Catawba County ERP RFP 27-1004

**State:** `PROPOSED_NOT_ACCEPTED`  
**Commercial structure:** subcontract behind a qualified ERP software/integration proposer  
**Fixed fee:** **$32,000**  
**Delivery window:** **20 business days** from receipt of the prime-approved interface inventory, migration extracts/fixtures, target data contracts, and UAT requirement mapping.  
**Optional shortlisted-demo / due-diligence support:** **$8,000 fixed / up to 5 business days** after written activation.

## Deliverables

1. **Migration reconciliation pack** — stable source identities, canonical values, source/target counts and hashes, missing/extra/changed records, financial-total conservation, exception ledger, and repeatable rerun evidence.
2. **Integration replay pack** — request identity, payload hashes, retries/idempotency, timeout-after-commit cases, duplicate-commit detection, rejects/dead letters, and operator recovery evidence for scoped interfaces.
3. **Sensitive-data evidence boundary** — repository/demo fixtures use tokens rather than raw SSNs, bank/routing details, birth dates, home addresses, or personal email; production handling remains inside the prime/County-approved security boundary.
4. **UAT evidence manifest** — requirement-to-scenario mapping, immutable evidence hashes, explicit pass/fail/blocked state, and unresolved-exception list.
5. **Cutover / rollback gate** — migration + interface + UAT evidence rollup that can become `ready_for_owner_review` while never granting production-cutover or County-submission authority.
6. **Shortlist evidence support (optional)** — exact-demo fixture pack, failure/recovery demonstrations, and evidence readout for implementation/technical due diligence.

## Acceptance criteria

The fixed-scope workshare is accepted on the mutually approved dataset when:

- every scoped source record has a deterministic source identity and target disposition;
- duplicate identities fail closed rather than overwrite;
- unexplained missing/extra/changed migration records are zero, or remain explicit in an agreed exception ledger;
- financial totals for scoped amount-bearing records reconcile by agreed domain/type/currency group;
- retry of the same interface request cannot silently mutate identity or produce a second commit;
- every scoped UAT scenario carries a requirement reference, result state, and evidence hash;
- replaying the same approved inputs reproduces the same evidence hashes; and
- no artifact grants production cutover, proposal submission, contract acceptance, or County authority.

## Prime responsibilities / retained authority

The prime retains ERP licensing and configuration, the RFP minimum-experience gate, bidder forms/signatures, pricing, staffing, references, insurance, data residency/security commitments, hosting/SLA, County communication, implementation management, actual production access, final UAT, cutover authorization, and proposal submission.

The prime supplies approved non-production fixtures or controlled extracts, target data contracts, interface specifications, requirement mapping, test environment access if needed, and one authorized reviewer.

## Exclusions

No direct County contact by this workshare; no sealed proposal, signature, pricing-form completion, software-license representation, inheritance of a partner's references or insurance, production credentials by default, unbounded data cleansing, unsupported security certification, award/payment/revenue claim, or representation that a specific ERP vendor is bidding unless separately evidenced.
