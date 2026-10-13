# Affordable-Housing Compliance Demo Evidence Carrier

Buyer-neutral, offline evidence compiler for a **paid prime/subcontract delivery seam** around municipal affordable-housing compliance software procurements.

It does **not** interpret housing law, determine tenant eligibility/compliance, certify security/accessibility, qualify Token Junkie Labs as a prime, submit a proposal, contact a buyer, or prove acceptance/payment/revenue.

## Why this exists

Two September 2026 San Diego County procurements create a reusable technical acceptance seam:

- City of Oceanside `NSD07182026`, Affordable Housing Compliance Monitoring Software, due 2026-10-19.
- City of Chula Vista `RFP P01-2027`, Compliance Monitoring Software Solution, due 2026-10-07.

Public discovery says the buyers need mature housing-compliance platforms; Chula Vista explicitly calls for an existing platform already used by public agencies. TJLabs therefore participates only behind a qualified housing-compliance prime/operator unless authoritative qualification evidence says otherwise.

## What the carrier proves

Given a prime-approved expectation pack and synthetic/deidentified candidate evidence, it deterministically compiles:

1. **Requirement/source custody** — every expected finding binds to an exact source SHA; discovery-only sources force `HOLD_SOURCE_AUTHORITY`.
2. **AI/demo finding reproduction** — precision/recall against a human/prime-authored gold set. The engine never derives legal rules itself.
3. **Migration reconciliation** — stable record IDs must reconcile source→target with explicit missing/extra/changed IDs.
4. **RBAC/audit behavior** — observed allow/deny behavior is checked against an externally approved role/action matrix.
5. **Exactly-once effects** — retries may replay the same effect ID but cannot mint a second logical effect under one idempotency key.
6. **Threshold authority** — without a separately approved threshold policy the best clean state is `MEASURE_ONLY`; with one, the best state is `READY_FOR_PRIME_REVIEW`.
7. **Reproducibility** — canonical SHA-256 bindings cover source inventory, requirements, findings, migration sets, policies, events, effects, thresholds, and the final receipt.

## Data boundary

Only `SYNTHETIC` or `APPROVED_DEIDENTIFIED` data is accepted. Common direct-PII field names are rejected recursively. Production tenant data is never authorized by a receipt.

## CLI

```bash
python revenue/affordable_housing_compliance_demo/engine.py compile request.json receipt.json
python revenue/affordable_housing_compliance_demo/engine.py verify request.json receipt.json
```

The CLI only reads stable non-symlink JSON and creates output exclusively; it refuses overwrite.

## Decision semantics

- `HOLD_SOURCE_AUTHORITY` — one or more requirements rely on discovery rather than a controlling source.
- `HOLD_EVIDENCE` — migration/access/idempotency evidence is not clean and no approved threshold policy can bound it.
- `MEASURE_ONLY` — evidence is clean but no approved threshold policy exists.
- `HOLD_THRESHOLDS` — an approved threshold policy exists and one or more metrics fail it.
- `READY_FOR_PRIME_REVIEW` — exact inputs satisfy the **prime-approved** threshold policy. This is not buyer acceptance, housing-compliance certification, proposal authority, or production-release authority.

## Source status for the current pursuit

The repository carrier is buyer-neutral. Current Oceanside/Chula Vista web material is **discovery evidence only** until the exact controlling solicitation/addenda are captured and SHA-bound by the pursuit owner. Never convert a search-result summary into `CONTROLLING` authority.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)
