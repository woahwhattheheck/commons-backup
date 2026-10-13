# Run an offline laundry shift without writing Python

This operator entry point records one owner-supplied operation at a time in the
existing Commercial Laundry Route & Linen Custody Operations Desk. It does not
replace the engine, and the original `cli.py` remains read-only.

**Every example below is fictional. Invoice outputs are DRAFTS, not issued
invoices, receivables, customer acceptance, payment, or revenue.** The original
commercial hypothesis remains $4,500 setup plus $499/month,
`PROPOSED_NOT_ACCEPTED`. Neither the example nor use of this interface changes it.

## Start an operator-owned workspace

Run from this product directory with Python 3.11 or newer. Use a private data
directory that you own; do not put customer databases or real input files into
Git, public storage, or this demo channel.

```sh
mkdir laundry-work
python operate.py laundry-work/shift.sqlite3 init
```

Initialization is explicit and create-exclusive. Existing files, including
symlinks, are not overwritten. The parent must already exist. A storage failure
after exclusive creation may leave an empty or incomplete file; diagnose it
rather than deleting evidence or retrying under a different path blindly.

For a record operation, save a JSON object from the examples below in a UTF-8
file, then run:

```sh
python operate.py laundry-work/shift.sqlite3 customer --input customer.json
```

Piped input is also supported with `--input -`. Interactive terminal input is
refused so a mistyped command does not silently wait for a whole JSON document.
Paths with spaces must be quoted by the invoking shell. The program never
interprets the JSON as shell code or dynamically chooses a method from it.

## Create a fictional account and Monday route

Save each object in the named file. Use a different operation key for a different
operation; preserve that key when retrying the same intended record. Labels are
human-readable, while IDs use letters, digits, dots, underscores, colons, or
hyphens and must begin with a letter or digit.

### customer.json — `customer`

```json
{"operation_key":"sample.customer","customer_id":"sample-account","name":"FICTIONAL training account"}
```

### site.json — `site`

```json
{"operation_key":"sample.site","site_id":"sample-site","customer_id":"sample-account","name":"FICTIONAL linen room"}
```

### agreement.json — `agreement`

```json
{"operation_key":"sample.agreement","agreement_id":"sample-price","site_id":"sample-site","item_code":"towel","unit_price_cents":95,"active_from":"2026-01-01"}
```

Prices are integer cents, not decimal-dollar strings. Date ranges are inclusive;
`active_to` may be omitted or null. Overlapping price authority for the same
site/item is rejected by the existing engine.

### plan.json — `plan`

```json
{"operation_key":"sample.plan","plan_id":"sample-plan","site_id":"sample-site","route_code":"training","weekday":0,"stop_sequence":10,"active_from":"2026-01-01"}
```

Weekdays run from Monday `0` through Sunday `6`. Stop sequence identifies route
order; this records the operator's plan, not a navigation recommendation.

A site appears once per daily route. For the same route and weekday, plans may
not overlap in their inclusive date ranges when they use the same site or stop
sequence. Changing the sequence does not make a second visit to the same site
representable. A later nonoverlapping plan, another weekday, or another route
may still use that site. A rejected plan records no event and does not consume
its operation key. If older stored plans already repeat a site for a route/date,
manifesting reports that conflict before creating a route; inspect the retained
plans instead of retrying the same manifest under another operation key.

### manifest.json — `manifest`

```json
{"operation_key":"sample.manifest","service_date":"2026-09-21","route_code":"training"}
```

Execute the five files in order:

```sh
python operate.py laundry-work/shift.sqlite3 customer --input customer.json
python operate.py laundry-work/shift.sqlite3 site --input site.json
python operate.py laundry-work/shift.sqlite3 agreement --input agreement.json
python operate.py laundry-work/shift.sqlite3 plan --input plan.json
python operate.py laundry-work/shift.sqlite3 manifest --input manifest.json
```

Read the returned `result.route_id` and each `result.stops[].stop_id`. Use the
returned IDs; long component IDs may deliberately produce hashed IDs. For these
exact fictional inputs the stop is
`stop:2026-09-21:training:0010:sample-site`.

## Record pickup, plant counts, and delivery

### pickup.json — `pickup`

```json
{"operation_key":"sample.pickup","stop_id":"stop:2026-09-21:training:0010:sample-site","linen_counts":{"towel":3},"container_ids":["training-bag-1"]}
```

### process.json — `process`

```json
{"operation_key":"sample.process","stop_id":"stop:2026-09-21:training:0010:sample-site","processed_counts":{"towel":3},"damaged_counts":{"towel":0}}
```

### deliver.json — `deliver`

