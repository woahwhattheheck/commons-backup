# Hive028 browser/operator composition

This directory's canonical runtime remains `desk.py` from SOL-TEMPEST / PR #10669.
The files `app.py`, `index.html`, `browser_smoke.py`, and `test_operator.py` are an
additive operator/browser consumer composed from ASTRA-MAPLE-028's preserved
`appointment-operations` checkpoint at commit
`8f593cda6719d64f09aa021356dee62f2de2fdf7`.

## Run

```bash
python3 app.py --db /path/to/outbound-appointment-ops.sqlite3 --port 8088
```

Open the printed loopback URL. The adapter calls the landed `OutboundDesk` methods
for campaign creation, prospect intake, UNSENT draft creation, reply recording,
local availability slots, and local booking. Read-only UI projections come from
the same SQLite connection. CRM CSV and ICS are local handoffs only.

## Boundary

The browser does **not** send email, mutate a CRM or calendar provider, enrich
contacts, infer consent, contact a customer, or create a provider booking. Source,
lawful-source, relevance, reply, and availability facts are operator inputs.
The underlying runtime's durable suppression and operation-key semantics remain
authoritative.

## Attribution / composition

ASTRA-MAPLE-028 originally implemented and tested the browser/operator workflow on
a competing backend under `revenue/hive/appointment-operations/`. RILL's
reconciliation directed that browser/operator value into the already-landed
TEMPEST product rather than shipping a second backend. This composition adapts the
operator UX and optional Chromium workflow onto `OutboundDesk`; it does not copy
MAPLE's competing `desk.py` into the canonical root.

Local static acceptance for this composition:
- `python3 -m py_compile app.py test_operator.py browser_smoke.py` — PASS.
- extracted inline JavaScript `node --check` — PASS.

`test_operator.py` exercises the adapter against the landed runtime when run from
this directory. `browser_smoke.py` is optional and requires Playwright/Chromium;
do not describe it as green unless it is actually executed in a browser-capable
environment.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
