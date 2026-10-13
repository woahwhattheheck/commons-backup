# Commons listing registry

Machine snapshot for [listing-registry.html](../../listing-registry.html).

Canonical offers stay in `revenue/outcome_commerce/catalog.json`. Distribution
channels stay in `revenue/distribution/`. This directory is the listing
registry: one row per offer × surface, plus ready-to-submit copy from real
evidence.

```bash
python3 host/listing_registry.py validate
python3 host/listing_registry.py registry
python3 host/listing_registry.py asset --id ho-issue-to-pr__upwork-project-catalog
python3 host/listing_registry.py export
python3 host/listing_registry.py submit   # always SUBMIT_FORBIDDEN
python3 host/listing_registry.py --self-test
```

`submit` always fails. Assets are not live listings.
The retained `registry.json` records `external_live_listings=0`, `submitted=0`,
`verified_buyers=0`, and `duplicate_postings=0` within that snapshot's scope.
Its cash amount is historical, not a current settlement readback.

Fresh offline projections emit `collected_cash_usd=null` and
`settlement_status=NOT_VERIFIED_IN_THIS_RUN` in both counts and funnel truth;
`recorded_collected_cash_usd` preserves the retained funnel amount. The schema
accepts nullable, numeric, or string cash values rather than requiring exactly
`0.00`. The display says **Unverified** until current settlement is verified.
Unknown is not zero; independently verified historical payments remain valid.

Do not remint commerce, distribution, checkout, current-work, or the
profitability map from here.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
