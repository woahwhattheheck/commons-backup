# Acquired-Asset Quality-Master Cutover Gate

A dependency-free, read-only evidence compiler for a bounded non-production asset-integration pilot. It freezes a source/current generation and a target/cutover generation, compares synthetic or approved de-identified records, and emits deterministic `READY` / `HOLD` evidence with replayable hashes.

The tool never writes to production systems and never makes food-safety, quality, manufacturing-disposition, product-release, contract, payment, or revenue decisions.

## Record and custody model

Each snapshot binds:

- immutable snapshot ID;
- role (`SOURCE_CURRENT` or `TARGET_CUTOVER`);
- schema revision;
- release-generation ID;
- canonical UTC capture time;
- literal complete-export declaration;
- SHA-256 of normalized rows;
- exact normalized rows for offline replay.

A record key is the opaque tuple `item_id + batch_id + site_id`. Compared fields are `process_revision`, `quality_master_revision`, `inspection_evidence_sha256`, `disposition`, and `last_updated_utc`.

Record states:

- `READY` — exactly one source + one target record, semantic fields equal, timestamp equal, target age within policy.
- `MISSING_TARGET` — no target row exists for a source key.
- `CONFLICT` — a semantic field differs, or fresh source/target timestamps differ.
- `DUPLICATE_KEY` — source or target key is non-unique.
- `STALE_TARGET` — semantic fields match but target evidence age exceeds policy.

Precedence is fail-closed: duplicate → missing → semantic conflict → stale → timestamp conflict → ready. Target-only keys separately force `HOLD_FOR_RECONCILIATION`.

## Frozen synthetic acceptance

`synthetic_acceptance.py` generates exactly 2,000 de-identified source records:

| State | Count |
| --- | ---: |
| READY | 1,800 |
| MISSING_TARGET | 50 |
| CONFLICT | 60 |
| DUPLICATE_KEY | 40 |
| STALE_TARGET | 50 |

The suite proves deterministic three-run receipts, input-order invariance, replay verification, custody failure on generation/schema/digest drift, duplicate JSON-key rejection, non-finite JSON rejection, exact staleness boundary, future/timezone-alias rejection, target-only handling, receipt/snapshot tamper rejection, and create-exclusive/symlink-safe outputs under normal and optimized Python.

```bash
python -m unittest -v test_engine.py
python -O -m unittest -v test_engine.py
python synthetic_acceptance.py
```

## CLI

Production compilation samples current UTC internally:

```bash
python engine.py compile --input request.json --report report.json --markdown report.md
python engine.py verify --report report.json --markdown report.md
```

The request object contains exactly `source`, `target`, and `policy`. Output paths must not already exist; final-component symlinks are refused.

## Privacy and authority ceiling

Public fixtures contain no Del Monte, customer, product, facility, or production data. `READY_FOR_OWNER_REVIEW` means only that the supplied snapshots reconcile under the declared policy. It does not authorize food-safety or quality decisions, manufacturing disposition, production cutover, deployment, buyer contact, payment, cash, or revenue recognition.
