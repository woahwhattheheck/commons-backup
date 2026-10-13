# Data Migration + Integration Acceptance Workshare

**State:** `PROPOSED_NOT_ACCEPTED`  
**Fixed-fee band:** $18,000–$45,000 USD (reference $30,000)  
**Target delivery:** 10–25 business days after complete accepted intake (reference 15)

## Bounded scope

One frozen legacy→target migration boundary plus agreed interfaces. Reconcile source-to-target fields/counts/values; replay interfaces for idempotency and named failures; produce UAT/cutover evidence and explicit exception ownership.

## Deliverables

- source→target field/count/value reconciliation matrix
- interface replay/idempotency evidence for agreed fixtures and failure cases
- exception ledger with owner, disposition, and retained evidence references
- UAT/cutover acceptance pack with rerun instructions and immutable source/test receipt

## Acceptance

- written tolerances reconcile or remain explicit HOLD exceptions
- named duplicate/replay/failure cases demonstrate fail-closed behavior
- buyer/prime can rerun the supplied checks from documented inputs
- no silently dropped row, interface, or unresolved ownership remains

## Milestones

1. Boundary + acceptance lock.
2. Deterministic draft evidence pack and exception review.
3. Final acceptance handoff with rerun instructions and source/test receipt.

## Intake / security gates

- written source/target boundary and authoritative system owners
- representative export/schema plus explicit row/interface bounds
- named acceptance owner and exception/tolerance policy
- non-production fixture path first; production credentials are not required for qualification

## Retained authority / exclusions

Prime/vendor retains architecture and product commitments. Buyer retains security/privacy/legal/compliance, production access, acceptance, signature, payment, award, and cutover authority. Excludes platform replacement, unbounded data cleansing, open-ended managed service, credential harvesting, and unsupported certification.

A routing or interest reply does **not** establish acceptance, contract, invoice, payment, or revenue.
