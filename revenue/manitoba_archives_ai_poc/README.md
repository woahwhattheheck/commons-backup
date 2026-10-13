# University of Manitoba IT-0280-2627-LB — Archives AI Proof of Concept

This directory is a **pursuit qualification and synthetic technical-acceptance carrier**. It is not a response submission, not a University deployment, and not evidence that any legal/privacy requirement has been satisfied.

## Current pursuit state

Public procurement discovery identifies RFP `IT-0280-2627-LB` / MERX notice `0000331062-MERX`, titled *IT Consulting Services for Archives AI Proof of Concept Project*, with a public September 25, 2026 close and submission routing through Euna (formerly Bonfire).

Run:

```bash
python qualification.py public_notice.json
```

The checked-in public notice must return `HOLD_CONTROLLING_PACK_REQUIRED`. That is intentional. Search/index pages can establish a live opportunity but cannot establish controlling requirements, addenda, bidder eligibility, evaluation weights, official forms, exact deadline timezone, or submission mechanics.

## Two independent evidence layers

### 1. Procurement qualification

`qualification.py` is fail-closed. Its ordinary CLI has no parameter that can mint official-source trust. A trusted host may call `evaluate_with_trusted_sources()` only after independently acquiring University/Euna official procurement bytes and recording exact source SHA-256, currentness, supersession, source kind, official locator, and canonical UTC deadline.

Requirements must bind to one exact current source ID + SHA. Mandatory requirements must bind to proven evidence. The maximum state is `READY_FOR_OWNER_REVIEW`, always with `submission_authorized=false`.

### 2. Synthetic Archives-AI acceptance

`poc_acceptance.py` is deliberately source-neutral and synthetic. It verifies mechanics useful to an archive-oriented AI PoC without pretending to know the University's final use case:

- exact corpus snapshot binding;
- record/version/content-hash citations;
- allowed-record retrieval boundaries;
- answer vs abstain vs human-review routing;
- no final answer from review-required synthetic records;
- model/prompt/policy version custody;
- deterministic replay evidence.

This harness does **not** establish production privacy compliance, collection access rights, legal interpretation, archive policy, University acceptance, or model quality on University data.

## Status ladder

- `INVALID` — malformed or contradictory procurement evidence.
- `HOLD_CONTROLLING_PACK_REQUIRED` — discovery-only state.
- `HOLD_DEADLINE_REVERIFY` — controlling deadline reached; current source/addenda must be re-read.
- `HOLD_REQUIREMENT_EXTRACTION_REQUIRED` — official package is bound but requirements have not been extracted.
- `HOLD_MANDATORY_GAPS` — one or more mandatory requirements lack proven evidence.
- `READY_FOR_OWNER_REVIEW` — qualification evidence is complete enough for an owner decision; still no submission authority.

## Validation

```bash
python -m py_compile qualification.py poc_acceptance.py test_qualification.py test_poc_acceptance.py
python -m unittest -v test_qualification.py test_poc_acceptance.py
python -O -m unittest -v test_qualification.py test_poc_acceptance.py
```

The path-scoped workflow also asserts that the checked-in discovery carrier remains on HOLD.

## Explicit non-authority

Nothing in this directory authorizes buyer contact, Euna/Bonfire registration, representations about Canadian/Manitoba eligibility or law, privacy or records compliance claims, insurance/reference/certification claims, pricing, submission, signature, contract acceptance, award, payment, production data access, production deployment, or revenue recognition.

Next owner-controlled work is in `SOURCE_RECOVERY.md`, `EVIDENCE_PLAN.md`, `PROPOSAL_ARCHITECTURE.md`, and `TEAMING_BRIEF.md`.
