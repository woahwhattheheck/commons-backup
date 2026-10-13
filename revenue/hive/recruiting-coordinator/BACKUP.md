# Recruiting Coordinator: portable backup and recovery

`workspace_backup.py` is a dependency-free Python 3.11+ command-line companion.
It preserves the entire SQLite workspace, including schema, records, revisions,
calendar data and retry history **when those values are stored in the database**.
It does not change the coordinator, its scheduling decisions or its browser UI.
External files, environment settings and application source are not included.

## Create and inspect a private snapshot

Use the database path configured for the running coordinator. The following
paths are examples, not a claim about the application's default database name.
Create the destination directories first.

```sh
python3 workspace_backup.py backup /private/recruiting.sqlite3 /private/backups/recruiting-20260908.zip
python3 workspace_backup.py verify /private/backups/recruiting-20260908.zip
```

The coordinator may keep running. SQLite's online backup API captures a
consistent committed state, including committed data still in the WAL. It does
not promise the state at command entry or include later commits. An open,
uncommitted transaction is not copied. The original database is opened read-only;
only the temporary snapshot is converted to a self-contained DELETE-journal file.
Do not substitute a raw copy of a live `.sqlite3` file.

The ZIP contains exactly `workspace.sqlite3` and `manifest.json`. The manifest
records SHA-256, byte length, schema digest, table row counts, SQLite user/application
versions and snapshot timestamps, but not record contents or the source path.
The ZIP itself is **not encrypted** and contains the complete database, potentially
including deleted-record remnants. Keep it in the owner's private storage, not
GitHub, Slack, a public website or a public downloads directory. Hashes detect
accidental changes; they do not prove an archive came from a trusted sender.
Only restore your own trusted backups.

## Restore without replacing current work

```sh
python3 workspace_backup.py restore /private/backups/recruiting-20260908.zip /private/recruiting-recovered.sqlite3
```

The destination must be a new path with an existing parent directory. The command
refuses an existing database, symlink, or existing `-wal`, `-shm` or `-journal`
sidecar at that name. It validates the archive, digest, SQLite quick check,
foreign-key consistency, schema and row counts before publishing the restored
file. A concurrent operation cannot overwrite the winner. A failed validation
leaves no destination database. Temporary working copies are removed.

Keep the original workspace. Start a separate coordinator instance using its
existing database option and the recovered path; consult `coordinator.py --help`
for that option. Inspect the restored records and continue work there only after
choosing which copy is the working workspace. **Do not run two divergent copies
as the same live recruiting workspace.** This tool does not reconcile later edits
or restore email/calendar-provider state. A previously sent invitation is not
unsent, resent or cancelled by restoring a database.

Archive and restored-database files are created with private mode `0600` on
POSIX. The destination filesystem must support hard links: publishing uses a
same-filesystem temporary file plus no-overwrite link, rather than an overwrite
rename. Parent directories are never created automatically.

## Limits and results

Commands write structured JSON to stdout on success and JSON errors to stderr
with exit code 2 on operational failure. They do not print candidate records.
Default database size limit is 256 MiB; manifest limit is 64 KiB. Set
`--max-bytes 536870912` on each command to use a larger explicit limit. Snapshot
creation has a 30-second timeout (`--timeout 60` changes it); a busy or continually
changing source can time out without producing an archive. SQLite validation and
ZIP work are synchronous, not background monitoring. Free disk must accommodate
the snapshot plus compressed archive during backup and a full copy during verify.

Python API:

```python
from workspace_backup import create_backup, verify_backup, restore_backup
receipt = create_backup("recruiting.sqlite3", "backups/snapshot.zip")
manifest = verify_backup("backups/snapshot.zip")
restored = restore_backup("backups/snapshot.zip", "recruiting-recovered.sqlite3")
```

## Executed validation

```sh
PYTHONWARNINGS=error::ResourceWarning python3 -B -m unittest -v test_workspace_backup.py
```

24 focused tests passed in the provided cloud VM (Python 3.13.5). Coverage uses
real SQLite databases, filesystem operations and CLI subprocesses, including
committed and uncommitted WAL writes, concurrent transactional writes, binary
history and operation rows, restored-copy edits, damaged archives, stale sidecars,
size limits, private file modes and 16 concurrent restore attempts with one winner.
All records are synthetic. These tests validate the backup mechanism, not the
application's scheduling semantics. The app-specific booking/reschedule reopen
check awaits the canonical coordinator source and is not claimed by this delivery.

Implementation references:

- SQLite online backup: https://www.sqlite.org/backup.html
- SQLite backup transaction/locking contract: https://www.sqlite.org/c3ref/backup_finish.html
- Python `Connection.backup`: https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
