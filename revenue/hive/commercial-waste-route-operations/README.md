# Commercial Waste Container Route & Service Exception Operations Desk

A local-first operations desk for regional commercial waste/container haulers that run recurring scheduled service across multiple customer sites.

**Commercial hypothesis:** $3,500 setup + $399/month. This is an offer hypothesis, not buyer acceptance or booked revenue. The software does not send outreach, dispatch vehicles, call providers, or mutate payments.

## What it does

- imports owner-authored customer → site → container → recurring plan data under a closed manifest grammar;
- retains one immutable workspace business-timezone policy and derives the current business date from the host clock rather than caller input;
- generates deterministic past, current, or future daily route plans from weekday schedules;
- prevents future planned stops from being asserted as serviced, skipped, or billable facts;
- tracks each elapsed stop as `PENDING`, `SERVICE_CONFIRMED`, `EXCEPTION_OPEN`, `RESOLVED_NO_CHARGE`, or `RESOLVED_BILLABLE`;
- requires billable makeup resolutions to carry an elapsed makeup-service date;
- requires skipped/blocked exceptions to be resolved before invoice drafting;
- rejects future-ended invoice periods even if rows were force-mutated outside the supported API;
- computes money only as SQLite-safe integer minor units;
- isolates invoice drafts by customer and period;
- transactionally binds every settled stop to at most one retained invoice draft, so overlapping or concurrent windows cannot duplicate a service charge;
- stores immutable invoice drafts, invoice-line custody rows, workspace settings, and event receipts;
- makes mutating commands idempotent by operation key: identical admitted structured input returns the prior result, while aliases or other changed input under a used key fail;
- survives process restart and serializes concurrent writers with `BEGIN IMMEDIATE`;
- backfills single-use invoice-line custody from legacy retained draft payloads and fails closed if legacy drafts overlap;
- exports deterministic JSON, CSV, and Markdown route views.

It intentionally does **not** choose routes, navigate vehicles, make compliance decisions, send messages, charge cards, or infer that a customer accepted the commercial offer.

## Quick proof

```bash
cd revenue/hive/commercial-waste-route-operations
python test_desk.py
python demo.py
python -m compileall -q .
```

The current hostile suite covers route/export determinism, exact admitted-payload replay binding, closed manifest grammar, cross-customer isolation, restart persistence, immutable evidence, concurrent stop races, missing-route and unresolved-state billing gates, future fact rejection, billable makeup-date authority, overlapping-period charge custody, concurrent invoice-claim racing, legacy custody backfill, and fail-closed legacy overlap detection.

The synthetic demo creates two customers / three sites, records one blocked-access exception, proves the unresolved invoice is blocked, resolves it as no-charge, and then produces separate ACME and BETA invoice drafts with three unique stop-custody rows.

## CLI

Initialize with retained business-time policy:

```bash
python desk.py --db ./desk.sqlite3 init \
  --manifest ./sample_manifest.json \
  --op-key manifest-2026-09-14
```

`business_timezone` may be:

- `SYSTEM_LOCAL` — use the host operating system's local timezone;
- `UTC` — use UTC without external timezone data;
- an installed IANA timezone such as `America/Kentucky/Louisville`.

The setting is stored once and is immutable. It is not accepted on service or invoice commands, so ordinary callers cannot select a favorable business date per request.

Inspect the trusted business date:

```bash
python desk.py --db ./desk.sqlite3 business-date
```

Generate a Monday route. Future route generation is allowed for planning:

```bash
python desk.py --db ./desk.sqlite3 route \
  --date 2026-09-14 \
  --op-key route-2026-09-14
```

Record service or an exception only after the route's service date has arrived under the retained business-time policy:

```bash
python desk.py --db ./desk.sqlite3 record \
  --stop-id 'stop:2026-09-14:PLAN-ACME-DOWNTOWN' \
  --outcome SERVICED \
  --op-key stop-acme-downtown-2026-09-14

python desk.py --db ./desk.sqlite3 record \
  --stop-id 'stop:2026-09-14:PLAN-ACME-MARKET' \
  --outcome SKIPPED \
  --exception-code BLOCKED_ACCESS \
  --op-key stop-acme-market-2026-09-14
```

Resolve an exception as no-charge:

```bash
python desk.py --db ./desk.sqlite3 resolve \
  --stop-id 'stop:2026-09-14:PLAN-ACME-MARKET' \
  --resolution NO_SERVICE_NO_CHARGE \
  --op-key resolve-acme-market-2026-09-14
```

A billable makeup requires a retained date that is not before the original route date and not after the trusted business date:

