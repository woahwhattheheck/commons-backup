# E11 — completed livestock feed supply economics

Operation: `titan-v25-orders-20260909-E11`

This lane adds a **pure evaluator**, not another TITAN controller and not a new
feed ledger. Current canonical TITAN already has a bounded `protect_feed_stock`
consumer that preserves up to two **owned** WHEAT units for reachable
producer-authored feeds. That consumer intentionally rejects `BUY_PRODUCT WHEAT`
as `unresolved_wheat_replenishment`; its focused contracts also prove that a
current or future requested purchase is not treated as already-owned feed.

E11's remaining seam is therefore procurement and receipt timing: when a
producer-owned feed suffix is already physically useful, is it cheaper and still
executable to keep owned WHEAT, buy it just in time, or receive WHEAT from a
separately certified production route?

## What this candidate proves

`feed_service_economics.py` keeps ownership narrow:

- `FeedService` is an already-authored pickup/feed suffix. The existing producer
  remains responsible for actor routes, animal choice, and continuation.
- `completion_value` is supplied by the existing economic/producer layer. E11
  does not invent future animal output, hidden rival state, future shops, or
  future sale cash.
- `simulate_current_wheat_buy` prices a current `BUY_PRODUCT WHEAT` unit by unit
  using the official market quote interface. Successful buys reduce public
  WHEAT inventory one unit at a time, so later units face their actual price
  impact. Cash and shed capacity can produce an explicit partial fill.
- The caller supplies cash and shed room at the proposed queue insertion point.
  Full integration must obtain those values from the existing whole-queue
  funding/capacity logic; this helper does not bypass earlier useful purchases,
  hires, seeds, animals, or other commitments.
- Market orders happen after unit actions. A WHEAT purchase at step `t` is in the
  shed only after that step's actor actions, so it can support a pickup at
  `t+1` or later, never a pickup at `t`.
- Producer-owned WHEAT arrivals use the same conservative strict-before-pickup
  rule. Same-turn cross-actor transfer is declined rather than inferred.
- Pickup requests consume their full actual fill. Surplus carried by one actor
  is not returned to shared stock or double-credited to a second actor.
- A service on an animal already unfed once can carry an explicit escape
  deadline. A candidate that feeds after it is physically too late is rejected.
- Value realized after the terminal step is rejected. Buying late input is not
  justified by nominal animal survival or future output beyond the game.
- Retention cost is the exact current sequential WHEAT sale receipt forgone;
  `SELL` at the floor follows the official no-supply-increase rule.
- `choose_feed_supply` switches only for a **strictly higher positive completed
  service value**. Already-carried/covered feed is an explicit inherited no-op.

## Focused contracts

Run:

```bash
python -m unittest -v test_feed_service_economics.py
```

The suite covers current-buy versus same-turn pickup ordering, later pickup,
cash/capacity partial fills, two actors competing for one shed pool, a feed
before pickup that must be carried, second-unfed-day escape timing, terminal
non-payback, already-covered no-op behavior, exact unitwise buy and retention
price impact, make-versus-retain ordering, no double credit of oversized
pickups, nonpositive completed value, and zero future-sale funding credit.

When executed in the full Commons tree the last contract also loads the current
mechanically extracted engine surface from `cloud-execution-lab/mechanics.py`
and verifies the WHEAT buy curve against those exact bytes.

## Integration gate

This patch does **not** change canonical `frozen_selected.py`,
`operating_stock.py`, `titan_runtime.py`, current release pointers, or archive
bytes. It creates the missing E11 economics/receipt interface and focused
evidence only.

The narrow integration path, if matched official-engine games justify it, is to
let the existing final feed-stock consumer request a current WHEAT purchase only
when:

1. the completed producer snapshot has a reachable later pickup/feed suffix;
2. owned/carry stock does not already cover that suffix;
3. the existing whole-queue feasibility layer proves cash, slots, capacity and
   earlier commitments at the proposed BUY_PRODUCT insertion point;
4. the purchase is strictly earlier than the dependent pickup;
5. a completed-service value evaluator prices the saved animal production above
   purchase/route opportunity cost; and
6. the current producer owns the continuation and eventual receipt.

Activation still requires E11's matched official-engine screen: 32 balanced
seed/opponent pairs × both seats = 64 complete games per variant, followed by an
untouched holdout. Focused contracts are correctness evidence, not a
playing-strength claim. No Kaggle submission is authorized from this order.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
