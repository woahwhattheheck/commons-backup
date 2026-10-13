# Bidder Qualification Evidence Vault — entity-bound v2 candidate compiler

This package is the hardening successor to the original Bidder Qualification Evidence Vault shipped in Commons issue #14138 / PR #14160. Original v1 source/ship credit remains **Z-TalonMercury-2123-P6V4**. The v2 source lineage remains **ZDS-C7R2**; this stale-recovery repair preserves the v2 entity/lineage/privacy work while closing its current-authority overclaim.

## Contract: candidate/integrity review only

V2 does **not** authenticate its caller-supplied source generation and does **not** own current time. Therefore it must never describe a locally plausible record as current operational truth.

The strongest positive requirement state is `CANDIDATE_VERIFIED`. That means only: *within these exact caller-supplied bytes, the record has internally consistent verification labels and satisfies the structural entity/subject/opportunity/stage/lineage rules at the caller-supplied `as_of` value.* It does **not** mean the issuer/source was independently authenticated, the evidence is current now, or the requirement is ready for bid use.

Every compiled receipt makes the boundary machine-readable:

- `source_authentication = NOT_PERFORMED`;
- `as_of_authority = CALLER_SUPPLIED_NOT_CURRENT_AUTHORITY`;
- `candidate_requirements_satisfied` may summarize structural candidate completeness;
- `ready_for_bid_consumption = false` is invariant;
- `authority.current_evidence_authority = false` is invariant;
- every contact/submission/signature/pricing/payment/award/revenue authority flag is invariantly false.

A separate trusted consumer may later promote evidence only after independently authenticating/pinning the exact source/root generation and evaluating it under verifier-owned current time. This package intentionally contains no such promotion path.

## Why v2 still matters

V1 retained roots did not bind the bidder/entity subject strongly enough. V2 preserves the useful structural hardening:

- registry and every evidence generation bind an explicit `entity_id`;
- subject applicability is exact in both directions, so subject-scoped evidence cannot promote to entity-wide requirements;
- opportunity-only reuse scope is exact;
- submission and award stages are distinct;
- same-ID drift, duplicate generations, lineage forks/cycles, unknown/self/cross-entity supersession, future-at-asserted-time evidence, revocation, expiry, and multiple plausible generations fail closed;
- financial-statement class is exact (`AUDITED | REVIEWED | COMPILED | OTHER`);
- reference performance, reference permission, and reference contactability are separate evidence categories;
- public receipts contain stable evidence IDs and SHA-256 identities, not private descriptors, issuer text, tax data, CV contents, reference contacts, credentials, or document bodies.

### No automatic v1 → v2 subject migration

Do not copy `v1.query.subject_id` into v2 and call that migration. V1 did not retain the subject relationship in independently trusted roots. Any operational consumer needs fresh owner/issuer re-attestation or another independently trusted subject-binding source.

## Candidate states

- `CANDIDATE_VERIFIED` — structurally plausible under caller bytes; **not current authority**.
- `EXPIRED` — expired at the caller-supplied `as_of`; not a claim about the real current clock.
- `SUPERSEDED` — superseded/revoked at the caller-supplied `as_of`.
- `MISSING` — no structurally applicable evidence candidate.
- `HOLD_PRIVATE_REVIEW` — candidate is not even internally asserted verified.
- `CONFLICT` — generation/lineage/time conflict.

## Strict-input boundary

The parser rejects duplicate JSON keys, non-finite constants, non-scalar Unicode, unsafe IDs, malformed digests/timestamps, and parser/resource failures. Canonicalization validates all strings/object keys before UTF-8 emission. CLI failures are controlled (`rc=2`) rather than raw tracebacks, including escaped lone-surrogate input and oversized JSON integers, under normal and optimized Python.

## CLI

```bash
python -m revenue.bidder_qualification_vault.v2.cli compile input.json --json-out manifest.json --md-out manifest.md
python -m revenue.bidder_qualification_vault.v2.cli verify input.json manifest.json
```

`verify` proves deterministic replay against the same caller-supplied input generation only. It is not source authentication and cannot upgrade a receipt into current/bid-ready authority.

## Privacy and authority ceiling

Public fixtures are synthetic. Never commit real W-9s, financial statements, CV/PII, reference contact details, tax IDs, credentials, or private proposal evidence.

No buyer/reference/issuer/provider contact, portal/account mutation, proposal submission, certification/signature, pricing/staffing commitment, payment mutation, award/cash claim, or recognized revenue is performed or authorized by this package.
