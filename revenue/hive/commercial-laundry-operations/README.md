# Commercial Laundry Route & Linen Custody Operations Desk

An offline, standard-library-only SQLite desk for commercial laundry and linen operators serving recurring multi-site business accounts. Record a whole shift without writing Python using `operate.py`; inspect and export it with the separate read-only `cli.py`.

## Start here

Use Python 3.11 or newer. No package installation, network service, customer account, or payment integration is needed.

```sh
cd revenue/hive/commercial-laundry-operations
mkdir laundry-work
python operate.py laundry-work/shift.sqlite3 init
python operate.py --help
```

Follow [the operator guide](OPERATOR_GUIDE.md) for the complete customer, site, agreement, route, pickup, processing, delivery, exception-resolution and invoice-draft workflow. It includes copyable fictional JSON inputs and handoff commands. Keep real customer data outside this repository.

For a temporary, explicitly fictional two-account demonstration of the same engine:

```sh
python demo.py
```

This demonstration uses actual SQLite persistence and the product engine, not a replacement implementation. It shows a clean stop and a stop whose damage/count exceptions block invoice drafting until an explicit example resolution. The demonstration is not customer evidence, a deployment, or revenue.

## Browser console

Run `python web_console.py /path/to/desk.sqlite3` and open the printed private session URL for guided setup, all ten operations, route/exception views, retry recovery, and direct downloads. Follow [the browser operator guide](WEB_CONSOLE.md) for startup and connection-loss handling. The older `operator_console.py` command launches the same console; there is one shared implementation. No browser build or external service is required. For backup and restore through the existing CLI, see [BACKUP.md](BACKUP.md).

## What the desk records

- Customers, sites, dated service agreements and item prices in integer cents.
- Recurring service plans and deterministic daily route manifests.
- Pickup, processing, damage and delivery counts, with physical-container custody across active stops.
- Explicit count, damage and missing/unexpected-container exceptions; an operator must resolve them before an invoice can be drafted.
- Immutable event history, operation-key idempotency and transaction-serialized terminal actions.
- Exact-cent invoice **DRAFTS**, route/customer snapshots, and JSON/CSV/Markdown handoff bundles.

The stop lifecycle is:

`MANIFESTED -> PICKED_UP -> PROCESSED -> DELIVERED -> INVOICE_DRAFTED`

Processing compares pickup counts with processed-good plus damaged counts. Delivery reconciles both good-item quantities and the pickup/delivery container sets. Invoice drafting requires a delivered stop, no open exceptions, and exactly one applicable dated price for each delivered item.

An identical operation key and payload returns the stored original result without another event. Reusing a key with changed content raises `IdempotencyConflict`. A replay is not a current snapshot; inspect the route for its present state. Separate terminal actions are serialized with `BEGIN IMMEDIATE`.

## Inspection and exports

```sh
python cli.py /path/to/desk.sqlite3 integrity
python cli.py /path/to/desk.sqlite3 route-snapshot route:2026-09-21:training
python cli.py /path/to/desk.sqlite3 customer-snapshot sample-account
python cli.py /path/to/desk.sqlite3 export-route route:2026-09-21:training ./route-handoff
python cli.py /path/to/desk.sqlite3 export-customer sample-account ./account-handoff
```

`cli.py` opens an existing supported database read-only and never initializes one. Export commands create only the requested handoff files; existing files and symlink export directories are refused. Customer CSV neutralizes formula-leading labels, Markdown renders labels literally, and long identifiers produce bounded export filenames.

## Scope and commercial state

The desk records operator-supplied operational facts. It does not certify sanitation or cleaning quality, contact customers, call navigation providers, post invoices into accounting, charge funds, deploy a service, or assert revenue. Those eight authority flags remain false in product outputs. An invoice DRAFT is not an issued invoice, acceptance, receivable, payment, or cash.

The original offer hypothesis is **$4,500 setup plus $499/month**, explicitly **`PROPOSED_NOT_ACCEPTED`**. This source recovery does not establish customer acceptance, savings, revenue, or payment.

## Source lineage

Original product/specification: Z-Sol-22. Recovery lineage: Z-IronWeave, SCREE-Z and Z-HARBOR. Operator interface and guide: ZZ-QUARTZ-S7D9. Production-only integration: yZ-Cairn-47, September 23, 2026.

The original production-only recovery imported six executable source files unchanged from `61b90f87acb3ae59853e2095300f7ceeb676d8ed` (the prior #15843 carrier for #14558). There is one implementation class: `laundry_desk.py` and `laundry_desk_core.py` load the same retained engine. The internal `.py.disabled` filename is intentional; the core loads it explicitly.

This recovery does not import the old test files, validation/receipt documents, or shared workflow edits. Historical branches retain their provenance; this directory is the runnable product and its operator documentation.
