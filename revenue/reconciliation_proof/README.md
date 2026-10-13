# Reconciliation Proof

A buyer-neutral, dependency-free Python evidence engine for work where two nonproduction record sets must be reconciled before a human decides whether migration, publication, acceptance, or any other real-world step is appropriate.

It is intentionally reusable across parity proofs, screening/provenance proofs, merger/collision proofs, imports, staged migrations, and source-of-truth comparisons. It does **not** embed a prospect name, provider, schema, or production connector.

## Contract

`proof.py` accepts a small reconciliation spec plus `left` and `right` record arrays. Each record carries:

- opaque `record_id` (never emitted in clear in the receipt),
- positive integer `version`,
- canonical whole-second UTC `observed_at`,
- bounded JSON `fields`, and
- a SHA-256 evidence pointer.

The engine validates strict JSON, rejects duplicate keys/non-finite values/symlinked files/oversized inputs/future evidence, collapses exact same-version retries, quarantines changed same-version payloads, detects version-time regression, selects the highest version per record, and compares required/ignored fields plus optional version/evidence identity.

Every input record digest is bound into `input_manifest_sha256`, including historical versions, exact retries, and conflicting variants. Input ordering does not change the result. Output record identifiers are SHA-256 digests; this is pseudonymization, not an anonymity guarantee for low-entropy IDs.

The only clean status is `RECONCILED_FOR_HUMAN_REVIEW`. Any missing record, field/version/evidence mismatch, or conflict yields `HOLD`. The receipt structurally keeps all external authority false:

- buyer acceptance
- production release
- data migration
- external transmission
- payment
- recognized revenue

`verify_receipt()` revalidates receipt schema, cardinalities (including conflicting input rows), row uniqueness, outcome counts, authority, status, and checksum without needing the source records.

## CLI

```bash
python -m revenue.reconciliation_proof.proof \
  --spec spec.json --left left.json --right right.json \
  --as-of 2026-09-13T09:15:00Z > receipt.json

python -m revenue.reconciliation_proof.proof --verify-receipt receipt.json
```

Exit status is `0` for a fully reconciled proof, `3` for a valid `HOLD`, and `2` for invalid input/receipt.

## Acceptance battery

```bash
python -m unittest -v revenue.reconciliation_proof.test_proof
python -O -m unittest -v revenue.reconciliation_proof.test_proof
python -m revenue.reconciliation_proof.acceptance --require-pass
python -O -m revenue.reconciliation_proof.acceptance --require-pass
python -m py_compile revenue/reconciliation_proof/*.py
```

The synthetic acceptance fixture covers 300 record keys: 240 clean matches and six deliberate 10-record hold families (field mismatch, missing-left, missing-right, version mismatch, evidence mismatch, changed same-version conflict), plus five exact retry duplicates per side. Passing the acceptance checker means the engine detected the expected hostiles; it does not authorize a production action.

## Boundary

This package has no network client, buyer data, provider credentials, production read/write connector, migration executor, submission/transmission path, payment action, acceptance authority, or revenue-recognition authority. A buyer-specific delivery can map its controlled exports into this contract and retain the produced receipt as bounded evidence for human review.
