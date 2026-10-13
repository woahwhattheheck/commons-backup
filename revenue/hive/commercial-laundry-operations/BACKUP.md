# Back up and restore an offline laundry shift

Run these commands from the product directory with Python 3.11 or newer. Use
operator-owned data directories outside Git and public storage. Backups contain
the same customer and operational data as the source; they are not encrypted or
uploaded by this tool. These commands do not issue invoices or move money.

## Create a standalone backup

The destination parent must already exist, and the destination filename must be
new. Choose a meaningful new name for each snapshot:

```sh
mkdir -p laundry-work/backups
python cli.py laundry-work/shift.sqlite3 backup laundry-work/backups/shift-20260923.sqlite3
```

The command uses SQLite's online backup operation, rather than copying only the
main database file. Committed records still in a live write-ahead log are part
of the snapshot. Writers can continue using the source. The copy phase aborts
if it exceeds 60 seconds; a busy database can be retried after inspecting the
reported error. The backup represents its copy's consistent snapshot, not
changes committed after that snapshot.

Before publication, the staged copy is converted to standalone journal mode
and checked for SQLite integrity, foreign-key consistency, required laundry
tables, and the engine's operation/event integrity. The complete file is then
published with a create-exclusive hard link. Existing files, symlinks, and
SQLite sidecars at the requested destination are never overwritten.

Success prints `BACKED_UP`, the destination, its byte size, and native operation
and event counts. The snapshot does not append a business event to the source.
There are no additional manifest or receipt files.

## Restore to a new working database

Restore never edits a live database in place. Choose a new file whose parent
already exists, then supply one JSON object containing the backup path:

```sh
printf '%s\n' '{"backup":"laundry-work/backups/shift-20260923.sqlite3"}' |
  python operate.py laundry-work/restored.sqlite3 restore --input -
python cli.py laundry-work/restored.sqlite3 integrity
```

A UTF-8 input file may replace `--input -`. Restore does not take an operation
key: it copies the existing event history rather than creating another event.
Success prints `RESTORED` with the copied operation and event counts. Use the
normal operator commands against the restored file after inspecting it. The
original database and backup remain available and unchanged by the copy.

The restored file initially uses standalone journaling. A subsequent normal
record operation enables the engine's usual WAL mode. Do not transplant old
`-wal`, `-shm`, or `-journal` files onto a restored database.

## Failure and storage boundaries

Operational failures print `REJECTED` on stderr and exit 2; success exits 0.
Invalid, incomplete, or corrupt copies are not published as usable backups.
The filesystem must support hard links within the destination filesystem. No
fallback silently weakens no-overwrite publication. On POSIX systems the file
and destination directory are flushed; a durability failure after publication
explicitly tells you that the new file exists and must be inspected.

A crash can leave a private `.laundry-copy-*` staging directory. Preserve and
inspect interrupted work rather than deleting files blindly. Source database
paths and destination directories must be operator-controlled; this is not a
security boundary against another process replacing paths or modifying SQLite
files. A same-disk backup does not protect against disk loss. The tool performs
no off-device transfer, rotation, deletion, scheduling, or encryption.

API reference: Python's [SQLite backup documentation](https://docs.python.org/3.13/library/sqlite3.html#sqlite3.Connection.backup).
