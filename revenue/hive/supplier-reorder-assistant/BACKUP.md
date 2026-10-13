# Whole-workspace backup and restore

`workspace_backup.py` adds a complete database snapshot alongside the browser's
single-plan JSON export. It preserves all plans, historical revisions and write
operation receipts. It does not change the browser, database schema or reorder
engine, contact a provider, upload anything, or schedule future backups.

## Snapshot a running workspace

In the same cloud or customer-controlled environment as the existing database:

```sh
python3 workspace_backup.py snapshot \
  --db /path/to/private-workspace/reorder.sqlite3 \
  --out /path/to/private-backups/reorder-20260908.zip
```

The SQLite online backup API creates a consistent snapshot while the source can
remain open. It includes committed work in a write-ahead log; copying just the
live `.sqlite3` file is not the operation used here. The archive contains exactly
`workspace.sqlite3` and `manifest.json`. The manifest records database size,
SHA-256, creation time, SQLite version and counts of plans, revisions and retry
receipts. Default database size limit: 512 MiB. The online-copy progress callback
has a 30-second deadline; retry under lower write traffic when that limit is hit.
This is not a total archive creation deadline: integrity checking and compression
follow the online-copy phase.

No existing output is overwritten. Both snapshot and restore stage their complete
output in the destination directory, then publish it with a non-overwriting hard
link. The destination filesystem must support hard links within that directory;
an unsupported operation is reported instead of replacing an existing path.

## Restore into a new workspace

```sh
python3 workspace_backup.py restore \
  --archive /path/to/private-backups/reorder-20260908.zip \
  --db /path/to/private-workspace/restored.sqlite3
python3 desk.py --db /path/to/private-workspace/restored.sqlite3 --port 8086
```

Choose a new database path and an unused server port. The existing database remains
unchanged. The restore checks the archive shape, bounded size, database SHA-256,
SQLite integrity, required workspace columns and table counts before publishing.
It never extracts archive paths into the surrounding directory. Old plan IDs and
operation IDs survive, so an identical retried receipt does not add goods again.
The usual per-plan cumulative quantity limits still apply after restoration.

A successful command prints JSON; a handled error prints a message to stderr and
exits with status 2. `verified: true` means the archive checks above passed, not
that supplier deliveries, business values, or archive provenance were established.
The checksum detects changes relative to the included manifest; it is not a
signature, and someone changing both files can produce a matching checksum.
Backups contain the complete workspace in plain, unencrypted form. Keep the
archive and its storage private, outside public repositories. Restore trusted
workspace archives only. No customer database was used in the delivery tests.

## Executed validation

```sh
PYTHONWARNINGS=error::ResourceWarning python3 -B -m unittest -v test_workspace_backup.py
python3 -m py_compile workspace_backup.py test_workspace_backup.py
```

Cloud execution on 2026-09-08: **20 tests passed in 2.653 seconds**, plus compilation.
Tests use real SQLite files, a concurrent committing writer, retained WAL work,
CLI subprocesses and new restore targets. The round trip preserves original and
current plan revisions plus the operation cache; receipt4 before backup and
receipt5 after restore produce on_hand11 without double-applying receipt4.
Existing output preservation, archive/data mismatches, malformed metadata, size
limits, unrelated/corrupt databases and unusual source filenames are covered.
The source browser remains the exact PR10523 delivery; its prior 30 SQLite/HTTP
and 16 offline DOM results are not counted again as new backup tests.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
