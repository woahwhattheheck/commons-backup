# Operational / Financial Evidence Reconciliation Workshare

**State:** `PROPOSED_NOT_ACCEPTED`  
**Fixed-fee band:** $6,500–$25,000 USD (reference $12,500)  
**Target delivery:** 5–15 business days after complete accepted intake (reference 10)

## Bounded scope

One named legal entity, one closed period, one currency, and explicit retained evidence sources. Reconcile operational rows to invoice/settlement/approval/credit evidence read-only and emit deterministic owner-review exceptions.

## Deliverables

- canonical evidence manifest and normalization/reconciliation rules
- deterministic duplicate/missing/orphan/timing/mismatch exception ledger
- owner-review packet binding material exceptions to retained source evidence
- rerun procedure plus bounded-period close receipt

## Acceptance

- every in-scope retained row is accounted for exactly once or remains explicit HOLD
- totals/classifications reproduce from frozen buyer-supplied inputs
- exceptions are not represented as fraud, savings, recovery, or accounting conclusions without buyer authority
- buyer/prime can rerun the reconciliation and reproduce the owner-review packet

## Milestones

1. Evidence boundary + authority/tolerance lock.
2. Deterministic reconciliation + exception review.
3. Final owner-review pack and rerun handoff.

## Intake / security gates

- one legal entity, closed period, currency, and evidence-source boundary
- buyer-supplied retained exports and owner mapping for rate/contract/approval authority
- written materiality/tolerance rules or explicit zero-tolerance default
- named exception-disposition and acceptance owner

## Retained authority / exclusions

Buyer retains contract interpretation, accounting policy, approval, dispute, posting, payment, recovery, write-off, acceptance, signature, award, and revenue recognition. Excludes payment initiation, ERP/accounting mutation, dispute filing/provider contact, audit/tax/legal/accounting opinions, fraud findings, savings/recovery guarantees, and open-ended bookkeeping/AP/AR.

A routing or interest reply does **not** establish acceptance, contract, invoice, payment, or revenue.
