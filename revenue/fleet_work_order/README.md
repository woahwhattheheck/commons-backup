# Fleet work order — exactly once

One bounded workflow for fleet and logistics maintenance teams:

`inspection/fault event -> exactly one work order -> exactly one escalation -> closeout receipt`

## Commercial ladder

- **$199 / one business day:** field contract, synthetic replay fixtures, exception taxonomy, run receipt, and a written fit verdict for one workflow.
- **$2,500 proof:** only after the diagnostic finds a fit; adapt the tested contract to one buyer-approved sandbox.

The diagnostic does not dispatch a technician, approve spend, pay an invoice, or connect to production. No credentials or private fleet data are required.

## Exact buyer intake

1. Fleet size and vehicle classes.
2. Current inspection/fault event source.
3. Current work-order destination.
4. The observed duplicate, retry, or worker-restart failure.
5. One redacted sample event, optional.

Buyer: fleet/logistics maintenance director or equivalent operating owner with authority over the work-order workflow.

## Binary acceptance

Run the same source event twice and crash the worker once after prepare and once after effect persistence. Each run must converge to:

- one work order;
- one escalation;
- one committed receipt;
- zero duplicate external effects;
- an explicit conflict when the same event id arrives with different bytes.

An incomplete synthetic event can roll back its provisional effects and leaves a `ROLLED_BACK` receipt. A committed work order is never silently erased.

## Public implementation

- [`fleet-work-order.html`](../../fleet-work-order.html) — no-login working demo and buyer intake.
- [`fleet-work-order.js`](../../fleet-work-order.js) — standalone crash/replay engine with browser local-storage and in-memory adapters.
- [`test_fleet_work_order.js`](../../test_fleet_work_order.js) — executable acceptance battery.
- [`receipt.json`](./receipt.json) and [`receipt.md`](./receipt.md) — synthetic run evidence and limits.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