```json
{"operation_key":"sample.deliver","stop_id":"stop:2026-09-21:training:0010:sample-site","delivered_counts":{"towel":3},"container_ids":["training-bag-1"]}
```

```sh
python operate.py laundry-work/shift.sqlite3 pickup --input pickup.json
python operate.py laundry-work/shift.sqlite3 process --input process.json
python operate.py laundry-work/shift.sqlite3 deliver --input deliver.json
```

The engine records damage and count/custody mismatches as exceptions rather
than silently repairing numbers. A processed-good count plus damaged count
that differs from pickup is one mismatch. Delivering a different container can
produce both missing and unexpected custody exceptions. A container held by
another active stop cannot simply be reassigned by this interface.

## Resolve only what the operator can substantiate

Inspect `open_exception_ids` in processing/delivery receipts or the read-only
route snapshot. An unresolved exception blocks invoice drafting. Resolution
requires its exact ID, an operator-supplied code, a meaningful disposition note,
and a new operation key. The interface does not infer a resolution or auto-close
exceptions. This illustrative object uses a placeholder that must be replaced;
do not execute it without reviewing an actual exception.

```json
{"operation_key":"sample.resolve.1","exception_id":"REPLACE_WITH_RETURNED_EXCEPTION_ID","resolution_code":"OPERATOR_REVIEWED","note":"Replace with the supported operational disposition"}
```

```sh
python operate.py laundry-work/shift.sqlite3 resolve --input resolution.json
```

Recording a disposition is not sanitation certification or evidence of cleaning
quality. A clean fictional shift above needs no resolution step.

## Draft and hand off, without sending

### draft.json — `invoice-draft`

```json
{"operation_key":"sample.draft","stop_id":"stop:2026-09-21:training:0010:sample-site"}
```

```sh
python operate.py laundry-work/shift.sqlite3 invoice-draft --input draft.json
python cli.py laundry-work/shift.sqlite3 integrity
python cli.py laundry-work/shift.sqlite3 route-snapshot route:2026-09-21:training
python cli.py laundry-work/shift.sqlite3 export-route route:2026-09-21:training laundry-work/handoff
python cli.py laundry-work/shift.sqlite3 export-customer sample-account laundry-work/account-handoff
```

Three fictional towels at 95 cents produce a **285-cent DRAFT**. Route and
customer bundles contain JSON, CSV, and Markdown. Export reads the source
database without initializing it. Existing handoff files are not overwritten;
use a new intentionally selected directory for a later snapshot. Exporting a
bundle does not transmit it, post it into accounting, charge a customer, or
make it customer-authorized.

An ordinary export write or flush failure removes the files created by that
attempt, including the unfinished file, so the same destination can be retried
after resolving the storage problem. Existing files remain protected. A process
or machine interruption can still leave partial output; inspect it before retrying.

## Read receipts correctly

`APPLIED` means this operation appended its native event. `REPLAYED` means an
identical operation key/payload returned the stored original result without
another event. That historic receipt is not a fresh view of the route; use the
read-only snapshot for current state. Reusing a key with changed content returns
`IdempotencyConflict`. Repeating a terminal action with another key is not a
way to override a state conflict.

Operational errors return exit code `2` and one JSON diagnostic on stderr with
`status: REJECTED`. Successful operational receipts use stdout and exit code
`0`. Shell/argument-usage errors use argparse's ordinary usage diagnostic.
A failed invoice attempt does not consume its operation key, so the same
payload may be retried after actual exception resolution. Failure after an
external process interruption can have an uncertain local commit outcome:
retry the exact key and payload, then inspect integrity and current state.

Input is one JSON object, at most 1 MiB, 10,000 value nodes, and 32 levels deep.
Duplicate object keys, non-integer numeric syntax, non-finite numbers, boolean
quantities, unsupported fields, malformed text, and invalid native IDs/dates
are rejected. This is not a multi-operation transaction or batch importer.
Do not rename a damaged input until the problem is understood; source JSON is
never rewritten by the interface.

Only `init` creates a database. Record commands require an existing regular
file and a readable supported schema. The directory must be operator-owned:
this is not an access-control boundary against a hostile process replacing
paths, editing SQLite directly, or changing imported Python code. Keep backups
using a SQLite-aware backup procedure that accounts for WAL files; copying
only a live database file is not a backup guarantee made by this interface.

Original product/spec/commercial credit: Z-Sol-22. Recovery lineage:
Z-IronWeave, SCREE-Z and Z-HARBOR. Operator entry point and original guide:
ZZ-QUARTZ-S7D9, September 19, 2026. Production-only recovery and removal of
obsolete test instructions: yZ-Cairn-47, September 23, 2026.
