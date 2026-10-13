# Migration Desk

Move a mapped CSV customer export into a working local customer-and-task desk, with its original attachments and relationships intact. Review a trial first, apply the exact plan once, then browse customers, update task status, download original files, and export the workspace from the browser.

This is the first runnable version of Hive demand `bm-hive-20260908-049`. Its defined destination is the included SQLite workspace. It does not connect to, export from, or write to a third-party CRM. An operator supplies that system's CSV export and attached files. No subscription, customer migration, sale, or external deployment is represented by the bundled example.

## Run the included workflow

The runtime uses only the Python standard library. It was executed on Python 3.13.5 with SQLite 3.46.1 in a cloud container. The `examples/` directory contains explicitly fictitious customers and a demonstration work order.

From this directory:

```sh
python migrate.py plan --source examples --mapping mapping.json --database work/crm.sqlite --operation demo-001 --output work/trial.json
python migrate.py apply --source examples --plan work/trial.json --database work/crm.sqlite --assets work/assets
python desk.py --database work/crm.sqlite --assets work/assets
```

Open `http://127.0.0.1:8080`. Select **Example Workshop** to see its linked task and original work order. Open the task, change its status, and save. **Export workspace** produces a ZIP of current customer/task/attachment records, exact attachment copies, and a hash manifest.

The trial does not create or modify the destination database. It produces five proposed creations: two customers, two linked tasks, and one attachment. Cutover performs real SQLite writes and copies the 165-byte demonstration attachment. A repeat of the exact apply operation returns its existing receipt instead of duplicating records.

The default listener is local to the machine running the desk. `--host` and `--port` can be supplied for an operator-managed environment. The bundled server is a small local workspace, not a managed public hosting service.

## Bring an export

Place UTF-8 CSV files and their attachments in one source directory. Copy `examples/mapping.json` and edit each destination-field-to-source-column mapping. Keep the namespace stable across updates: record identity is derived from **record kind + namespace + original external ID**, not a name or email. IDs such as `001` remain strings with their leading zeros.

| Dataset | Required mapped fields | Optional mapped fields |
| --- | --- | --- |
| customers | `external_id`, `name` | `email`, `phone` |
| tasks | `external_id`, `customer_external_id`, `title` | `status`, `due_date` |
| attachments | `external_id`, `customer_external_id`, `path` | `name` |

A dataset can be omitted from the mapping. Every task and attachment must resolve to an imported customer or a customer already present under the same namespace. Missing parents, repeated source IDs, repeated CSV headers, missing mapped columns, and unsupported field names produce actionable errors rather than partially populated records.

Task statuses are `open`, `in_progress`, `done`, and `cancelled`. Missing status columns default to `open`; a mapped but empty or unrecognized status requires source correction. Due dates are empty or exact `YYYY-MM-DD`. Translate source-specific statuses and dates explicitly before import. The importer does not guess their meaning.

Attachment paths are relative to the export directory. Ordinary files up to 64 MiB each are supported; symbolic links and parent-directory references are not source attachments. Original filenames remain display metadata; copied bytes use their SHA-256 content address. The original export is never rewritten or deleted.

## Canonical attachment reader integration

The attachment paths in both trial collection and cutover now consume LINDEN's existing `attachment_intake.read_attachment` component from Commons #10493. The integration preserves RELAY's canonical workspace from #10501 and passes its existing 64 MiB per-file limit explicitly. Mapping and CSV files continue to use the original `read_source` path.

When `O_NOFOLLOW`, `O_DIRECTORY`, `O_NONBLOCK` and descriptor-relative `os.open`/`os.stat` are available, the adapter reads the attachment bytes from opened directory/file descriptors and checks regular-file type, size and identity around the read. It rejects symlinks (including the supplied export root), non-regular files, source replacement/change, and nonportable or empty/dot/parent path components according to its existing contract. Export attachment paths must use ordinary relative POSIX names on this path.

