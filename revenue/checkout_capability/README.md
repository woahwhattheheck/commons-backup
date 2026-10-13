# Checkout capability snapshot

Measured provider truth for public Commons checkout. This folder stores
**no** bank, routing, tax, card, credential, address, or private buyer
data.

`snapshot.json` is the observation. `host/checkout_capability.py`
projects public rails from it and fails closed when catalog, SKU files,
or HTML disagree.

The snapshot's `observed_at` scopes its recorded cash and stage fields. The
offline projector returns `collected_cash_usd=null`,
`settlement_status=NOT_VERIFIED_IN_THIS_RUN`, and
`settlement_scope=offline_snapshot_only`. The original snapshot amount and time
remain in `recorded_cash_usd` and `recorded_cash_observed_at`. This view does
not replace independently verified historical payments or establish current
settlement.

A public rail is chargeable **and** payout-capable only when livemode,
`charges_enabled`, `payouts_enabled`, link `active=true`, and the
canonical recorded URL all match. Duplicate Payment Links on the same
SKU metadata stay inert.

## Live cash

Verified Commons product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

Cite husk-survival-marketplaces-live-cash-20260909-01 — do not remint. Claim `husk-checkout-capability-live-cash-20260909-01`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
