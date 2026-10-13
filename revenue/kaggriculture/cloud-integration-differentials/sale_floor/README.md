# Optional sale-floor funding selector

`select_sale_funded_seed_queue` is a five-argument callback for the existing
`seed_queue_selector` seam. It first delegates to the current `seed_funding`
certificate. Only when that certificate has validated the inputs and rejected
solely because the original queue needs cash does this wrapper consider a hard
lower bound from earlier sales of products already present in the observed own
shed.

The proof is prefix ordered. Every purchase or hire must be affordable before a
later sale is credited. Each product's observed stock is credited at most once,
at the official engine `PRICE_FLOOR`. Carried goods, pending harvests, expected
purchases, rival private state, future prices and later sales add no credit. Any
subsequent SELL rewrite requires revalidation.

```python
from sale_floor import select_sale_funded_seed_queue
chosen, report = select_sale_funded_seed_queue(
    mechanics, post_unit_observation, final_selected_action,
    demand_valid_seed_proposal, configuration)
```

This is opt-in. The existing `seed_funding.py`, default callback, canonical
runtime, default features and release archive are unchanged.

## Evidence

The focused repository regression has 10 methods and executes official market
transitions for both seats. The complete preparation packet passed 38 methods,
410 official market stages, 202 certified paired cases and 640 exact default
result comparisons. It includes unchanged Arlene route queues and cached
`SeedBudget`: MAIN step 600 retains seven hires while reducing WHEAT 17→3
(+$140), and step 624 retains eight hires while removing an unnecessary buy
(+$90), both seats. Negative cases include hire-before-sale, reused or absent
stock, truncation, later sale, SELL rewrite, invalid numbers, product bounds,
land, animals and multiple hires.

The exact callback was also installed into fresh stateful actors for 17 retained
streams / 12,069 calls from the a8af and 7b58 packages. Their 30 actual funding
calls were already cash-funded, so this option activated zero times and changed
no action before the known step-696 input-budget wrapper boundary. DELVE 9965001
and 9965019 are likewise cash-funded. This is reusable component work, not a
current checkpoint improvement, game result or promotion request.

See `VALIDATION.json` and `RETAINED-STREAM-SCAN.json`.

## Reproduce the repository regression

```sh
python3 -B revenue/kaggriculture/cloud-integration-differentials/sale_floor/test_sale_floor.py
```

The test uses the repository's pinned official engine and current base
certificate. It executes no full game and consumes no policy seed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
