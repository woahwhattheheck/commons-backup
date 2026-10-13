# Shop Operations Desk

A runnable local merchant workspace for Hive demand `bm-hive-20260908-032`.
Prepare source-linked catalog listings, allocate customer orders and creator
samples from the same stock, record shipment handoffs, inspect partial returns,
and export the resulting inventory and order records. Python standard library
only for the application; SQLite stores the work across restarts.

This is a working import/export operations desk, **not a connected TikTok Shop
app**. It does not publish a marketplace listing, send a creator/customer message,
ship a parcel, collect payment, issue a refund, or update remote stock. Those
operations remain in the merchant's existing tools. No merchant, provider
installation, actual order, or revenue is claimed by the supplied fixtures.

## Run

Requires Python 3.10 or later. From this directory:

```sh
python shop_ops.py --db ./workspace.sqlite3 serve
```

Open `http://127.0.0.1:8765`. The database is created if absent; restart with the
same `--db` path to continue the workspace. `--port` and `--host` are available
on `serve`. Anyone able to reach the server can read and change this workspace;
there is no login or merchant isolation. This is one merchant workspace, not a
hosted multi-tenant service. Keep real customer data out of public repositories.

The dashboard supports catalog import, product editing, receipts, multi-line
orders, sample allocations, cancellation, fulfillment, partial returns, listing
and inventory export, and a movement history. Product source links and copy are
operator-supplied. Unknown attributes stay explicit, rather than generated facts.
A ready/listed record requires description text and cleared uncertainty notes;
this is a completeness check, not independent verification of product claims.

## Complete a workflow

1. Add a product with its SKU, factual listing copy, merchant/specification source,
   price in minor currency units (for example, 2400 USD = $24.00), and listing
   record. `listed` means the operator recorded that state, not that an API
   confirmed a listing. Product SKUs are immutable; use Edit to change metadata.
2. Receive units against a delivery reference. Each `(reference, SKU)` is unique;
   separate actual deliveries need separate references. The same reference can
   cover multiple SKUs. Posted receipt records stay immutable. Use the physical-count
   workflow below to reconcile an observed stock difference; do not enter a duplicate
   receipt as a correction.
3. Reserve an order using a unique external order ID and one `SKU,quantity` per
   line. Choose Creator sample to allocate samples with the identical stock
   accounting. Recipient fields are references, not a messaging integration.
4. After physical handoff, enter the shipment/handoff reference and record
   fulfillment. Cancellation releases a reserved allocation. A fulfilled order
   cannot be cancelled in this desk; record returned units instead.
5. After inspecting a return, record its unique return-line ID, fulfilled order,
   SKU, quantity and explicit restock/non-restock outcome. Partial returns can
   be recorded separately. Use separate return-line IDs for separate SKUs.
6. Export inventory/listing CSV and order/line CSV for the merchant's existing
   workflow. These are this desk's schemas, not advertised as official TikTok
   import templates. A merchant-specific mapping and a real installation are
   the next integration work, not completed here.

The test example receives 10 units, fulfills four, restocks two returned units,
records one damaged return without restocking, and fulfills one creator sample.
The result is **seven on hand, zero reserved, seven available**, reconciled from
the actual movement rows. All names and source URLs in examples are fictitious.

## Catalog import and command API

A catalog file is a JSON array of metadata objects, or an object containing
`products`. New SKUs use `version: 0`; existing SKUs use the version exported in
`GET /api/state`. Import applies every row in one transaction or none. Duplicate
SKUs within one import are rejected. Stock fields in metadata imports are not
applied; receipt/reservation/fulfillment/return operations own quantities.

`sample_catalog.json` is an explicitly synthetic import suitable for trying the
UI on a new database. `example.invalid` links are placeholders, not live catalog
sources or endorsements.

Each mutation is `POST /api/command` with a JSON body:

```json
{
  "key": "merchant-receipt-20260908-001",
  "action": "receive",
  "data": {"sku": "BAG-01", "quantity": 10, "reference": "delivery-001"}
}
```

Supported commands and payloads:

| Action | Data |
| --- | --- |
| `product` | One product metadata object, including expected `version` |
| `catalog` | `products`: nonempty list of product metadata objects |
| `receive` | `sku`, positive integer `quantity`, unique receipt `reference` per SKU |
| `stocktake` | `sku`, observed `quantity` (zero allowed), current `version`, unique count `reference` per SKU, optional `note` |
| `stocktake_batch` | nonempty `counts` list of the same stocktake payloads, at most one per SKU |
| `order` | unique `id`, `kind` (`sale` or `sample`), `recipient_ref`, `lines` of `sku` and `quantity` |
| `fulfill` | order `id`, nonempty `shipment_ref` |
| `cancel` | reserved order `id` |
| `return` | unique return-line `id`, `order_id`, `sku`, `quantity`, explicit boolean `restock`, optional `note` |

