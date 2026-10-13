# Parts Sourcing Desk

A working, single-workshop browser workspace for Hive demand
`bm-hive-20260908-044`. Model/serial intake, source-linked catalog and alias search,
technician fit findings, editable order handoffs, manual external-order records,
revision history, SQLite persistence and downloadable backups are implemented.

The application does not contact suppliers, buy parts, send messages, infer
physical compatibility or claim current stock. References and observed dates
come from the shop's permitted catalog exports or manual entries. Every included
example is fictitious. This is runnable source, not a deployed subscription or a
record of a fulfilled customer sourcing request.

## Run

Python 3.11 or newer; runtime uses only the standard library. Keep `parts_desk.py`,
`supplier_enquiries.py` and `index.html` together, then run in the selected execution environment:

```sh
python3 parts_desk.py --db /path/to/workshop/desk.sqlite3 --port 8080
```

Open `http://127.0.0.1:8080` on that same machine. The server defaults to loopback
and the database is stored outside the source directory by default. Opening
`index.html` alone, or on static GitHub Pages, does not start its API. A loopback
address is not a customer-accessible hosted service. No dependency installation,
provider subscription or purchase is needed for the runtime. Stop with Ctrl+C;
restart with the same database path to reopen saved work.

For Commons work, use the provided cloud execution environment and preserve the
owner's device/storage boundary. This build and its tests ran in cloud, not on
the owner's PC. A hosted deployment is a separate unperformed operation.

## Complete a sourcing job

1. Save a unique workshop job reference with exact manufacturer, model, serial
   when available, requested part/description and quantity. A case-insensitive
   duplicate job reference returns the existing-record conflict, not a new job.
2. Enter a source-referenced catalog option or import a permitted CSV/JSON export.
   Search part number, explicit aliases, model, SKU, supplier or description.
   Attach useful results to the selected job. An alias match never implies fit.
3. Open **Technician fit review**. Record the finding, technician and source,
   measurement or serial details. Unknown or conflicting fit stays unreviewed,
   uncertain or incompatible. Resolve missing details with the technician or
   manufacturer outside the application; no supplier inquiry is sent here.
4. To clarify an option with a supplier, select **Include in supplier enquiry pack**
   on the saved options you want. Under **Supplier enquiry drafts**, choose the
   as-of date and source-age reminder, then **Download selected enquiries**. The ZIP
   contains one unsent text draft per selected supplier, an internal printable
   summary, JSON and its file manifest. Extract it and review each supplier's own
   text file before sharing; other suppliers' drafts and the combined summary
   stay internal. Downloading does not update the job or send anything.
5. Create a handoff, adjust quantity, unit price, shipping and notes, and download
   its text file. The file includes model/serial, supplier/SKU, source URL and date,
   fit finding, totals and unresolved warnings. Printing also produces a job
   summary. Drafting and downloading do not place an order.
6. After an actual order through an existing external supplier workflow, record
   its real confirmation reference. The local record becomes `placed`. The app
   neither verifies that external fact nor initiates the purchase. A cancelled
   draft may be replaced; recording cancellation of a placed order requires the
   supplier confirmation detail, and retains the original order/history.

The **Try the workflow** control loads explicitly fictitious catalog/job data.
The example with two units at 12.50 and shipping 4.00 has a 29.00 pre-tax total.
It is not an actual price, supplier quote, compatible part, stock claim or order.

## Consistency and limits

Every mutation is a SQLite transaction. Saved revisions detect stale edits;
reload before applying changes to a newer record. `operation_id` deduplicates an
unchanged retry, including a lost response after commit. Reusing an operation ID
with different data returns a conflict. Responses to unchanged retries are the
original snapshots, so reload for current state after recovery.

One active local order per job is enforced in the database, including concurrent
requests. This prevents duplicate handoffs within this workspace; it cannot
prevent someone ordering twice outside it, creating another job reference, or
using independent copied databases. Keep one active workspace for each shop's
ordering ledger. A backup is a recovery copy, not a second live ordering desk.

Options retain their source snapshots. Catalog edits or equipment-request
changes visibly stale prior fit findings instead of silently confirming them.
Refreshing an option resets its fit finding while the earlier review remains in
history. Recorded handoffs retain their historical amounts and source details;
current warnings identify later changes.

Prices and shipping use exact integer cents, at most two decimal places.
Blank/null is unknown, not zero. Missing price or shipping leaves the relevant
total unknown. No tax, foreign exchange, delivery guarantee or live inventory
calculation is performed. Currency is a recorded three-letter code, not an
exchange conversion. Supported imports contain 1–2000 rows; HTTP bodies are
limited to 2 MiB and the browser file input to 1.5 MB. This is a bounded workshop
desk, not a multi-tenant hosted platform or a background synchronization service.

## Catalog input

CSV uses one header row; JSON uses an array of objects. Required columns:
`id`, `supplier`, `supplier_sku`, `part_number`, `description`, `source_url`,
`checked_on`, `currency`.

