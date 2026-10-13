# Payment-capability registry

Provider-neutral rails for Commons checkout. Source of truth:
`registry.json`. Projector: `host/payment_capability.py`.

A rail is public only when `capability_state=CHARGEABLE` and
`public_presentation=EXPOSE`. Owner-dashboard chargeability is not a
public URL. Inert rails keep one-click official provider UIs and stay
unpublished.

The registry's `observed_at` scopes its recorded cash and stage fields. An
offline read does not verify current settlement. The projector returns
`collected_cash_usd=null`, `settlement_status=NOT_VERIFIED_IN_THIS_RUN`, and
`settlement_scope=offline_registry_only`. It preserves the registry amount and
time as `recorded_cash_usd` and `recorded_cash_observed_at`. Unknown current
settlement is not zero; keep independently verified historical payments.

This leftover reuses:

- `revenue/checkout_capability/snapshot.json`
- `revenue/outcome_commerce/catalog.json`
- `revenue/payment_ready/pack.json`
- `revenue/reply_to_revenue/funnel.json`
- `revenue/scope_to_delivery/catalog_bindings.json`
- `ground/RESOURCE_LEDGER.json`
- `ground/PROFITABILITY_BUILD_MAP.md`
- `ground/FEATURES.md`

It does not remint SKUs, Payment Links, or catalog listings.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
