# SQLite persistence for the existing Hive prospect workspace

This is a complementary backend for FIELDNOTE's
`revenue/hive_prospect_workspace/`, demand `bm-hive-20260908-029`. It serves that
existing customer interface and adds an explicit private-backup panel. It does
not replace the CRM, duplicate its company/contact model, or change its imports,
merges, notes, segments or exports.

## Run in the existing private environment

Python 3.10+; standard library only. From the Commons root:

```sh
python3 revenue/hive/prospect-workspace/server.py \
  --assets revenue/hive_prospect_workspace \
  --db /your/private/existing-directory/prospects.sqlite3 \
  --port 8766
```

Open `http://127.0.0.1:8766` in that environment's browser. The database parent
folder must exist. All builds and checks for this contribution run in a cloud
container, not the owner's PC. No new infrastructure is provisioned.

The supplied asset directory must contain the existing workspace's `index.html`
and referenced assets. The server preserves the existing model.js bytes and
adds only a backup iframe to the served HTML. It does not modify the source
files on disk. The panel is also available at `/persistence.html`.

## Use the same workspace's backup/restore workflow

Export a JSON backup from the existing workspace. Select it in **Private SQLite
backups**, then press **Save to SQLite**. Reopening the server with the same
`--db` preserves that exact JSON text. Download the saved backup and restore it
using the existing workspace's backup-import control.

These are explicit backups, **not automatic saving or live synchronization**.
The panel never reads or replaces browser storage. No contact data is copied to
a server until the operator selects a file and saves. Only one current server
backup is retained; replacing it is not a version-history product.

The snapshot service checks JSON syntax, an object root and a 2 MB UTF-8 bound.
It does not reinterpret the CRM schema. Use that workspace's own exported
backups and restore validation, not arbitrary JSON from another application.

Before each write, the client supplies the revision it read. SQLite transactions
reject a stale save or delete with HTTP 409 rather than replacing another write.
A stable operation ID makes a retry of the same bytes and base revision return
the prior receipt without applying the operation twice. Reusing an operation ID
for different content fails. A retried receipt describes its original operation
revision, which can be older than the current server revision.

After a connection error, **Retry pending operation** resends the same request.
After a revision conflict, download the latest backup, refresh the revision,
and explicitly choose what to save. The service never resolves conflicting
workspace snapshots by silently merging or choosing one.

## Privacy and deletion

The default listener is loopback. This is a single private-operator service, not
a public multi-tenant CRM: there is no account system or tenant separation. Do
not expose customer backups to the public Internet. Use an existing private
runtime and its appropriate operator access; no deployment is included.

**Delete server backup** removes the current payload and increments the
revision. It does not delete the existing browser workspace, downloaded files,
external backups, or historical filesystem copies. Operation receipts contain
hashes/revisions, not full prior payloads. This is logical deletion, not a claim
of forensic erasure. For a full database copy, stop the server before copying the
SQLite file; keep that copy private.

The server has no outbound API calls, analytics, scraping, enrichment credits,
messaging or payment behavior. Source includes no real customer records.

## API

`GET /api/state` returns `revision`, `payload` (exact JSON text or null), `sha256`
and `present`.

`POST /api/state`, content type `application/json`:

```json
{
  "payload": "{\"version\":1,\"companies\":[]}",
  "expected_revision": 0,
  "operation_id": "example-save-1"
}
```

`payload: null` deletes the current backup using the same revision/retry rules.
A successful response includes `status: saved` or `already_applied`, the
operation's `revision`, its payload hash, and whether that operation stored data.
Invalid inputs return 400, revision/operation conflicts 409, and storage errors
503. No payloads or query terms are printed to access logs.

## Validation

```sh
cd revenue/hive/prospect-workspace
python3 -B -m unittest -v test_server
python3 -m py_compile server.py test_server.py
node --check persistence.js
```

The focused suite uses real temporary SQLite databases, concurrent writers and
an actual HTTP server. It checks exact-byte reopening, stale-write preservation,
retry identity, deletion/recreation, concurrent saves and static consumer asset
composition. These are not the full Commons tests or a claim of hosted
installation. Native browser navigation in the authoring sandbox returned
`ERR_BLOCKED_BY_ADMINISTRATOR`; no native browser persistence pass is claimed.

License: Apache-2.0 under the Commons root license.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
