# Bidder Qualification Evidence Vault

A buyer-agnostic, evidence-only authority layer for reusable bidder facts. It lets an opportunity-specific pursuit ask narrow questions such as “are two current **corporate** past-performance records present?” without copying private source documents into a public proposal carrier or converting an owner assertion into proof.

`EVIDENCE_READY` is deliberately narrow: the exact query was satisfied by the exact host-pinned evidence snapshots at evaluation time. It is **not** bidder qualification, buyer acceptance, permission to contact a reference, signature authority, an insurance/security certification, a solvency finding, a bid/submission authorization, an award, payment, or revenue.

## Evidence classes

`ENTITY_STANDING`, `CORPORATE_PAST_PERFORMANCE`, `CLIENT_REFERENCE`, `STAFF_CREDENTIAL`, `STAFF_AVAILABILITY`, `INSURANCE_ARTIFACT`, `SECURITY_ARTIFACT`, `FINANCIAL_DOCUMENT`, `SIGNER_AUTHORITY`, and `VENDOR_FORM`.

Each registry item contains only PII-minimized metadata plus a stable evidence ID, exact source SHA-256, observation/currentness data and optional validity date. Raw private documents, raw reference contact values, and buyer-confidential packets stay outside this package.

Mechanical boundaries include:

- individual prior-employer work cannot satisfy `CORPORATE_PAST_PERFORMANCE`;
- reference release is explicit and still never authorizes contact;
- financial documents prove presence/period only, never solvency;
- insurance/security artifacts never become adequacy/certification claims;
- staff availability is time-bounded;
- signer evidence never grants signature permission;
- every action-authority bit in every result is `false`.

## Trust model

Three strict inputs are normalized and hashed:

1. **authority snapshot** — maps each evidence ID to exact class + source SHA-256 and carries a monotone generation/predecessor digest;
2. **registry snapshot** — PII-minimized metadata whose evidence set/class/source hashes must exactly match the authority snapshot;
3. **query** — exact evidence requirements pinned to one authority ID/generation and one registry ID.

Compilation also requires `expected_authority_sha256` and `expected_registry_sha256`. Those roots must come from independently retained trusted state. The `roots` CLI command is setup convenience only; hashing attacker-supplied bytes and trusting the resulting hash is self-authentication.

Verification first reconstructs the historical bundle byte-for-byte at its recorded evaluation time, then re-evaluates the same trusted snapshots at the verifier's current process-owned UTC time. A once-valid receipt therefore becomes current `HOLD` after evidence ages out or expires.

## CLI

The CLI is stdin/stdout only and performs no provider/filesystem/customer mutation.

```bash
python -m revenue.bidder_qualification_vault.vault roots < roots-envelope.json
python -m revenue.bidder_qualification_vault.vault compile < compile-envelope.json > bundle.json
python -m revenue.bidder_qualification_vault.vault verify < verify-envelope.json > verification.json
```

`compile` requires `authority`, `registry`, `query`, `expected_authority_sha256`, `expected_registry_sha256`; `verify` adds `bundle`. Exit status: `0` current ready, `2` valid current hold, `3` malformed/untrusted/tampered.

Opportunity owners remain authoritative for buyer packets, deadlines, bid/team/no-bid posture, proposal content, pricing, legal/commercial decisions and submission. Consume this vault only as reusable evidence readiness.

## Validation

```bash
python -m unittest -v revenue.bidder_qualification_vault.test_vault
python -O -m unittest -v revenue.bidder_qualification_vault.test_vault
python -m py_compile revenue/bidder_qualification_vault/*.py
```

The focused hostile suite covers root mismatch/rollback, authority/registry transplant, stale/future/expired evidence, corporate-vs-individual past performance, reference release, insurance/security/signer state, subject/query binding, deterministic replay, currentness recheck, strict JSON, type confusion, and bundle tampering.
