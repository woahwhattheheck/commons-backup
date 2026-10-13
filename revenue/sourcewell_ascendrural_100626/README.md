# Sourcewell RFP 100626 — Rural Access Relay

Operation: `SOURCEWELL-ASCENDRURAL-100626-RURAL-ACCESS-RELAY-ZBFK8D2-20260913`

This package deliberately separates **verified public opportunity facts** from **registered-portal controlling documents** and from the buyer-neutral product kernel.

## Verified public opportunity facts

Sourcewell's public procurement portal currently identifies:

- RFP `100626`, **AscendRural Innovation Challenge: Bridging Distance to Rural Care & Services**.
- Status: **Open**.
- Question deadline: **2026-09-28 15:30 CDT**.
- Proposal deadline: **2026-10-06 15:30 CDT**.
- Submission: **online only** through the Sourcewell Procurement Portal.
- Public scope includes five problem areas: transportation access and coordination; local access to primary/specialty/oral care; chronic condition management; last-mile delivery of essentials; and strengthening the business of rural access.
- The public notice does **not** establish a contract budget. This package rejects any non-null `public_budget` rather than guessing.

Controlling source:
`https://proportal.sourcewell-mn.gov/Module/Tenders/en/Tender/Detail/8f76f478-9d49-487b-8802-2f07435c3d66/`

The portal requires registration for the solicitation documents. Therefore this package is intentionally **not bid-ready**. It remains `HOLD` until exact bytes and hashes are bound for the RFP, Master Agreement, FAQ/Q&A, and current addenda index. Even after those bytes are bound, the gate advances only to `CONTROLLING_SOURCE_BOUND_REVIEW_REQUIRED`; it never infers responsiveness, legal acceptance, pricing, permission to submit, buyer acceptance, award, payment, or revenue.

## Product: Rural Access Relay

The buyer-neutral kernel addresses only three public problem areas:

1. transportation access and coordination;
2. last-mile delivery of essentials; and
3. strengthening the business of rural access.

It is an **evidence/reconciliation rail**, not an autonomous dispatcher. The event ledger models non-emergency ride, essential-goods delivery, and service-handoff workflows. It provides:

- exact event-id replay suppression;
- conflict detection when a reused event id changes meaning;
- monotonic sequence/gap checks;
- one-provider acceptance consistency;
- explicit exception -> provider clear -> reassignment;
- terminal-state enforcement;
- evidence SHA-256 binding; and
- deterministic receipt hashing.

A clean ledger returns `CONSISTENT_FOR_OPERATOR_REVIEW`, never an instruction to dispatch, diagnose, treat, approve eligibility, charge money, submit a proposal, sign a contract, or recognize revenue.

### Hard authority exclusions

The qualification manifest requires these fields to be explicitly false:

- emergency dispatch authority;
- clinical decision / diagnosis / treatment authority;
- eligibility adjudication authority;
- payment authority;
- buyer-contact authority;
- proposal-submission authority;
- contract-signature authority; and
- revenue-recognition authority.

Any escalation of those flags is rejected.

## Files

- `qualification.py` — fail-closed Sourcewell source/document gate with content-addressed receipts.
- `relay.py` — deterministic rural service-handoff ledger auditor.
- `current_notice.json` — public-notice snapshot and buyer-neutral product boundary; controlling documents intentionally empty.
- `../../tests/test_sourcewell_ascendrural_100626.py` — hostile and happy-path tests.
- `../../.github/workflows/sourcewell-ascendrural-100626.yml` — path-scoped normal + optimized Python verification.

## Verification

```bash
PYTHONPATH=. python -m unittest -v tests/test_sourcewell_ascendrural_100626.py
PYTHONPATH=. python -O -m unittest -v tests/test_sourcewell_ascendrural_100626.py
python -m py_compile \
  revenue/sourcewell_ascendrural_100626/qualification.py \
  revenue/sourcewell_ascendrural_100626/relay.py \
  tests/test_sourcewell_ascendrural_100626.py
```

At construction time: 24/24 tests passed under normal Python, 24/24 under `python -O`, and all three Python files compiled.

## Next authorized state transition

1. Register/take the plan in Sourcewell's portal through an authorized account.
2. Retrieve the controlling RFP, Master Agreement, FAQ/Q&A, and current addenda index.
3. Hash the exact bytes and record official portal URLs and retrieval timestamps.
4. Re-run `qualify(...)` with those four document records.
5. Read the controlling documents and bind actual proposer eligibility, evaluation, pricing, insurance/legal, forms, references, and submission requirements.
6. Only then decide direct-prime vs partner/no-go and draft a proposal. The code itself cannot authorize contact or submission.
