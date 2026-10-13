# Purchasing desk: browser workspace

A dependency-free browser consumer of the existing `purchasing_operator.py` matcher. Import and edit normalized vendor, PO and invoice CSVs, retain original documents, reconcile the rows, edit unsent follow-up drafts, and reopen any saved revision. Export a source-linked review ZIP or the canonical accounting CSV. The matcher and its existing examples are unchanged.

## Start

From `revenue/hive/purchasing-paperwork-operator`:

```bash
python3 desk.py
```

Open `http://127.0.0.1:8766/`. The default database is `~/.local/share/commons/purchasing-desk.sqlite3`, outside the source checkout. Use `--database /your/private/path/packets.sqlite3` or `--port 8767` to choose another location or port. Python's standard library is sufficient; no dependency install, API key, service account or external network connection is required.

This is a local, single-operator workspace, not a hosted multi-tenant service. Keep the server and database in a trusted private environment. All uploads, attachments, draft text and prior revisions remain in the database until the operator removes it. Stop the server before copying the database for backup or removing it. Removing an attachment in the editor affects the new revision only, not retained history. Do not commit databases or customer exports to the source repository.

## Complete the workflow

1. Choose **Load example**, or import three UTF-8 CSVs with the columns in `examples/`. CSV editors let the operator correct normalized rows; the tool does not extract text or interpret photos. Optional original documents are retained as opaque downloadable bytes.
2. Choose **Reconcile & save**. The existing sample produces three invoice lines: two matched review rows totaling USD 74.00 and one quantity exception. Nothing has been posted or sent.
3. Edit the follow-up subject/body and save a new revision. The draft is tied to its exact source hashes and issue content. Changing a source resets affected draft edits; earlier revisions remain viewable.
4. In the sample invoice CSV, change `Belt B,3,20.00` to `Belt B,2,20.00` and save. The new revision has three matched rows and no exception draft; the previous discrepancy is still available in history.
5. Download the selected saved revision's review ZIP. It contains `reconciliation.json`, `accounting_import.csv`, `exception_drafts.json`, exact source CSVs, optional original attachments and a filename/hash manifest. Original attachment filenames are metadata; archive paths are generated names with a simple original extension when present. The browser offers individual original downloads as well.

The accounting CSV is an unchanged raw interchange from the canonical matcher, not a spreadsheet-sanitized representation. Review imported text before opening it in spreadsheet software. Matching is exact per PO line; this UI does not add cumulative partial-invoice accounting, approval, payment or general-ledger posting semantics.

## Revisions and retries

Every successful save appends a revision. An update requires the revision the editor opened; simultaneous edits do not overwrite each other. A conflict keeps saved work intact and tells the operator to reopen the current revision. Historical views cannot be saved over the current head from the browser.

An optional stable `request_id` makes a create/update retry return the original accepted revision. Reusing that ID with different request bytes returns a conflict. The browser retains its request ID across an uncertain response while the input stays unchanged. Source inputs remain exact bytes; text edits intentionally create new UTF-8 bytes in a new revision.

Limits: three source CSVs, ten optional attachments, at most 2 MiB per file, at most 8 MiB decoded files per packet, and a 12 MiB HTTP request body. A rejected import/update creates no revision. No application logs contain document bodies or filenames.

## Local API

`GET /api/packets` lists saved packets. `GET /api/example` reads the existing fictional examples. `GET /api/packets/{id}?revision=1` reads one saved revision; omitting the query selects the current one. The returned object includes the selected revision, current revision, saved time, sources, attachments, report, accounting rows and drafts.

`POST /api/packets` creates a packet. `POST /api/packets/{id}` appends a revision. JSON input has `title`, `sources` keyed by `vendors`, `purchase_orders`, and `invoices`, optional `attachments`, optional `draft_edits`, and optional `request_id`. Each source/attachment has `{ "name": "filename.csv", "data": "base64 of original bytes" }`. Updates also require an integer `expected_revision`. `draft_edits` maps a returned draft's `basis_sha256` to `{ "subject": "...", "body": "..." }`.

Downloads are `GET /api/packets/{id}/bundle`, `/accounting.csv`, `/sources/{kind}`, or `/attachments/{zero_based_index}`, each accepting `?revision=...`. Attachments are downloads, never rendered or sent to another service. Input diagnostics use HTTP 422, revision/retry conflicts 409, missing packets/revisions 404, and request-size errors 413.

## Checks exercised

```bash
PYTHONWARNINGS=error::ResourceWarning python3 -B -m unittest -v test_desk.py
```

The consumer suite exercises the real matcher, SQLite reopen/history, original-byte hashes, source-linked ZIP/CSV, edited drafts and source-change reset, correction/reconciliation, concurrent update handling, idempotent retry, invalid input rollback, and real local HTTP routes.

A separate development check exercised the rendered HTML in system Chromium at desktop 1440×1080 and mobile 390×844. Because that cloud browser denies localhost navigation, it used an in-memory fetch binding to the real Store. The complete sample/edit/history/correction DOM workflow passed with no page errors or horizontal mobile overflow. HTTP behavior was tested separately; this is not a full browser-network end-to-end or hosted-deployment claim.

Hive demand: `bm-hive-20260908-040`. This addition ships a working local browser consumer. It does not claim a customer sale, document OCR, supplier message, accounting-system import, approval or payment.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
