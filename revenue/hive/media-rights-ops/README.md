# Content Rights & Usage-Window Operations Desk

Local-first operations software for agencies, brand teams, and media operators that need an exact answer to an operational question: **does this planned placement fit the authority facts the owner has supplied, and what currently needs renewal or retraction review?**

The desk stores immutable asset fingerprints and derivative lineage, normalized grant facts, exact placement requests, grant revocations, and an audit ledger. It evaluates channel / territory / time-window scope, records permitted placements idempotently, blocks changed replays, and produces expiry/renewal and retraction-review queues plus deterministic JSON, CSV, Markdown, and receipt hashes.

## Truth and authority boundary

This is **not** a copyright, contract, licensing, fair-use, or ownership determination engine. `READY_ON_SUPPLIED_AUTHORITY` means only that a requested placement fits the owner-normalized facts currently stored in the desk. It never infers rights, parses legal language, creates a grant, contacts a creator/licensor, uploads/publishes/removes media, logs in to a platform, or moves money.

Derivative lineage is provenance only, not authority inheritance. A grant authorizes only its exact `asset_id`; a grant on a parent/master does **not** authorize a child/derivative unless the owner supplies a separate grant fact for that exact child asset.

All production mutations are local SQLite writes through the CLI. The optional HTTP desk binds to loopback and is read-only with respect to state: it exposes snapshot/evaluation/queue reads, while HTTP `/api/place` and `/api/revoke` fail closed with `405`. Use CLI `place` / `revoke` for mutations.

## Commercial hypothesis

`$25,000 fixed / PROPOSED_NOT_ACCEPTED`: one entity, one normalized grant schema, up to 5,000 assets/versions and 20,000 grant/placement rows, target 10 business days after complete normalized intake. Optional `$1,500/month` operations support is a hypothesis only after a delivered fixed-scope implementation. No buyer acceptance, contract, payment, cash, or revenue is claimed here.

## Quick start

```bash
cd revenue/hive/media-rights-ops
python rights_ops.py import desk.sqlite3 example_manifest.json --at 2026-09-15T06:00:00Z
cat > intent.json <<'JSON'
{"asset_id":"cut-a-15s","channel":"instagram","territory":"US","starts_at":"2026-10-01T12:00:00Z","ends_at":"2026-10-15T12:00:00Z"}
JSON
python rights_ops.py evaluate desk.sqlite3 intent.json
python rights_ops.py queues desk.sqlite3 --as-of 2026-12-10T00:00:00Z --horizon-days 30
mkdir -m 700 bundle
python rights_ops.py export desk.sqlite3 bundle --as-of 2026-12-10T00:00:00Z
python rights_ops.py serve desk.sqlite3 --host 127.0.0.1 --port 8765
```

The desk page also accepts a bounded CSV (`asset_id,channel,territory,starts_at,ends_at`, at most 500 data rows). `POST /api/batch` with `{"csv":"..."}` evaluates every row on one read-only SQLite snapshot. READY, HOLD, and invalid rows all stay in the result; blank or malformed rows are numbered by their original starting CSV line and are not dropped or repaired. Quoted fields may span lines; following records retain their actual source line numbers rather than a parsed-record index. The page can filter that result and download the same rows as JSON or CSV. Batch review does not record a placement and does not invent a `request_id`. On narrow screens the snapshot digest wraps and the result table scrolls inside its labeled panel; focus “Batch review results” with Tab and use the horizontal arrow keys to reach all columns. Filters affect the visible table only: both downloads always retain every READY, HOLD and invalid row.

To record a placement, add a stable `request_id` to the intent and use CLI `place --at ...`. The same request and content replay without duplication; the same request ID with changed content fails closed. CLI `revoke <grant_id> --at ...` is immutable: a revocation can be replayed exactly but not silently rewritten. A recorded placement affected by revocation enters the retraction-review queue; the desk does not remove it from any provider.

Export publication consumes an **already-provisioned empty real directory**. The exporter does not create or remove that directory. It first fences whole-path substitution, then walks every absolute path component from the filesystem root through retained directory descriptors with `O_DIRECTORY|O_NOFOLLOW`, proving each observed component identity against the opened descriptor. This rejects symlinks in **any** ancestor component, not only a symlink in the final output name. Export leaves are then created descriptor-relatively with exclusive/no-follow creation.

Before success, the desk re-opens the caller-visible output path component-by-component, requires that final directory generation to match the retained generation, requires the retained directory to contain exactly the transaction-created filenames, and revalidates every created leaf identity. Leaf descriptors remain open until those checks finish.

Failure rollback is deliberately **fail-visible rather than pathname-destructive**. Portable Python/POSIX interfaces do not provide atomic "unlink this name only if it is still this inode" semantics; a `stat(name) -> unlink(name)` cleanup sequence can delete a foreign successor substituted between the calls. The desk therefore never pathname-unlinks transaction leaves during rollback. It truncates only through retained descriptors for inodes it actually created, then closes them. A failed export may consequently leave zero-byte transaction tombstones, while a foreign successor is preserved. The caller should discard that failed output directory and provision a fresh empty `0700` directory before retrying.

The logical export payload is also captured from one durable SQLite generation: the exporter holds SQLite's single-writer reservation while both snapshot and operational queues are read, so a placement or revocation cannot commit between those views and produce a package assembled from two database generations.

Secure publication requires a host with descriptor-relative `open`/`stat`, `O_DIRECTORY`, `O_NOFOLLOW`, `stat(..., follow_symlinks=False)`, and file-descriptor `listdir`; unsupported hosts fail closed instead of silently using a weaker path.

## Acceptance surface

The hostile suite covers exact-asset authority; parent-grant/child-derivative non-inheritance; HTTP mutation fail-closure with unchanged durable state; allowed placement; wrong channel and territory; future/expired/revoked grants; unlicensed/unknown assets; request replay mutation; HOLD-without-write; immutable revocation; renewal/expiry queues; concurrent duplicate placement -> exactly one durable row; restart behavior; deterministic exports; one-generation snapshot/queue capture under concurrent revocation; pre-provisioned empty-directory enforcement; final and ancestor symlink rejection; ordinary-directory substitution between observation/open; post-open pathname replacement/redirection; failure rollback preserving foreign successors without pathname unlink; foreign-entry injection preservation; duplicate-key, floating-point, non-finite, cyclic/missing-lineage, duplicate authority rows, and naive-time failures.

Run both ordinary and optimized modes:

```bash
python -m unittest -v test_rights_ops.py test_export_generation.py test_export_custody.py
python -O -m unittest -v test_rights_ops.py test_export_generation.py test_export_custody.py
python -m py_compile rights_model.py rights_store.py rights_export.py rights_http.py rights_ops.py test_rights_ops.py test_export_generation.py test_export_custody.py
```

Input JSON is bounded to 8 MiB, UTF-8 only, duplicate-key rejecting, floating-point/non-finite rejecting, exact-schema validated, and timestamps must be offset-aware. The caller owns output-directory provisioning and permissions; export files are requested as mode `0600` subject to the process umask.