A platform lacking those required APIs retains the original portable reader. That fallback keeps the existing bounded read and path checks but does not acquire the adapter's descriptor-relative or change-detection guarantees. An adapter rejection on a capable platform becomes `MigrationError`; it is never retried through the weaker fallback. A frozen source export is still required, and no protection against every concurrent or privileged writer is claimed.

Only attachment byte acquisition changes. The canonical intake still records the digest and byte length of the returned bytes in the trial. Cutover still compares the newly read bytes with that trial before using the existing content-addressed asset storage. Identity, duplicate decisions, relationships, revisions, journal entries and rollback remain unchanged. The adapter's separate `prepare_attachments` duplicate-coalescing API is not used, and its source is unchanged. The canonical destination remains its existing SQLite records plus asset files, not a new BLOB schema.

This continuation was checked by complete retained-source inspection, exact serialized patch reconstruction and independent blob identities. No Python, SQLite, filesystem migration, browser, test, backup or recovery drill was executed. The historical validation receipts elsewhere in this guide remain attributed to their original work and are not evidence that this integration ran. No customer data, external CRM/provider action, deployment, payment or commercial acceptance is involved.

## Duplicates and revisions

`duplicate_email: "error"` stops the trial when customer email addresses collide after trimming whitespace and case-folding. Correct the source or explicitly choose `"keep_separate"`; the trial records the affected IDs and retains distinct customer records. There is no implicit merge, fuzzy match, or attachment reassignment.

Review `changes`, `counts`, `duplicate_decisions`, `source_files`, and `cutover_steps` in the trial JSON. Each proposed row includes its original file/row, before-image, after-image, action, and revision. An update represents the mapped source record, including documented defaults for omitted optional fields; it is not a partial-field patch.

Use a new operation ID and output plan path for a new source revision. Applying a plan re-reads and compares the source export, checks current destination revisions, and validates all resulting relationships before committing. The same operation ID cannot be reused for a different plan. Local desk edits use the displayed revision, so an outdated form cannot overwrite a later save silently.

## Rollback and portability

To undo a completed import:

```sh
python migrate.py rollback --database work/crm.sqlite --operation demo-001
```

Rollback restores exact before-images only while the imported records still match the applied state. It stops without changing any records when a later edit would be overwritten or a later related task would be orphaned. An already-rolled-back operation can be inspected/retried, but applying again requires a newly generated plan with a new operation ID. Reconcile later work explicitly instead of discarding it.

SQLite record changes are atomic. Content-addressed attachment copies are retained after rollback, and a failed apply can leave an unreferenced copied blob. This preserves original material; automatic deletion or garbage collection is not part of this version.

A command-line export is also available:

```sh
python migrate.py export --database work/crm.sqlite --assets work/assets --output work/customer-export
```

Exports go into a new directory. Existing exports remain intact. The output contains `customers.json`, `tasks.json`, `attachments.json`, an `attachments/` blob directory, and `MANIFEST.json`. Record IDs and customer relationships are included. Keep the database and assets together when moving the working desk to another machine. Exports contain the operator's actual workspace data; the public source includes demonstration data only.

## Validation and next customer step

```sh
python -B -m unittest -v test_migration
```

The 27-method suite exercises real SQLite writes, source files, exact attachment copies, idempotent apply, duplicate decisions, stale plans/revisions, partial-copy failure, rollback, relationship preservation, and live local HTTP read/edit/download/export endpoints. `VALIDATION.json` records the executed environment and measured run; `TEST-OUTPUT.txt` is the actual final output.

The browser interface was additionally rendered and interacted with using substituted example API responses, including a 390-pixel mobile viewport. This is a separate DOM check, not a browser-to-server integration claim: the installed browser policy blocked direct local HTTP navigation. The actual HTTP backend is covered by the independent live-server test above.

The next customer step is to map one consenting customer's exported customer/task/file sample, review duplicate decisions, and run the trial against a fresh destination before cutover. A live source-system adapter or another destination requires a separate integration; no provider action is included here.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
