# Migration Desk recovery

This is a recovery companion to the existing Migration Desk, not another migration
engine. Keep `workspace_backup.py` beside the existing `intake.py` and `migrate.py`.
It uses Python's standard library and the canonical workspace validation.

## Back up a working desk

From `revenue/hive/migration-concierge/`:

```sh
python3 workspace_backup.py backup --database /private/desk.sqlite3 --assets /private/assets --output /private/desk-recovery-01.zip
python3 workspace_backup.py verify /private/desk-recovery-01.zip
```

Use a NEW output filename each time. The database can be in use: SQLite's online
backup API includes committed WAL writes while excluding uncommitted changes.
It may retry while writers are active, with a 60-second snapshot deadline. The
snapshot does not pause or modify the application's records. Do not delete or
rewrite content-addressed asset files while backing up; a missing or mismatched
version makes the operation fail without publishing an incomplete archive.

The ZIP includes the complete SQLite snapshot (records, import runs, plans,
reports, and before/after rollback journal), all distinct attachment content
addresses referenced by current records OR historical change images, and a
SHA-256/byte-count manifest. Unrelated asset-directory files are excluded.

The existing `migrate.py export` remains the current-record data handoff. It is not
replaced: recovery additionally preserves the operation history and old attachment
versions required to roll back an attachment replacement after restoration.

## Restore without replacing the original

```sh
python3 workspace_backup.py restore /private/desk-recovery-01.zip /private/recovered-desk
python3 desk.py --database /private/recovered-desk/workspace.sqlite3 --assets /private/recovered-desk/assets --port 8080
```

The recovery directory must not already exist. Verification completes in private
staging before that directory is reserved. Successful output contains
`workspace.sqlite3`, `assets/`, and `MANIFEST.json`; the CLI prints `restored: true`
and exits 0. Point the existing desk at those paths; it remains the only record,
edit, and rollback implementation. The original database and assets are retained.

A recovered workspace keeps the same record IDs, revisions, relationships, import
operation IDs, retry behavior and rollback journal. To retry an original import,
retain its ORIGINAL source CSV export, mapping, and plan separately: the recovery
archive does not reconstruct the source export. Rollback itself uses the restored
journal. Later edits still make the canonical rollback refuse to overwrite work.

## Failure and privacy boundaries

The archive is **private and unencrypted**, and may include personal data from old
record versions as well as current records. On POSIX, a published backup is mode
0600 and the restored directory is mode 0700. Keep backups in a private location;
the SHA-256 manifest detects corruption, not malicious replacement or provenance.
Only restore archives obtained from a trusted source. Neither backup nor restore
contacts a CRM, sends a message, changes provider accounts, or publishes files.

All declared members, hashes, sizes, required tables, SQLite integrity, current
relationships and historical attachment coverage are checked. Files are streamed
to controlled names; arbitrary archive paths, extra/duplicate members and invalid
metadata are rejected. Format limits: 2 GiB aggregate uncompressed payload,
100,000 distinct attachment versions, and a 4 MiB manifest. No members are silently
skipped when a limit is exceeded.

Archive publication uses an exclusive same-filesystem hard link. A filesystem
without hard-link support causes an error, not an overwrite fallback. Existing
archive paths (including dangling links) are never replaced. Concurrent backup
writers and restores have one successful destination claimant.

Restore is **not a crash-atomic multi-file operation**. A copy failure leaves the
new directory with `.RESTORE_INCOMPLETE`; do not open that partial workspace. Keep
the original and retry restoration into another NEW directory. The marker is
removed only after every file has been copied and fsynced. There is no claim of
power-loss durability for directory metadata. The tool never deletes a failed
restore directory or overwrites an existing destination. Failure exits 2 with
`completed: false`; inspect the error instead of treating a partial directory as
success.

## Executed checks

```sh
PYTHONWARNINGS=error::ResourceWarning python3 -B -m unittest -v test_workspace_backup.py
```

The first Linux cloud-container run passed 21/21 methods in 2.665 seconds, with no
skips. These are new real SQLite/filesystem/concurrency/CLI integration tests
against the unchanged canonical core, not a repeat of the original product's
27-test panel. They exercise restored edits, retry and rollback, historical
attachment rollback plus the actual export API, live WAL, corruption/coverage
failures, private permissions, and interrupted-copy markers. No native browser,
Windows, hosted-CI, real customer migration, or revenue result is claimed.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