Optional fields: `make`, `model`, `serial_scope`, `aliases`, `unit_price`,
`shipping`, `stock_status`, `stock_qty`, `lead_time`, `source_note`.

Use decimal strings for prices, `YYYY-MM-DD` for the actual observation date,
HTTP(S) source references without embedded credentials, and `unknown`, `in_stock`
or `out_of_stock` for the recorded stock state. JSON aliases are arrays; CSV
aliases use semicolons. Preserve leading zeros by treating identifiers as text.
Use `source_note` for the exact source page/section and its context. A source URL
is retained as a reference, never automatically fetched.

Matching catalog IDs update those entries and increment a version only when
normalized content changes. Validation is all-or-nothing; invalid input preserves
the previous catalog. The reusable provenance/preview addition by ASTRA-ROWAN
composes into this same product; see `CATALOG_FILES.md` when present. No second
catalog database or independent order workflow is introduced.

CLI import uses the same database transaction:

```sh
python3 parts_desk.py --db /path/to/workshop/desk.sqlite3 --import-catalog permitted-export.csv
```

## API for integrations

GET `/api/state`, `/api/catalog?q=...`, `/api/requests/{id}`, `/api/export`,
`/api/backup`, and `/api/orders/{id}/handoff.txt` return the saved state or downloads.

GET `/api/requests/{id}/enquiries.zip?option_id=...&as_of=YYYY-MM-DD&max_age_days=7`
downloads the existing supplier-enquiry pack for saved options. Repeat `option_id`
to choose several options; omitting it includes all saved options for that job,
matching the exporter CLI. The browser POSTs the same route with JSON
`{option_ids:[...],as_of:"YYYY-MM-DD",max_age_days:7}` so a large selection does not
depend on URL length. This read-only POST needs no `operation_id`; the browser
always sends the explicitly selected IDs.
The date defaults to the current UTC date; the reminder defaults to seven days.
Unknown selections or invalid export parameters return a JSON error with HTTP 400.
Saved fit state, source snapshots, revisions and existing-order notices come from
the existing exporter. These downloads do not write the workspace or contact suppliers.
See `SUPPLIER_ENQUIRIES.md` for the command-line and Python routes.

All POST requests use `application/json`; workspace mutations also use `operation_id`. Request/option writes
include the current request `revision`; order edits use the order's `revision`.

- `/api/requests` creates `{data:{job_ref,make,model,serial,part_number,description,quantity,notes}}`.
  `/api/requests/{id}` edits the same shape plus revision.
- `/api/catalog/import` accepts `{items:[row,...]}` or `{format:"csv",content:"..."}`.
- `/api/requests/{id}/options` attaches `{catalog_id,revision}`.
  `/api/options/{id}/review` takes `{fit,technician,note,revision}`;
  `/api/options/{id}/refresh` takes `{revision}`.
- `/api/requests/{id}/orders` creates `{option_id,revision}` with optional quantity,
  unit_price, shipping and notes. `/api/orders/{id}` edits those draft values.
  `/api/orders/{id}/placed` records `{supplier_reference,revision}`;
  `/api/orders/{id}/cancel` records `{note,supplier_confirmation,revision}`.

`Desk(path).mutate('catalog','',payload)` is the same catalog import operation.
`catalog_data(row)` is the canonical pure validator. The service is an open
single-workshop workspace; do not publish private workspace exports or databases.

## Backup and recovery

**Database backup** uses SQLite's online backup API, including committed WAL
content. Keep the downloaded SQLite file in the shop's chosen persistent storage.
To recover, preserve the original and open a separate copied backup:

```sh
python3 parts_desk.py --db /path/to/recovered/parts-desk.sqlite3 --port 8081
```

Check the saved jobs, source snapshots, orders and reference history before
continuing work from the recovered file. Do not overwrite a newer active database
with an older snapshot. **Export workspace** is a human/integration-readable JSON
snapshot; it is not the automatic restore format. Databases, exports, real customer
records and supplier files do not belong in the public source repository.

## Executed validation

```sh
PYTHONWARNINGS=error::ResourceWarning python3 -m unittest -v test_parts_desk test_ui_transport
python3 -m unittest -v test_ui_dom
```

The first command passed 40 tests in the provided cloud environment: 39 real
SQLite/transaction/restart/HTTP tests and one exact-UI-source test with 13 Node
assertions against the actual HTTP/SQLite service. It covers complete sourcing,
review, handoff, edits, manual reference/cancellation, atomic imports, backups,
concurrent order requests and unchanged retry recovery. Node 18+ is needed only
for the optional UI transport test, not for the application.

The optional Playwright/Chromium DOM test passed 18 rendering, form, conflict,
390px mobile and print assertions using **in-memory response fixtures only**.
Desktop and mobile screenshots were inspected. Native Chromium localhost
navigation in this environment returned `ERR_BLOCKED_BY_ADMINISTRATOR`; native
browser-network persistence and native download interactions were not validated.
The DOM test is not represented as an end-to-end browser-network test. Real HTTP,
download response bytes and database restart are tested separately.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
