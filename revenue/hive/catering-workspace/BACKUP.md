# Back up and move saved catering events

The optional event service stores saved events in SQLite. Use the included online-backup command instead of copying a database file while saves are in progress. This command uses Python's standard library; no account, external storage service or additional package is needed.

From the catering workspace directory, choose a **new** private destination outside the browser asset tree:

```sh
python3 event_backup.py \
  --source ~/.hive-catering/event_store.sqlite3 \
  --destination /your/private/backups/catering-2026-09-08.sqlite3
```

The default source is `~/.hive-catering/event_store.sqlite3`, so `--source` can be omitted when using the service defaults. The command leaves the source and previous backups untouched. It returns the new copy's byte count, SHA-256, event/revision/retry-operation counts and SQLite quick-check result. It does not print event contents. Keep the backup private: it contains the same customer documents as the original.

The copy includes complete event documents, retained history and retry-operation identities. Concurrent saves are supported by SQLite's online backup API; the resulting copy is one consistent snapshot, not a promise to contain edits committed after that snapshot. A failed copy does not replace another file; only its own incomplete newly created destination is removed.

## Continue from a copy

Stop the old event service when performing a cutover, retain the original file, and start the same application against the backup:

```sh
python3 event_store.py --database /your/private/backups/catering-2026-09-08.sqlite3 --port 8080
```

Reopen the saved event in the workspace before editing it. Browser state can still point to a revision newer than an older backup. A stale save will produce a revision conflict rather than silently replacing the saved event. Export unsaved browser edits before reopening a different document.

The reopened copy becomes the active writable database. To keep an untouched archival copy, first create another new backup with `event_backup.py` and use that second copy for the active service. Future edits to one database do not synchronize to the other. Moving the private SQLite file between machines is an operator step, not something this tool uploads or performs on the owner's device.

## Executed coverage

```sh
PYTHONWARNINGS=error::ResourceWarning python3 -m unittest -v test_event_backup.py
python3 -m py_compile event_backup.py test_event_backup.py
```

Seven tests use real SQLite files and the real CLI. They cover history and retry identity preservation, continued work on a reopened copy, existing-file preservation, absent/unrelated/invalid sources and consistency while another connection commits saves in WAL mode. Tests use synthetic event records only. This is an operating feature of the same catering workspace, not a separate product or a hosted-backup claim.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
