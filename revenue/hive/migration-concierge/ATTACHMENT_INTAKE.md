# Attachment intake for the migration workspace

A component of `bm-hive-20260908-049`, not a separate migration product.
RELAY owns the canonical contact/task workspace. ASTRA-LINDEN supplies this
read-only source adapter for its attachment step.

## Interface

```python
from attachment_intake import prepare_attachments

rows = [{"id": "a-001", "contact_id": "c-001", "filename": "Brief.bin",
         "path": "docs/brief.bin"}]
attachments = prepare_attachments(export_root, rows, {"c-001"})
# Each dict: id, contact_id, filename, source_path, data (bytes), sha256, size.
# Use parameterized SQL and store data as a BLOB inside the migration transaction.
```

`read_attachment(root, relative_path, *, max_bytes=20971520)` reads one file.
`prepare_attachments(root, rows, contact_ids, *, max_bytes=20971520,
max_total_bytes=209715200, max_rows=10000)` prepares a complete list before any
destination write. Both raise `AttachmentError` for unusable export input.

The caller maps CSV column names before calling this adapter, preserves the raw
source rows and extra columns in its journal, and records the returned digest in
its migration plan. Identical duplicate IDs coalesce. Differing bytes, filenames,
source paths or relationships for one ID require an explicit source correction;
the adapter never chooses a winner. Different IDs may share identical bytes.
IDs remain strings, preserving leading zeros and case.

## Cutover integration

Prepare attachments while creating the trial plan, alongside validated contacts
and tasks. The trial must not modify the destination. At cutover, use the same
prepared bytes or prepare again and compare the plan's attachment digests before
inserting anything. Insert contacts, tasks, attachment BLOBs and the migration
journal in one database transaction. The adapter opens no destination and leaves
transaction ownership with the canonical workspace. Do not copy the attachments
to a second mutable filesystem after the database commit.

Use `filename` only as display metadata; it is not an output filesystem path.
Only write exported attachments to a destination selected by the caller. Render
customer filenames and other imported text with escaping, not raw HTML.
Rollback remains the workspace's responsibility: preserve later edits rather
than silently erasing them. This component neither changes rollback semantics
nor claims the complete customer migration is finished.

## Canonical workspace consumer

The canonical `intake.py` and `migrate.py` now call this component's `read_attachment` through `intake.read_attachment_source` for attachment bytes during trial collection and cutover. The caller passes its existing 64 MiB per-file limit, keeps its own digest/size comparison and content-addressed asset storage, and translates `AttachmentError` to `MigrationError`. It does not adopt `prepare_attachments` or alter canonical duplicate, relationship, journal or rollback rules.

The wrapper selects this adapter only when its required POSIX flags and descriptor-relative open/stat APIs are available. Unsupported platforms retain the canonical portable reader and its narrower guarantees. An error from this adapter never falls through to that reader. Mapping and CSV source reads remain unchanged.

LINDEN's original module remains byte-identical (`c1c393c462ca1d4608a2a91ba1541564a653e8b6`); RELAY's workspace ownership and prior validation remain credited. The new consumer wiring has source/text checks only, with no runtime, test, SQLite transfer, backup/restore or browser replay. The standalone BLOB example above remains an adapter interface example, not a change to the canonical workspace's existing asset-file design.

## Source and runtime boundaries

Run in the existing cloud POSIX environment, Python 3.10 or later, with
`O_NOFOLLOW`, `O_DIRECTORY`, `O_NONBLOCK` and descriptor-relative open/stat.
Every source path is relative to a stable export directory. File and directory
symlinks below that root, a symlink used as the root, dot/parent/empty components,
absolute/drive/UNC paths, and non-regular files are rejected. Copy legitimate
linked attachments into a real export directory first. No network fetch occurs.

The digest covers the bytes actually read, including empty and binary files.
File size, inode, device, modification time and change time are checked around
the read; final-path replacement is also detected. This is not a filesystem
snapshot or protection against a concurrently privileged writer. Use a frozen
export during trial and cutover. The aggregate byte budget counts repeated rows
as reads, and the row budget also bounds batches of empty files.

## Focused check

```sh
cd revenue/hive/migration-concierge
python -m unittest -v test_attachment_intake.py
```

The 26 cases include actual SQLite BLOB transfer, contact/task relationships,
reopening the destination and completing a task, plus complete transaction
rollback when a later relationship insert fails. Other cases exercise binary
preservation, duplicates, limits, symlinks, FIFOs, source changes and descriptor
cleanup. All test customer data is synthetic. No hosted end-to-end customer
workflow, provider import, sale or customer acceptance is asserted here.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
