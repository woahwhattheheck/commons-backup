# Qualification Evidence Vault

This package answers a narrow procurement question from explicit evidence: **does the current evidence support a prime response, require a qualified partner, require owner evidence, or establish a disqualifying gap?**

It does not infer that a repository merge is a customer reference, that a proposed price is revenue, that an internal project is past performance, or that an owner assertion proves insurance/certification/reseller status. Categories are exact and non-substitutable.

## Outcomes

- `PRIME_SUPPORTED` — every modeled mandatory requirement is satisfied by fresh, exact-category `VERIFIED` evidence.
- `PARTNER_ONLY` — all unresolved modeled gaps are explicit missing/expired requirements that the solicitation says a partner may cure.
- `HOLD_MISSING_EVIDENCE` — at least one mandatory requirement is unknown, owner-only, stale under the solicitation's freshness rule, or absent from the evidence vault. Unknown never silently becomes a partner gap or a prime pass.
- `DISQUALIFIED` — an explicit missing/expired mandatory requirement is marked non-curable and disqualifying.

These are evidence-routing labels, not buyer decisions. Every packet keeps outreach, submission, award, contract, certification/reference-use, payment and revenue authority false.

## Evidence model

Statuses are `VERIFIED | MISSING | OWNER_ONLY | EXPIRED | UNKNOWN`. Visibility is `PUBLIC | PRIVATE`. Each record binds an exact category and qualifier, source kind/reference, event time, and optional expiry.

Sensitive/private material belongs in a private vault. `redact` omits private rows completely and exposes only `private_record_count`; assessment packets never emit private evidence identifiers, only private counts. This repository intentionally contains only public provider-verifiable delivery examples and a synthetic solicitation.

`VERIFIED` is a curated vault state, not a live network attestation. The evaluator does not fetch external providers at runtime, and every packet states `CURATED_BUNDLE_NOT_LIVE_PROVIDER_AUTHENTICATED`. Provider URLs/receipts must therefore be checked by the process that curates the vault; the evaluator enforces category/source compatibility and deterministic qualification over that curated evidence without pretending caller JSON is cryptographically authenticated.

The public examples demonstrate the anti-alias rule: merged OSS PRs are `DELIVERY_RECEIPT/OSS_EXTERNAL_MERGE`. They cannot satisfy `PAST_PERFORMANCE`, `REFERENCE_PERMISSION`, `CERTIFICATION`, `PAYMENT_RECEIPT`, or any other category merely because the merge is real.

## CLI

```bash
python -m revenue.qualification_evidence_vault.cli compile \
  --vault revenue/qualification_evidence_vault/example.public-evidence.json \
  --solicitation revenue/qualification_evidence_vault/example.synthetic-solicitation.json \
  --as-of 2026-09-16T22:45:00Z \
  --packet /tmp/qualification.json \
  --brief /tmp/qualification.md

python -m revenue.qualification_evidence_vault.cli verify \
  --vault revenue/qualification_evidence_vault/example.public-evidence.json \
  --solicitation revenue/qualification_evidence_vault/example.synthetic-solicitation.json \
  --packet /tmp/qualification.json \
  --brief /tmp/qualification.md
```

Inputs are bounded, strict UTF-8 JSON with duplicate keys/non-finite numbers rejected. POSIX input opens use no-follow/nonblocking descriptor checks and require regular files. Outputs are create-exclusive mode `0600` where supported.

## Partner-gap semantics

A requirement becomes `PARTNER_GAP` only when the vault explicitly contains missing/expired evidence and the requirement declares `partner_can_cure=true`. No record, `UNKNOWN`, `OWNER_ONLY`, or evidence too old for the solicitation produces `OWNER_EVIDENCE_REQUIRED` instead. This prevents a convenient teaming story from substituting for basic evidence collection.

## Regression contract

The test suite covers category aliasing, merged-work/reference conflation, payment/delivery conflation, unsupported certification, owner assertions, stale insurance, explicit partner gaps, non-curable gaps, private redaction, duplicate JSON keys, packet tamper, freshness, bool-not-int, create-exclusive publication, CLI compile/verify, and optimized Python.