```bash
python desk.py --db ./desk.sqlite3 resolve \
  --stop-id 'stop:2026-09-14:PLAN-ACME-MARKET' \
  --resolution MAKEUP_COMPLETED_BILLABLE \
  --makeup-service-date 2026-09-15 \
  --op-key resolve-acme-market-billable-2026-09-15
```

Create an invoice **draft** only after every scheduled stop in the elapsed customer/period is present and settled:

```bash
python desk.py --db ./desk.sqlite3 invoice \
  --customer-id ACME \
  --period-start 2026-09-14 \
  --period-end 2026-09-14 \
  --op-key invoice-acme-2026-09-14
```

Each included stop is claimed transactionally by that retained draft. A later overlapping period that would reuse any claimed stop fails with `BillingBlocked`. There is no delete/revision API; replacing a draft requires an explicit future supersession design rather than silently re-billing its stops.

Export:

```bash
python desk.py --db ./desk.sqlite3 export-route --date 2026-09-14 --format json
python desk.py --db ./desk.sqlite3 export-route --date 2026-09-14 --format csv
python desk.py --db ./desk.sqlite3 export-route --date 2026-09-14 --format markdown
python desk.py --db ./desk.sqlite3 events
```

A one-customer synthetic manifest is included as `sample_manifest.json`.

## Manifest shape

```json
{
  "business_timezone": "SYSTEM_LOCAL",
  "customers": [
    {
      "id": "ACME",
      "name": "Acme Coffee Group",
      "currency": "USD",
      "sites": [
        {
          "id": "ACME-DOWNTOWN",
          "name": "Downtown Cafe",
          "containers": [
            {
              "id": "ACME-DOWNTOWN-8YD",
              "label": "Rear 8yd",
              "container_type": "front-load 8yd",
              "plans": [
                {
                  "id": "PLAN-ACME-DOWNTOWN",
                  "weekday": 0,
                  "service_code": "RECURRENT_PICKUP",
                  "price_minor": 12900
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

`weekday` is Python's weekday convention (`0` Monday … `6` Sunday). `price_minor` is a non-negative SQLite-safe integer such as cents for USD. The manifest grammar is closed at every object level: unknown fields are rejected rather than silently ignored. Operation-key replay is bound to the exact admitted structured payload before state normalization, so aliases such as `usd` versus `USD` or trimmed versus untrimmed text cannot reuse the same key.

## Existing database migration

Opening a pre-repair database performs a local schema migration:

1. adds `makeup_service_date` when absent;
2. creates retained workspace settings and defaults an already-initialized legacy workspace to `SYSTEM_LOCAL`;
3. creates immutable `invoice_lines` custody;
4. reconstructs each draft's stop claims from its retained `payload_json` under `BEGIN IMMEDIATE`.

Migration is fail-closed. Invalid payloads, missing stop references, mismatched custody, repeated stops, or two legacy drafts claiming the same stop raise `StateConflict`; the migration transaction rolls back rather than choosing a winner or deleting evidence.

## Operational invariants

1. **Planning is not fact authority.** A future route may exist, but its outcomes and billable resolutions cannot become terminal before the retained business date reaches the route date.
2. **No future-ended billing.** `period_end` must be on or before the trusted business date, even if the SQLite state was force-populated outside the supported API.
3. **No unresolved billing.** Any `PENDING` or `EXCEPTION_OPEN` stop for the customer and elapsed invoice period blocks the draft.
4. **No missing scheduled service.** Every active scheduled plan/date in the period must have a routed stop.
5. **One stop, one retained draft.** `invoice_lines.stop_id` is unique and claimed in the same writer transaction as the draft; overlap and races fail closed.
6. **Billable makeup is dated.** `MAKEUP_COMPLETED_BILLABLE` requires an elapsed makeup-service date no earlier than the original service date.
7. **No float or oversized money.** Plan prices and invoice totals are bounded integer minor units safe for SQLite.
8. **One operation key, one admitted input.** Exact structured-payload retry is stable; a changed admitted alias with the same key raises `OperationConflict`, and unknown manifest fields fail validation instead of normalizing away.
9. **Terminal-stop race safety.** The SQLite writer transaction checks current stop state before transition; concurrent terminal attempts yield one winner.
10. **Immutable retained evidence.** Workspace settings, invoice drafts, invoice-line custody rows, and event rows reject update/delete through SQLite triggers.
11. **No external side effects.** Provider calls, outreach, vehicle dispatch/navigation, and payment mutation are outside this product.

## Product boundary

This is operations software, not a hauling, routing, regulatory, safety, environmental, identity, or payment decision engine. Operators remain responsible for truthful real-world service facts, dispatch/navigation, applicable rules, and billing approval. The host clock and retained timezone policy provide chronological authority; they do not prove that an operator's past-dated service assertion is true. Invoice output is explicitly a **draft** and does not charge or send anything.
