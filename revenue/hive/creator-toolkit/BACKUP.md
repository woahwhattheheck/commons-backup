# Back up and restore Creator Desk

In **Creator workspace**, select **Back up workspace**. The app returns a checked SQLite snapshot with the original resource files, links, member records, delivery references, consent history, queued/cancelled/recorded follow-ups, inquiries and retry records. It uses SQLite's online backup API, including committed WAL data, rather than copying an active database file.

**The snapshot contains personal data.** Keep it in existing private cloud storage. Do not attach a real workspace to a public issue, publish it in Git, or use it as a demonstration fixture. The shared-workspace operating model described in `README.md` also applies to this download.

## Restore into a new file

From this directory in the existing cloud environment:

```sh
python3 workspace_copy.py /private/cloud/creator-workspace.sqlite3 /private/cloud/restored-workspace.sqlite3
python3 app.py --db /private/cloud/restored-workspace.sqlite3 --port 8768
```

The paths are examples; choose actual existing cloud storage. No infrastructure is provisioned by these commands. The destination must not exist. Existing files, symlinks, and a destination created concurrently by another process are retained instead of replaced. The source database stays in place. A failed copy leaves no partially published destination.

The same command can create a backup directly from a running workspace. It validates SQLite integrity, required workspace columns, foreign-key relationships and each stored resource's SHA-256 before publishing the copy. The resulting JSON receipt contains file size, SHA-256 and per-table counts, not member addresses. This is copy/restore for the current Creator Desk schema, not a general database repair or schema-migration tool. Additive columns are preserved.

After restoration, the app remains usable with the same delivery/member references. A repeat resource request does not create another delivery, and cancelled drafts in the snapshot stay cancelled. Copying and restoring never send email or execute a recorded action. The application intentionally has no automatic mail sender.

## Capture time matters

A snapshot represents one consistent committed database state. Later source changes are not included. In particular, an opt-out recorded **after** the snapshot must be carried forward before any external follow-up. Restoring old consent records does not establish current consent. Coordinate a cutover using a fresh snapshot and do not operate two divergent copies as though they were one live workspace. Preserve the original until the destination has been checked and the current working path is chosen.

The download limit is 64 MiB. For a larger workspace, use the CLI with an explicit transfer limit, for example `--max-mib 256`; this does not alter the app's individual resource-upload limit. The copy tool uses a temporary file beside the destination and requires filesystem support for atomic same-filesystem hard links. It does not upload, delete, merge or overwrite any existing workspace.

## Executable checks

```sh
python3 -B -m unittest -v test_workspace_copy test_toolkit
```

The 18 new snapshot tests use actual SQLite/filesystem, committed WAL, concurrent writes, a real CLI subprocess and a real HTTP download. They cover every-table equality, original binary data, delivery reuse, stopped preferences, non-overwrite, broken relationships/hashes, transfer limits, and cleanup. Together with the 29 application tests, the executed suite is 47 methods. Test members and records are fictional.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
