# Inbound Lead-to-Booking Operator — Hive011

Dependency-free local Python/SQLite handoff for `bm-hive-20260908-011`. It accepts form/email-shaped inquiry records, binds each `source_ref` to one immutable normalized payload, routes configured service/area pairs, saves **reply drafts only**, reserves local availability slots transactionally, keeps follow-up reasons visible, and exports CRM-ready CSV.

It does **not** send email/SMS, mutate Google/Outlook calendars, scrape contacts, use customer data, or call a provider. The booking table is a local conflict-safe operator handoff.

## Run the synthetic demo

```bash
python -B -m unittest -v test_app.py
python app.py --db demo.sqlite3 --config demo_config.json intake demo_intake.json
python app.py --db demo.sqlite3 --config demo_config.json state
python app.py --db demo.sqlite3 --config demo_config.json crm
python app.py --db demo.sqlite3 --config demo_config.json serve --port 8098
```

HTTP endpoints are `POST /intake`, `POST /book`, `GET /state`, and `GET /crm.csv`. The server binds loopback by default.

## Dedupe, routing, and consent

`source_ref` is unique. An exact retry returns the existing result; changed content under the same source reference is rejected. Slot reservation uses `BEGIN IMMEDIATE`; a slot can have one lead and a lead can have one slot. Manual booking retries are idempotent.

Configured service/area pairs select a local calendar. Out-of-area inquiries become operator follow-ups. When `consent` is false, no reply draft or booking is created. With consent, an available requested slot becomes a local reservation plus a reviewable draft; an unavailable or missing slot returns route-local alternatives. Nothing is externally sent.

## Production handoff boundary

Before customer use, replace the fictional config with explicit service areas and availability, map the customer's approved intake fields to this schema, and connect any approved send/calendar actions through the customer's existing tools. Keep provider credentials and customer records out of Git.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