Command keys are durable in SQLite. **Retry the identical key and payload after
an uncertain response.** It returns the original result even after a restart;
reusing a key with different data is a conflict. Successful receipt references,
order IDs and return IDs cannot be inserted again under a new key. Repeated
fulfill/cancel of an already-matching state does not move stock again. A later
fulfill under a new key still requires the exact nonempty `shipment_ref`; a
mismatch or blank reference is a conflict and does not mutate. The UI
keeps an uncertain request and its key in the current tab for exact retry; it
does not persist that pending browser request across tab closure. Use the state
view and the integration's retained request key to reconcile after closure.

For command-line operation, save one complete command object to a file:

```sh
python shop_ops.py --db ./workspace.sqlite3 apply command.json
python shop_ops.py --db ./workspace.sqlite3 export > operational-snapshot.json
```

`GET /export/{table}.csv` exports `products`, `orders`, `lines`, `returns`,
`return_lines`, `receipts`, `movements`, or `stocktakes`. CSV prefixes formula-like
text with an apostrophe for spreadsheet handoff; JSON retains raw strings. JSON snapshots
are operational exports, not full database backups: the idempotency table is
not included. For a full backup, stop the server and copy the SQLite database
with any remaining WAL/SHM sidecars as a unit, or use SQLite's online backup API.
Do not restore a JSON export expecting original retry history to be present.

## Reconcile physical inventory

The **Reconcile a physical stock count** form records observed on-hand units,
including reserved units that are still physically present. It does not record
available-to-sell units and it does not create a new receipt. Load the current
ledger, count the units, and submit the observed quantity with a unique count
reference and source/adjustment note. A count of zero is valid when no units are
reserved. The operation records the prior on-hand amount, expected version,
observed quantity and timestamp, and posts the exact difference to the existing
movement ledger. Even a matching count produces a zero-delta observation.

The count must use the current product version. A receipt, reservation,
fulfillment, prior count or metadata edit makes an older observation stale.
Refreshing the dashboard does **not** silently replace the version attached to
an in-progress count. Load the ledger and recheck the physical count before
trying again. Changing the SKU clears its loaded version.

A count below outstanding reserved units returns a conflict with **no inventory
or order change**. Resolve the affected allocations in the existing order
workflow first, then capture a fresh count. This version does not model negative
availability, backorders or an oversold state; it never cancels customer orders
silently to force a count through. Reconciliation is for observed quantities,
not a rewrite or deletion of original receipts, return records or orders.

For multi-SKU intake, save this command shape to a JSON file and use CLI `apply`
or send it to `/api/command`:

```json
{
  "key": "fixture-count-batch-001",
  "action": "stocktake_batch",
  "data": {
    "counts": [
      {"sku": "BAG-01", "version": 2, "quantity": 8,
       "reference": "fixture-count-001", "note": "Synthetic shelf count"}
    ]
  }
}
```

Replace the example version and quantity with the current ledger and observed
count; the example does not itself constitute a count. Every row is applied in
one transaction, or no rows are changed. Duplicate SKUs in a batch are rejected.
The same count reference can describe different SKUs in one counting session;
`(reference, SKU)` remains unique across successful counts. Retrying the original
command key and exact payload returns the original result without reapplying
an old count, even after later shipments or a restart. Use a new reference for
a genuinely new physical observation. `stocktakes.csv` exports the count history.

Existing workspaces gain only a new `stocktakes` table on startup; their original
rows, operation keys, reservations, price snapshots and history remain intact.
There is no marketplace feed, automatic stock detection or remote stock update.

## Accounting and concurrency

`available = on_hand - reserved`. Reservations increase reserved only;
fulfillment decreases both on-hand and reserved; cancellation decreases reserved
only; inspected restock increases on-hand. Non-restock returns are retained in
the return tables without entering sellable stock. Samples use the same rules.
Order lines retain the price/currency at reservation, not the latest catalog
price. No exchange conversion, tax, shipping charge, refund or payment ledger is
computed.

