# Fleetline — rental operations workspace

A runnable first version of Hive demand `bm-hive-20260908-036` for operators
who already own and manage a small car or equipment fleet. It is working
booking software, not a hosted rental marketplace or payment service.

## Run in the approved execution environment

Python 3.10 or later and its standard library are enough for the product.
Use the existing private cloud workspace; this delivery does not provision
infrastructure or require work on the owner's computer.

```sh
cd revenue/hive/rental-operations
python server.py --db /path/to/private/fleet.sqlite --port 8086
```

Open `http://127.0.0.1:8086` in that environment's browser. The service binds
only to loopback and serves its own page and JavaScript. The default database
is `~/.fleetline/fleet.sqlite`, outside the source directory. Keep the database
and exports private. This is a single-workspace desk, not a public multi-tenant
service. It contains no external integrations, telemetry, credentials,
automated messages, or payment processing.

## Complete operator workflow

Add each physical asset separately with an hourly or 24-hour rental rate, a
minimum number of charge units, an optional fixed booking fee, and an optional
refundable security deposit. Enter a customer booking or maintenance hold,
check availability, and save. The date-filtered schedule shows current status,
pricing snapshot and revision. Edit reserved records, cancel them to release
availability, record partial and completed handover/return checklists, generate
a current customer-message draft, print the schedule, and export the workspace
including its audit history. Drafts are never sent by this app.

For customer bookings, Fleetline makes the commercial calculation explicit:

`amount due = rental subtotal + booking fee + refundable security deposit`

A synthetic $75.25/day asset with a $10 booking fee and $200 refundable deposit
quotes $285.25 due for exactly 24 hours. The rental subtotal remains $75.25;
those components are stored separately as integer cents. Taxes, delivery and
other unconfigured charges are not included. Fleetline does not record whether
an amount was paid, and the quote is not a legal rental agreement.

## Pricing snapshots and migration

* Existing bookings keep the rate, minimum, booking fee and refundable deposit
  from the moment they were first reserved. Rescheduling recalculates duration
  against that snapshot; later asset-price edits affect only new bookings.
* Maintenance holds carry zero rental subtotal, fee, deposit and amount due.
* Existing v1 SQLite workspaces are migrated in place on open by creating two
  additive sidecar tables for asset terms and reservation snapshots. The original
  asset/reservation column order is untouched, so older raw fixtures and binaries
  can ignore v2 terms. Rows without a sidecar record read as zero fee/deposit and
  use the existing rental total as amount due.
* API clients that update an existing asset without sending the new fee/deposit
  fields preserve the asset's current values rather than silently resetting
  them. New assets default both optional terms to zero.

## Scheduling and data behavior

* Each asset has capacity one. Booking and maintenance intervals use the same
  atomic SQLite overlap check. End times are exclusive, so adjacent intervals
  are allowed. A maintenance hold cannot silently displace a booking.
* Concurrent writers cannot reserve the same interval twice. Record revisions
  prevent stale edits from overwriting a newer value. Repeated API requests
  with the same operation ID and exact command return the original result;
  reusing that ID with changed content returns a conflict. The browser retains
  an unchanged retry ID while its page remains open. After an ambiguous result
  or page reload, refresh the schedule before entering a replacement request.
* A completed handover requires the checklist items and allows only one physical
  handover per asset at a time. Return it before handing it over on another
  booking. A returned booking keeps its original reserved interval and pricing
  snapshot; an overdue physical return does not automatically extend the
  calendar interval. Review actual handover state before promising pickup.
* Times are stored as UTC microseconds. API times need an explicit offset or
  `Z`, with no more than six fractional digits. The editor uses the browser's
  device timezone and the schedule displays the offset. Nonexistent local
  clock-change times are rejected. Unchanged editor times preserve the original
  timestamp, including fractional precision.
* Complete JSON exports contain assets, reservations, operation results and an
  append-only audit history. The export remains `fleetline-export-v1` for
  backward compatibility and now carries the extra commercial-term columns.
  It is a portable data record, not a one-click restore feature. Back up the
  SQLite file using SQLite's backup facility before replacing a live workspace.

## API

`GET /api/state` returns current records. `GET /api/availability?start=...&end=...`
returns per-asset availability plus `rental_subtotal`, `booking_fee`,
`security_deposit` and `amount_due`. `GET /api/message?id=...` creates an unsent
draft with the booking's pricing snapshot, and `GET /api/export` downloads the
workspace.

`POST /api/command`, with `Content-Type: application/json`, accepts:

```json
{"operation_id":"your-stable-request-id","command":{"action":"save_asset","id":null,"expected_revision":0,"name":"Example lift","unit":"day","rate":"75.25","minimum_units":1,"booking_fee":"10.00","security_deposit":"200.00","notes":"Synthetic example"}}
```

Other command actions are `save_reservation`, `cancel`, and `checklist`.
Reads never change the database. Writes, their audit event and retry result
commit in one transaction. Malformed or conflicting commands leave existing
rows unchanged.

## Executed checks

Core historical regression commands remain:

```sh
PYTHONWARNINGS=error::ResourceWarning python -m unittest -v test_fleet.py
node --check app.js
# Optional development check with Playwright + Chromium:
python test_browser.py
```

Commercial-term regressions add:

```sh
PYTHONWARNINGS=error::ResourceWarning python -m unittest -v test_commercial_terms.py
PYTHONWARNINGS=error::ResourceWarning python -O -m unittest -v test_commercial_terms.py
python test_commercial_browser.py
```

The focused unit suite covers exact component arithmetic, immutable commercial
snapshots across reschedules, legacy-shaped asset updates, maintenance zero
charges, availability output, customer drafts, fail-closed money validation,
in-place v1 migration, positional-SQL compatibility, and SQLite backup preservation. It passes in normal and optimized Python.
The focused browser exercise covers asset term entry, availability, booking,
asset price changes without retroactive quote mutation, message draft and JSON
export using the real HTTP server and SQLite. In this cloud run native local
navigation was blocked, so the browser test used the repository's documented
embedded DOM with real-HTTP fetch bridge; native origin/CSP/network loading is
therefore not claimed by that focused check.

Only fictitious customer data is used by tests. No customer, sale, payment,
hosted availability, live rental booking or outbound delivery is claimed.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
