# Localized Media Release & Variant Operations Desk

A local-first operations desk for teams that already possess source media and owner-supplied release authority, but need a deterministic way to manage localized variants, exact revision approvals, stale-parent invalidation, and a reproducible handoff package.

**Commercial hypothesis:** `$20,000 fixed` for one owner / up to 250 source titles and 2,500 locale/territory variants; optional `$1,000/month` support after delivery. These are **PROPOSED_NOT_ACCEPTED** terms, not revenue or buyer acceptance.

## What the product does

- binds every localized artifact to an exact SHA-256 source generation;
- records owner-declared required `(locale, territory, kind)` variants;
- records reviewer approval only against the exact current revision + content hash;
- invalidates release readiness automatically when source or localized bytes change;
- rejects replay/remint conflicts through durable request-id idempotency;
- serializes writes with SQLite `BEGIN IMMEDIATE` and survives reopen/retry;
- produces a deterministic ZIP containing `release.json`, `release.md`, and `receipt.json`;
- recomputes the package from current retained state for exact verification;
- creates exports with an exclusive, no-follow leaf under a retained parent-directory descriptor, refusing overwrite/symlink targets and attempting to truncate only its retained output descriptor on failure without unlinking a pathname.

## Database startup

The ordinary CLI distinguishes three cases. A missing database, or one with no user schema objects, is initialized in a single transaction: the five desk tables are created or the attempt is rolled back. An existing desk whose tables, columns, keys and constraints match the current desk is reopened and its schema is left untouched. Any other nonempty database, including one whose only object is a view or trigger, is refused. Refusal does not alter that file's schema or rows. Recognition uses the schema on the connection reserved for startup, not the pathname, so a concurrent replacement is not treated as solved by inspecting the path. The read-only review still opens an existing database itself and does not run this startup.

## Authority ceiling

This is working operations software, not a legal/rights/translation-quality diagnostic. It **does not** infer or interpret contracts, licenses, fair use, cultural suitability, or translation quality. `rights_ready` is an owner-supplied fact. `external_publish_authorized` is always `false` in the generated packet. The desk does not contact licensors/translators/customers, publish to platforms, mutate payment/accounting/provider systems, deploy externally, or spend money.

## Portfolio review

To review all titles, native holds, current approvals and retained events in one read-only browser report:

```bash
python -B review.py --db /operator/path/desk.sqlite3 --out /operator/path/new-review
```

Open `new-review/review.html` to search, filter, print and download complete JSON/CSV projections. The existing database is opened read-only and the output directory must be new. See [REVIEW.md](REVIEW.md) for launch instructions, snapshot limits and the difference between native projected rows and a raw database dump. This does not approve variants or authorize publication.

## Quick demo

All bundled demo media/text is fictional and self-authored. Choose a **new, non-existing workspace under an existing parent**. The demo refuses existing directories, files and symlinks before opening its database; it never deletes a previous package or reuses an existing database. On failure, inspect any newly created partial workspace and choose a new path for a retry. Existing product databases remain usable through the normal CLI and the read-only review; the demo is not their reset/retry command.

```bash
cd revenue/hive/localized-media-release-desk
python -B demo.py --workdir /tmp/localized-release-demo
python -B desk.py --db /tmp/localized-release-demo/localized-release.sqlite3 status --title-id demo-title
python -B desk.py --db /tmp/localized-release-demo/localized-release.sqlite3 verify --title-id demo-title --package /tmp/localized-release-demo/localized-release-demo.zip
```

A successful demo finishes at `READY_FOR_LOCAL_HANDOFF`; it does **not** authorize external publication. Repeating the demo command with the same directory returns a nonzero error instead of replacing artifacts.

## CLI workflow

Create a title from exact local source bytes and a strict JSON requirement list:

```bash
python desk.py --db desk.sqlite3 create-title \
  --request-id create-001 \
  --title-id campaign-master \
  --source ./master.mov \
  --required ./required.json
```

Record the owner-supplied rights-readiness fact:

```bash
python desk.py --db desk.sqlite3 set-rights-ready \
  --request-id rights-001 --title-id campaign-master --ready true
```

Add a required localized artifact. The result returns the exact revision and SHA-256 needed for approval:

```bash
python desk.py --db desk.sqlite3 add-variant \
  --request-id es-001 --title-id campaign-master \
  --locale es --territory US --kind subtitle --artifact ./es-US.srt
```

Approve only the exact current revision/hash:

```bash
python desk.py --db desk.sqlite3 approve \
  --request-id es-approve-001 --title-id campaign-master \
  --locale es --territory US --kind subtitle \
  --reviewer reviewer-es --revision 1 --sha256 <returned_sha256>
```

Inspect holds:

```bash
python desk.py --db desk.sqlite3 status --title-id campaign-master
```

Export only when every owner-declared variant is current + approved and `rights_ready=true`:

```bash
python desk.py --db desk.sqlite3 export \
  --title-id campaign-master --out ./campaign-master-release.zip
```

The export is create-exclusive: an existing file or symlink at that leaf is never replaced.

## Fail-closed semantics

Ordinary current operations own process UTC; there is no `--as-of` or caller clock override. A source mutation leaves existing variants bound to the old source generation, producing `STALE_SOURCE_BINDING` until each required variant is explicitly revised. A variant mutation increments its revision and immediately makes prior approvals stale. An approval must match the current title, variant key, revision, content SHA-256, and source generation. Request IDs are durable: exact retries return the first result; the same request ID with different semantics is rejected.
