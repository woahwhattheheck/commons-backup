# United Fund donor-intent-to-project outcome rail core

Deterministic, network-free reconciliation core for a synthetic portfolio shaped to the publicly reported United Way of Anchorage FY2026 United Fund. This is an **internal delivery primitive**, not evidence that United Way purchased, approved, deployed, or validated a system.

## Public portfolio binding (2026-09-13)

United Way of Anchorage currently reports that FY2026 United Fund grantmaking invested **$250,000** in **17 projects** across **14 nonprofits**, selected from **73 proposals**. Its grants page says the $250,000 has been disbursed and gives the public award-size distribution: most recipients received $15,000, three received $30,000, and one received $10,000.

Source authority:

- https://www.unitedwayanc.org/news/UnitedFundFY26
- https://www.unitedwayanc.org/about/grants

The focused test suite embeds a frozen synthetic fixture using only synthetic partner/project/fund identifiers while preserving those public portfolio counts and award totals. Buyer-controlled agreements, restrictions, amendments, finance records, metric definitions, attestations, and corrections remain authoritative in a real implementation.

## What the core proves

For a frozen JSON ledger it:

- reconciles fund restrictions to exact project allocations and rejects restricted-fund leakage;
- requires award allocation arithmetic and disbursement arithmetic to reconcile in integer cents;
- can require every approved award to be fully disbursed before the portfolio passes;
- preserves project milestone state and holds pending milestones visibly;
- binds each aggregate outcome observation to an explicit metric-definition revision and effective window;
- rejects overlapping metric-definition windows and observations that do not have an applicable definition;
- excludes definitions marked non-donor-safe or causal from publishable donor reporting;
- requires partner attestation for publishable outcome observations;
- preserves correction/withdrawal lineage so a replacement observation cannot silently coexist with the old one;
- rejects conflicting latest attestation states, unknown correction targets, duplicate event IDs, unknown schema fields, malformed SHA-256 evidence references, and negative monetary values;
- rejects beneficiary/person-level field names before reconciliation; the delivery boundary is aggregate outcome evidence only;
- sorts all set-like surfaces before receipt generation so input order cannot change the result;
- emits a SHA-256 over canonical JSON and verifies that receipt offline.

A syntactically valid ledger may return `HOLD`. `HOLD` is a measured reconciliation state, never grant approval, partner-performance judgment, donor solicitation, disbursement authority, or causal-impact certification.

## Run

```bash
python -m unittest revenue/united_fund_outcome_rail/test_reconcile.py
python -O -m unittest revenue/united_fund_outcome_rail/test_reconcile.py
```

Exit codes: `0` valid/pass (or valid receipt), `2` invalid/ambiguous input, `3` valid ledger with one or more holds when `--require-pass` is used, `4` invalid/tampered receipt.

## Input and privacy contract

Money is integer cents. Financial and evidence-bearing events use stable IDs and SHA-256 references to buyer-controlled evidence; the evidence bytes themselves are not stored in this package. Person-level beneficiary fields such as names, email, phone, street address, SSN, and date of birth are rejected rather than silently accepted.

The embedded synthetic fixture contains no real donor, beneficiary, partner, employee, bank, or payment-provider data. A production implementation would still need buyer-approved access controls, source adapters, evidence storage/signatures, UI/workflow, export/reporting, backups, operator runbooks, and acceptance against United Way-controlled fixtures.

## Acceptance boundary

The public $250,000 / 14-nonprofit / 17-project portfolio shape is useful for testing arithmetic and lineage, but it does **not** establish the private restrictions, disbursement records, outcome definitions, attestations, or corrections that only United Way can authorize. This core supports the narrow reconciliation/replay portion of the proposed service; it does not establish a customer relationship, contract, donor intent, grant eligibility, reimbursement/disbursement approval, partner performance, regulatory compliance, or causal impact.
