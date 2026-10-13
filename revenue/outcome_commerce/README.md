# Commons Outcome Commerce Bridge

This module turns Commons' separate commercial surfaces into one machine-readable
economic layer without changing their canonical terms.

```text
canonical offer -> catalog adapter -> quote
DIO job         -> immutable commercial events -> deterministic state projection
accepted work   -> immutable metering events -> deterministic statement
statement       -> external rail reference -> separately measured cash states
```

Run:

```bash
python3 host/outcome_commerce.py validate
python3 host/outcome_commerce.py catalog
python3 host/outcome_commerce.py quote --listing ho-issue-to-pr
python3 host/outcome_commerce.py quote \
  --catalog revenue/outcome_commerce/examples/hybrid_catalog.json \
  --listing synthetic-hybrid-agent \
  --metric platform=1 --metric action_units=1350 --metric outcomes=4
python3 host/outcome_commerce.py statement \
  --catalog revenue/outcome_commerce/examples/hybrid_catalog.json \
  --events revenue/outcome_commerce/examples/hybrid_events.json
python3 host/outcome_commerce.py project \
  --events revenue/outcome_commerce/examples/commercial_events.json
```

The CLI is standard-library-only, uses `Decimal`, deduplicates exact event IDs,
refuses conflicting duplicates and mixed-currency statements, applies explicit
reversals and prepaid credits, and never claims payment.

## Per-SKU sales funnels

The canonical `catalog.json` also carries one `funnels` entry for every listing.
It does not create a second offer catalog or replace source terms. Each entry
binds the intended buyer and trigger to acquisition copy, public qualification,
checkout or buyer-specific invoice, fulfillment, acceptance, refund truth,
next offer, and unresolved gaps. Priorities are a complete unique sequence, so
the web page can present a first-cash queue without deleting or hiding a SKU.

The funnel chain is:

```text
DISCOVERED -> QUALIFIED -> QUOTED -> FUNDED -> RUNNING -> SUBMITTED
           -> ACCEPTED -> SETTLED -> BANK_AVAILABLE
```

`data-funnel-sku` and `data-funnel-action` attributes make browser CTAs
machine-identifiable without adding telemetry. A click remains `INTENT_ONLY`.
No durable state advances until its named evidence exists, and only
`BANK_AVAILABLE` closes the cash loop. `funnel_truth` is a dated observation,
not a counter that silently changes when a checkout opens.

`event.schema.json` is the canonical DIO-linked commercial transition envelope.
It preserves `correlation_id`, chains predecessor events, and binds retries to a
stable `idempotency_key`. A crash after an external call enters
`UNKNOWN_EFFECT`; the projector refuses a blind retry and accepts only an
explicit provider reconciliation to `RUNNING` (effect absent) or `SUBMITTED`
(effect completed). `metering-event.schema.json` is the charge-calculation
adjunct. Neither schema moves money, contacts a buyer, or invokes a provider.

Schemas use JSON Schema draft 2020-12. Example data is synthetic and does not
represent a buyer, invoice, settlement, or collected cash.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
