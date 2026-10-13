# Supplier reorder browser workspace

This browser desk consumes the existing `reorder_assistant.py`; it does not replace
or duplicate its purchasing calculations. The original CLI and examples remain
usable. Python 3.10 or newer and a browser are sufficient; the application has no
third-party Python or JavaScript runtime dependencies.

## Open the workspace

Run in a cloud workspace or a customer-controlled environment, keeping the database
outside the source/publication tree:

```sh
cd revenue/hive/supplier-reorder-assistant
python3 desk.py --db /path/to/private-workspace/reorder.sqlite3 --port 8086
```

Open `http://127.0.0.1:8086` in the same environment. The server listens on loopback
and serves this product, not the surrounding repository or database directory.
Its default database is `~/.commons-reorder/workspace.sqlite3`. Stop with Ctrl+C;
restart using the same database path to reopen saved plans. This is one shared
workspace, not a hosted multi-customer service. No external service is contacted.

## Complete a planning and receiving workflow

1. Upload UTF-8 stock, rules, and supplier catalog CSVs, or use the explicitly
   fictional example. All three inputs remain editable before saving. Existing
   engine column names are displayed beside the inputs. Choose the catalog's
   currency label and as-of date; currency labels do not perform conversions or
   independently validate prices.
2. Save a new draft plan. The engine calculates exact-item draft lines and separate
   alternative-review notes. A draft does not place an order, reserve inventory,
   update a supplier catalog, or send a message. Edit the inputs and save another
   independent plan to revise the proposal; the earlier plan is retained.
3. Open the intended saved plan and record goods actually received using receipt
   CSV. Each row supplies `receipt_id,received_at,supplier_id,supplier_sku,sku,quantity`.
   The supplier and SKU tuple must match the original saved draft. Reuse the same
   receipt ID only for the same received-goods row.
4. Download updated stock CSV, the complete current-plan JSON, or original submitted
   source CSV text. The JSON includes inputs, receipts, receipt-upload text, source
   hashes, and the calculated plan. Print the plan from its result panel. Historical
   revisions are available in the source/history drawer without changing the active
   receiving target.

The fictional example requests 9 filter units at 4.25, totaling 38.25 USD, and leaves
5 belt units unfilled with a separate fit-review suggestion. A 4-unit receipt changes
filter `on_hand` from 2 to 6 while imported `on_order` stays 3. A second 5-unit receipt
changes `on_hand` to 11. A cumulative quantity above the original draft's 9 units is
not applied. None of these operations sends or purchases anything.

## Receipt and source semantics

The saved input stock and calculated draft are immutable for a plan. Every receipt
change replays the entire distinct receipt ledger against that original stock,
exactly once. An identical existing receipt row is a no-op; a reused receipt ID with
changed values is a conflict. Quantities are checked cumulatively across uploads
and process restarts. Receipt IDs are scoped to a saved plan, not globally across
independent plans or external purchase orders. Do not record the same delivery in
multiple independent plans and treat their exports as one inventory ledger.

The `pipeline_includes_draft` checkbox is fixed when saving a plan. Normally leave
it off: generating a draft has not added anything to the imported `on_order` value.
Turn it on only when that imported stock already includes the draft's units in its
pipeline; the canonical engine then decreases `on_order` as receipts increase
`on_hand`. The engine's existing pipeline behavior is unchanged.

Source downloads preserve the exact UTF-8 text submitted to the server, including
BOM/CRLF when supplied through the API. A browser text editor may normalize an
uploaded file's line endings or BOM before submission; byte identity with the
pre-editor file is not promised. Malformed CSV widths, duplicate headings, missing
columns, invalid numeric data, non-Unicode text, and oversized inputs return a
message without reporting a successful save. Limits are 2 MiB per CSV, 20,000 rows
per CSV, and 8 MiB per JSON request.

Saving uses SQLite transactions, immutable revision records, and an expected
revision on receipt changes. A stale tab receives HTTP 409 rather than overwriting
newer work. Reopen the plan before retrying. Each write has an `operation_id`; an
identical retry returns the recorded response, while changed content with the same
ID returns 409. The browser reloads current state after a successful response so a
retried older success does not replace its view with an older revision. Browser
operation IDs survive retries in the current page, not a full page reload; inspect
the saved list before re-creating a plan after an ambiguous page interruption.

## HTTP interface

All write bodies are JSON and include a caller-generated `operation_id`.

- `GET /api/runs` lists saved plan metadata; `GET /api/runs/{id}` returns a plan.
- `POST /api/runs` takes `title` and `inputs` containing `stock`, `rules`, `catalog`
  CSV strings, `as_of`, optional `currency` (default USD), and optional
  `pipeline_includes_draft` (default false).
- `POST /api/runs/{id}/receipts` takes `expected_revision` and `csv`.
- `GET /api/runs/{id}/history` lists retained revision numbers;
  `GET /api/runs/{id}/history/{revision}` returns a snapshot.
- `GET /api/runs/{id}/source/{stock|rules|catalog}` returns submitted input text;
  `/api/runs/{id}/updated-stock.csv` and `/api/runs/{id}/export.json` return downloads.

CSV exports contain business text as supplied. Treat imported text as data in a
spreadsheet application. The desk does not add formula escaping that would change
source SKU/name values. Keep retailer data and database backups outside public Git.
To preserve the whole workspace, stop the server and copy its SQLite database;
the current-plan JSON is a useful export, not a complete multi-plan restore tool.

## Tests and current scope

```sh
PYTHONWARNINGS=error::ResourceWarning python3 -B -m unittest -v test_desk.py
python3 -m py_compile desk.py test_desk.py
```

The consumer tests exercise real temporary SQLite databases, restart persistence,
concurrent receipt writes, duplicate/cumulative receipts, historical snapshots,
source exports, and a real loopback HTTP server. An additional in-memory Chromium
DOM check exercised the exact UI and Store independently of browser networking.
The delivery record separates those results: direct Chromium localhost navigation
was blocked by the cloud environment, so native browser-to-server navigation and
native download completion are not claimed as tested there.

Next customer step: privately map one consenting retailer's stock/rule/catalog
exports to these column names and walk through a saved draft and actual delivery
receipt. This source delivery is not a customer acceptance, deployment, sale,
subscription, payment, or supplier integration.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
