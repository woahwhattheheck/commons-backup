# MRHD Impact Match evidence rail core

Deterministic, network-free reconciliation core for the public 2026 Missouri River Historical Development (MRHD) Impact Match grant rules. This is an **internal delivery primitive**, not a claim that MRHD bought, approved, deployed, or validated a system.

## Public rule binding (2026-09-13)

MRHD's public 2026 materials state that the Impact Match cycle has **$1.5M available**, individual awards of **$25,000–$250,000**, a required **25% recipient match**, and that **no more than 50% of the required match may be in-kind**. The grant is reimbursable; recipients pay project expenses up front and submit a Grant Completion Form for reimbursement. The public schedule says applications closed August 31, funding decisions are announced October 2, and awards are October 22.

Source authority:

- https://mrhdiowa.org/news — 2026 cycle announcement and Executive Director contact
- https://mrhdiowa.org/impactmatchgrant — current rules, reimbursement model, match cap, cycle dates, amendment/completion requirements

Rules can change. Buyer-provided final agreements and amendments remain authoritative. This core therefore records rule parameters in every receipt rather than hiding them in code.

## What the core proves

For a frozen JSON ledger it:

- applies only **approved** award amendments to the award amount while preserving all amendment lineage;
- computes the required match using integer cents and ceil-to-cent arithmetic;
- counts only **realized** cash/in-kind contributions toward match;
- caps counted in-kind match at the configured share of required match;
- requires eligible project spend to cover award + required match;
- reconciles paid/pending reimbursements without letting paid reimbursement exceed the award or eligible spend;
- requires pending milestones to remain visible as a hold;
- rejects duplicate award IDs, cross-ledger event ID collisions, negative monetary values, unsupported states, malformed evidence hashes, and unknown schema keys;
- sorts every set-like surface before output so input order cannot change the receipt;
- emits a SHA-256 over canonical JSON and can verify that receipt offline.

A valid ledger can still return `HOLD`. `HOLD` is a measured state, not a runtime failure and never becomes an approval decision.

## Run

```bash
python revenue/mrhd_impact_match_rail/reconcile.py input.json --output receipt.json --require-pass
python revenue/mrhd_impact_match_rail/reconcile.py --verify receipt.json
python -m unittest revenue/mrhd_impact_match_rail/test_reconcile.py
python -O -m unittest revenue/mrhd_impact_match_rail/test_reconcile.py
```

Exit codes: `0` valid/pass (or valid receipt), `2` invalid/ambiguous input, `3` valid ledger with one or more holds when `--require-pass` is used, `4` invalid/tampered receipt.

## Input contract

Money is integer cents only. Every financial event carries a unique `event_id` and a SHA-256 of the buyer-controlled source evidence. Completed/pending/waived milestone states also carry evidence hashes. Evidence bytes themselves are **not** stored here.

The implementation deliberately does not ingest names, beneficiary PII, bank data, grant-portal credentials, or payment credentials. A production implementation would add buyer-approved access control, evidence storage, signatures, export/reporting, workflow/UI, backups, operator runbooks, and acceptance against MRHD-controlled fixtures.

## Acceptance boundary

This core supports the narrow arithmetic/lineage/replay portion of the commercial offer. It does **not** establish a customer relationship, contract, grant eligibility, reimbursement approval, compliance certification, impact measurement, funds movement, or the full proposed implementation. MRHD staff and its Board retain every substantive grant decision.