All mutations use `BEGIN IMMEDIATE`, foreign keys, inventory consistency checks,
and a durable operation/result table in the same transaction. Multi-SKU orders
and catalog imports roll back together. Product metadata updates require the
current version; stock movements also advance that version, so stale editors
must reload rather than replace fresh data. Snapshots read one transaction.
Quantities and minor-unit prices are integers from zero through 1,000,000,000;
receipt, order and return quantities must be positive. Observed stock counts may
be zero, and count adjustments may be positive, zero or negative. JSON bodies
are bounded to 2 MB. Network binding and SQLite storage remain operator choices.

## Initial delivery validation (PR10630)

```sh
PYTHONWARNINGS=error::ResourceWarning python -B -m unittest -v test_shop_ops
```

The initial delivery passed 27 methods on Python 3.13.5 in the provided cloud
container. These use real temporary SQLite files, threads, local HTTP requests
and CLI subprocesses, including 12 concurrent reservations for five units,
20 identical receipt retries, concurrent return caps, malformed data, partial
returns, import rollback, replay after restart, and ledger reconstruction.

An optional browser-control suite needs Playwright and installed Chromium:

```sh
CHROMIUM_PATH=/usr/bin/chromium python -B -m unittest -v test_browser
```

Eight methods passed against actual Chromium DOM and File objects with **explicit
fetch and UUID test adapters**. These exercise form typing, multi-line samples,
exact retry payloads, conflict handling, return inspection, literal text,
editing versions, mobile overflow, catalog files and fulfillment controls. The
suite skips when the optional browser dependencies are absent. Native Chromium
navigation to the running loopback server returned
`net::ERR_BLOCKED_BY_ADMINISTRATOR` in this environment; native browser-to-HTTP
end-to-end acceptance is **not** claimed. Separate real HTTP tests are green.

The browser suite found and covered the retry button's hidden-state styling;
`[hidden]` now retains priority over the general button display rule. No hosted
CI success, deployed site, remote integration or whole-repository test result is
claimed by these local results.

## Stock-count follow-through validation

```sh
PYTHONWARNINGS=error::ResourceWarning python -B -m unittest -v test_shop_ops test_stocktake
CHROMIUM_PATH=/usr/bin/chromium python -B -m unittest -v test_browser
```

The composed product passed **47 real SQLite/HTTP/CLI methods** (27 retained and
20 new stock-count methods) and **11 explicitly adapter-backed Chromium DOM
methods** (eight retained and three new controls). Ten concurrent counts with
one expected version accept exactly one; 24 identical retries share one result;
a count-versus-order race cannot erase a committed allocation. Multi-SKU failure
rolls back prior rows and audit changes. Additive schema-upgrade and post-shipment
replay tests preserve original data and operation history. Browser controls prove
that refresh does not silently rebase a stale observation and a changed SKU
clears its version. The same native-browser-network limitation described above
still applies; these results do not claim an external installation or full-suite
hosted acceptance.
## Native operator handoff

On 2026-10-03, a native Chromium 153.0.8010.0 session opened this desk through its actual Python HTTP server using a separate disposable SQLite database. The unchanged `sample_catalog.json` supplied fictional BAG-01. The operator imported it through the file input, received ten units, reserved and fulfilled a four-unit sale, recorded two restocked and one non-restocked returned unit, and reserved and fulfilled a one-unit creator sample. The ledger finished with seven on hand, zero reserved and seven available. Source description, ready state and 2400 USD minor-unit price stayed intact; the two order lines retained that price/currency.

The count form loaded the current ledger version and recorded seven with an explicit note that this was fictional quantity review, not an observed physical inventory. Its audit row retained the prior amount/version and the seventh movement recorded a zero adjustment. Two fulfilled allocations, their distinct fictional handoff references, two return records and three returned units persisted. No physical shipment, customer transaction, creator contact, refund or count occurred.

Seven actual CSV downloads covered products, orders, lines, stocktakes, movements, returns and return lines. The native JSON snapshot exactly matched the existing CLI export. Page reload and a real server stop/restart with the same database preserved the full snapshot. The 390-pixel mobile page remained 390 pixels wide and downloaded JSON bytes identical to desktop and after restart. No fetch, storage or UUID adapter was injected; browser execution recorded no page/console errors, failed HTTP responses or external requests.

Visual inspection exposed white inherited text on the white header reference panel. A scoped text color repairs that panel while preserving its links/content and the rest of the header. This acceptance continues the original ROWAN delivery and the subsequent shipment-reference repair without changing the backend, retained catalog or stock/retry contracts. Existing suites were not rerun or expanded, no dependency was installed, and the temporary browser/server were closed. JSON remains an operational export with the backup limits described above; this is not a connected marketplace or customer installation.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
