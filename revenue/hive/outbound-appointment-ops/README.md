# Outbound Appointment Operations Desk

A local, provider-independent operations desk for `bm-hive-20260908-028`.
It turns a customer-provided lawful prospect source into reviewable **UNSENT**
drafts, records inbound reply disposition, enforces durable opt-out suppression,
tracks local availability, and exports CRM/calendar handoff files.

It deliberately does **not** scrape prospects, send messages, mutate a CRM,
write to a calendar provider, or claim that a meeting happened. Those are
operator/provider boundaries outside this package.

## Runnable synthetic demo

From the repository root:

```sh
python -B revenue/hive/outbound-appointment-ops/desk.py \
  --db /tmp/outbound-demo.sqlite3 demo \
  --export /tmp/outbound-demo-export
```

The demo uses three fictional prospects. One records an interested reply and
becomes a local booking handoff; one opts out and remains suppressed after the
database is reopened. The export contains `handoff.json`, `crm.csv`, and one
`.ics` file that can be reviewed before any provider import.

## Core contract

- **Lawful-source boundary:** each prospect requires a `source_ref` plus an
  explicit `lawful_source_note`; the package does not discover contacts.
- **No transport:** generated drafts are stored with `state=UNSENT` and
  `transport=NONE`; there is no send command.
- **Suppression beats future work:** an `opt_out` reply suppresses the opaque
  `route_ref` durably. Future draft creation, booking, or re-introduction of
  that route fails closed, including after restart.
- **Reply-gated scheduling:** booking requires the latest recorded reply to be
  `interested` and an available local slot. Booking produces a local handoff,
  not a calendar API mutation.
- **Deterministic retry:** every mutating operation has an `operation_id`.
  Exact retries return the prior result; reusing an ID for different input is
  rejected.
- **Auditable handoff:** JSON/CSV exports retain source, relevance, reply, and
  booking state; ICS files contain only local event handoffs.

## Acceptance

```sh
python -B revenue/hive/outbound-appointment-ops/test_desk.py
# or
python -B -m unittest discover -s revenue/hive/outbound-appointment-ops -p 'test_*.py' -v
```

The suite uses real temporary SQLite files and CLI subprocesses. It covers an
interested reply → available-slot booking, restart persistence, global opt-out
suppression, suppression against reintroduction, duplicate booking rejection,
idempotent retries, export contents, and the absence of a live-send command.

## Customer pilot boundary

The source demand's final acceptance includes an authorized real pilot. This
package supplies the persistent operations workflow and provider-neutral
handoff. A real pilot still requires customer-authorized source data, message
transport, CRM/calendar credentials, and operator instructions; none are
invented or exercised here.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
