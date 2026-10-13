# Multi-Framework Evidence Freshness Gate

A dependency-free, read-only pre-assessment QA gate for evidence reused across SOC 2, ISO 27001, HITRUST, and PCI DSS work.

It requires each evidence object to carry an opaque owner reference, collection time, assessment-period coverage, framework/control mapping, SHA-256 checksum, freshness-rule identity, and source reference. It emits exactly one state per object:

- `REUSABLE`
- `STALE`
- `SCOPE_MISMATCH`
- `MISSING_OWNER`
- `INCOMPLETE`

`REUSABLE` is deliberately narrow. It means the supplied record is complete, its declared mappings are inside the declared assessment scope, its observed coverage spans the declared assessment period, its coverage does not extend beyond collection/evaluation custody, and it is current under the supplied freshness policy. It does **not** mean the evidence is authentic, sufficient for an audit, that a control is effective, or that any certification should be granted. Scope, policy, owner and source references remain caller-declared inputs; do not promote this packet into an independent authority root.

## Current-time and temporal custody

Production `compile_packet(raw)` owns process UTC and exposes no caller-selected evaluation clock. Deterministic historical compilation exists only behind underscored internal/test helpers.

Production `verify_packet(packet)` first replays the exact historical bytes for integrity, then reevaluates the embedded normalized input against verifier-owned current UTC. It rejects future packet evaluation instants and rejects a packet whose classification has changed since compilation, including a formerly reusable object that has become stale. Historical integrity replay alone is not a current-freshness decision.

Evidence cannot claim observed coverage after its own `collected_at` or after the evaluation instant. Such rows are `INCOMPLETE` with `FUTURE_COVERAGE`. This module intentionally fails closed rather than guessing whether an untyped artifact is a prospective policy/document whose validity might extend into the future.

## Determinism and provenance

The compiler canonicalizes scope, mappings, and evidence order; emits a source-field trace for every result; commits the normalized input and projection with SHA-256; renders deterministic Markdown; and produces a content-addressed receipt. Internal deterministic replay recompiles at the recorded evaluation instant only to validate receipt integrity; current verification always uses verifier-owned process time.

## CLI

```bash
python -m revenue.multi_framework_evidence_freshness.cli compile input.json packet.json review.md
python -m revenue.multi_framework_evidence_freshness.cli verify packet.json
```

Input JSON is read from one bounded regular-file descriptor. Final-component symlinks and non-regular inputs such as FIFOs fail closed; oversized inputs are rejected before unbounded reading and in-read mutation is detected. Outputs are create-exclusive and created relative to a retained parent-directory descriptor; a late second-output failure preserves the first publication for explicit reconciliation rather than deleting by pathname.

## Golden acceptance

`golden.py` deterministically materializes exactly 400 temporally possible synthetic evidence objects and pins the canonical corpus SHA-256. The focused hostile suite requires exactly:

- 240 `REUSABLE`
- 50 `STALE`
- 40 `SCOPE_MISMATCH`
- 35 `MISSING_OWNER`
- 35 `INCOMPLETE`

Coverage includes current-time API custody, future packet rejection, fresh-to-stale verification failure, future collection/coverage, coverage-after-collection, duplicate keys/IDs, non-finite and bool/int traps, secret-shaped refs, symlink/FIFO/oversize input rejection, deterministic receipts, Markdown commitment, create-exclusive output, symlinked parent rejection, and normal + optimized Python.

## Authority ceiling

This module performs no audit or certification opinion, control-effectiveness rating, evidence alteration, independence-sensitive recommendation, customer/assessor contact, provider/account mutation, submission, signature, payment, or revenue recognition. Human assessors retain those decisions.
