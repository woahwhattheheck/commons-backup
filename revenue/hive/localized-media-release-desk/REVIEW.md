# Read-only localized-media portfolio review

Review every title in an existing Localized Media Release Desk without editing the database or assembling individual JSON commands. The reader reuses `ReleaseDesk.status()`; it does not contain a second rights, revision, approval or readiness engine.

## Run the review

Use Python 3.10 or newer, with only the standard library and the adjacent `desk.py`.

```sh
cd revenue/hive/localized-media-release-desk
python -B review.py --db /operator/path/localized-release.sqlite3 --out /operator/path/review-2026-09-23
```

The database must already exist. The output directory must **not** exist, and its parent must exist. The command prints the generated `review.html` path. Open that file in a browser; there is no server, upload service, network dependency or account connection.

Search titles, required variant keys, reviewer names, source hashes, event detail and native hold reasons. Select On hold or Ready for local handoff, expand the visible titles, and inspect exact revision approvals and source-parent bindings. Print current view expands the visible detail panels for printing. Search and status filters affect only what is displayed: **all downloads retain the entire native portfolio projection**, not just matching titles.

The existing fictional demo can supply an example database. Its `--workdir` must be a new, non-existing directory under an existing parent; an existing workspace is refused without deleting its package or opening its database. A failed new demo workspace remains for inspection. The review itself never invokes the demo or initializes a database, and can read a previously created product/demo database without rebuilding it.

## Six local outputs

- `review.html`: portable searchable review, with the other five files embedded as download links. It remains usable when copied alone.
- `portfolio.json`: all native title projections, their source identities, required variants, current approvals, holds and event histories, plus the snapshot acquisition interval and bounded database row counts.
- `titles.csv`: one row per title, source identity, owner-supplied rights flag, native release status, dates and complete hold list.
- `variants.csv`: one row per required slot, including missing variants; absent revision/hash/name/parent-current fields stay blank rather than becoming zero or false.
- `approvals.csv`: one row per current-revision approval returned by the native projector.
- `events.csv`: one row per retained title event; its full detail remains JSON in the final column.

CSV values that could start spreadsheet formulas are prefixed with an apostrophe; nothing is evaluated. Use `portfolio.json` for the unmodified values. Integers are serialized by Python and are not round-tripped through JavaScript. Header-only CSVs are valid when there are no corresponding rows.

The export is the **native status projection**, not a raw backup or exhaustive database dump. In particular, approvals from old revisions and variant records not present in the title's required list are not included by `status()`. Database row counts refer to underlying snapshot tables and can therefore differ from projected CSV row counts. The database itself and its request-id history are not packaged.

## Read and output behavior

The source connection uses SQLite `mode=ro` and `query_only`; it does not call the desk constructor or execute schema initialization. SQLite's online backup copies one consistent database generation into a private in-memory database. Every native title projection reads that same copy. The reader preserves the source database's configured journal mode; SQLite may still require its normal read locks and WAL/shared-memory coordination files.

The in-memory connection is also query-only. A borrowed-connection adapter preserves the native per-title BEGIN/COMMIT lifecycle and rolls back failed reads before the next operation. The adapter exposes no command to approve variants, change rights, create titles, export a release package, or send anything externally.

The snapshot represents one point within the reported acquisition interval. It is not a perpetual readiness grant or proof of external authority. A live writer may change the original desk afterward; reopening the report cannot detect that. Re-run into a new output directory to obtain a new view, and use the existing desk's current-state workflow before a later handoff.

No partial title selection is silently passed off as a complete portfolio. The operation stops before output if the source lacks the existing desk's required tables/columns, snapshot acquisition fails, a native title projection fails, or a bound is exceeded. Current bounds are 128 MiB of SQLite pages; 2,500 titles; 25,000 stored variants and required slots; 100,000 approval rows; 100,000 event rows; and 16 MiB of generated native JSON. Snapshot backup has a 30-second progress deadline, separate from SQLite's bounded busy timeout. Large/inconsistent databases are not truncated into apparently complete reports.

Files are generated before creating a new output directory. Existing output files/directories/symlinks are refused, and each new file is opened exclusively. A disk/write failure can leave a partial new output directory; the command reports failure and leaves it for inspection rather than deleting paths or pretending the export completed. Choose a new directory for a retry. Directory/file modes request 0700/0600 where supported by the host; an operator must still protect the copied reports because they include complete retained media metadata and event details.

## Authority and delivery

`READY_FOR_LOCAL_HANDOFF` is the unchanged desk status, not a legal rights opinion, translation-quality judgment, client acceptance or external publication authorization. `external_publish_authorized` remains false. No source media is uploaded, translated, published, approved or released by this reader, and no payment/provider action occurs.

Original product: Z-Sol (#14685/#14688). Existing export repair: #14692. Read-snapshot repair: Z-Harbor (#14718). Ingestion repair: Z-Meridian-Q7L9 (#15985). Portfolio reader: yZ-Tern-7V6 / GPT-6 Astra Pro. Existing commercial hypotheses remain proposed and unaccepted.

This delivery adds no tests, fixtures, dependency or workflow. It is source delivery; this seat did not execute the application or claim browser, hosted or customer acceptance.
