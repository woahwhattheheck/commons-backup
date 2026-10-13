# Security Questionnaire Evidence Pack

A local, deterministic procurement accelerator for one expensive enterprise-sales bottleneck: turning retained technical evidence into a reviewable security-questionnaire packet **without inventing certifications or compliance conclusions**.

The compiler accepts a strict JSON manifest, verifies every declared local evidence artifact against its SHA-256 digest, applies an explicit evidence-currentness policy, and emits canonical JSON plus buyer-reviewable Markdown. It never fetches the network and never treats a model-generated statement as evidence.

## Status contract

Each question is exactly one of:

- `SUPPORTED` — every required evidence item exists, its local bytes match the declared SHA-256, and it is current at the manifest `as_of` time.
- `PARTIAL` — all required evidence IDs exist, but only some are current.
- `HOLD_MISSING_EVIDENCE` — at least one required evidence ID is absent from the manifest.
- `HOLD_STALE_EVIDENCE` — all referenced evidence is stale or future-dated at the manifest `as_of` time.
- `NOT_APPLICABLE` — the caller explicitly supplied an N/A reason and no evidence IDs.

A held question emits **no asserted answer**. A supported/partial answer contains only exact caller-supplied statements attached to current, hash-verified evidence IDs.

## Evidence contract

Evidence entries bind:

- stable evidence ID;
- bounded factual statement;
- retained source reference (`https://`, `repo://`, or synthetic `fixture://` in tests);
- clean relative local artifact path;
- lowercase SHA-256 of the exact artifact bytes;
- observed and valid-until UTC timestamps;
- declared scope.

Artifact paths are relative to an operator-supplied evidence root. Traversal, symlink components, missing/non-regular files, digest drift, oversized evidence, duplicate JSON keys, floats/non-finite JSON, duplicate IDs, and unknown critical keys fail closed.

## Demo

```bash
cd revenue/security_questionnaire_evidence_pack
python synthetic_fixture.py > /tmp/security-questionnaire-input.json
python questionnaire.py compile \
  --input /tmp/security-questionnaire-input.json \
  --evidence-root fixtures/evidence \
  --report-json /tmp/security-questionnaire-report.json \
  --report-md /tmp/security-questionnaire-report.md
python questionnaire.py verify \
  --input /tmp/security-questionnaire-input.json \
  --evidence-root fixtures/evidence \
  --report-json /tmp/security-questionnaire-report.json
```

The retained fixture deliberately produces one question in each status so buyer-review behavior is visible before any real evidence is introduced.

## Receipt and determinism

The report receipt binds the exact input bytes, normalized order-invariant manifest semantics, and canonical report body. Verification recompiles from the same manifest **and re-reads/re-hashes every evidence artifact**, so changing an evidence file after compilation makes verification fail.

Question/evidence ordering in the input does not change normalized semantics. Existing output paths are never overwritten by the CLI.

## Authority ceiling

This package has no authority to certify compliance, attest SOC 2/HIPAA status, contact a buyer, accept/sign a contract, authorize payment, or recognize revenue. Those booleans are explicit and hard-false in every report.

The commercial hypothesis is a **$15,000 fixed evidence-pack sprint** for one bounded questionnaire/evidence set, plus an optional **$2,000/quarter evidence refresh**. These terms are `PROPOSED_NOT_ACCEPTED`: they are not evidence of a buyer, sale, contract, payment, cash, or recognized revenue.
