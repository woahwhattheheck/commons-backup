# P18 — completed feed WHEAT sourcing certificate

Operation: `titan-v25-orders-20260909-P18`

P18 extends the **already landed E11 feed-service evaluator** rather than creating
another feed ledger or controller. E11 proved receipt ordering and compared
`make` / `buy` / `retain` candidates once a supply arrival and explicit costs
exist. P18 supplies the missing `make` certificate: can an already-authored WHEAT
plant → water → harvest → deposit route physically finish before the dependent
pickup, and what completed opportunity cost should E11 compare with exact JIT
buying or retention?

## Mechanical boundary

The certificate is deliberately conservative and uses current extracted WHEAT
mechanics:

- WHEAT seed cost is read from `mechanics.CROPS["WHEAT"]`, not hard-coded into
  the evaluator.
- Planting starts at `consecutive_unwatered = 1`; a route that weeds before its
  harvest is not certified. Because this evaluator has no actor-order proof, it
  conservatively declines a WATER on the exact PLANT step rather than inventing
  a same-step handoff; a later action on the planting day is certifiable.
- HARVEST must reach the official first-yield age. Unfertilized WATER actions in
  the official yield window raise the certified yield one unit at a time, up to
  the official maximum.
- Harvested WHEAT remains actor-carried until a later deposit. A deposit at step
  `t` is converted to E11 `SupplyArrival(step=t, ...)`; E11's strict receipt
  contract then allows it only for a pickup at a later step.
- Shed room is checked at the proposed deposit. A route that would overflow is
  not treated as completed supply.
- Deposits after the terminal action horizon have zero service value.

This is not route search. The active producer remains responsible for selecting
the actor, tile, movement, water, harvest and return path. P18 certifies only a
completed producer-owned continuation.

## Delivered cost

`wheat_route_cost` includes explicit seed cash (zero only when the caller proves
an already-owned seed), field opportunity cost, displaced actor action value,
travel opportunity cost, the foregone sale value of WHEAT consumed as feed, and
named extra costs. It gives **zero credit to future sale cash**.

The field/action/travel inputs are intentionally supplied by the existing
producer/economic layer. A ten-dollar seed does not imply a ten-dollar delivered
feed unit; a route that displaces more valuable fieldwork or cannot finish by the
feed deadline must lose to a feasible purchase/retention alternative.

`make_e11_candidate` accepts the landed E11 module object and returns E11's own
`FeedSupplyCandidate`; P18 does not duplicate its stock accounting.

## Bounded reserve

`observed_feed_reserve_units` implements only the requested 0/1/2-day reserve
screen. It counts **observed dated feed obligations**, subtracts already-covered
units, caps the buffer, and adds no speculative future demand.

## Focused evidence

Run:

```bash
python -m unittest -v test_feed_sourcing.py
```

Contracts cover first-yield timing, weed survival, yield-window watering,
over-promised yield, harvest/deposit order, same-step dependent pickup,
terminal cutoff, shed blockage, complete delivered cost, owned-seed cost,
adaptation to E11, imminent-deadline no-op, make-vs-retain opportunity cost,
0/1/2-day reserves, and already-covered no-op behavior. On a full Commons
checkout one additional contract loads the current extracted mechanics bytes and
pins the WHEAT constants used by the certificate.

## Activation gate

This additive patch does **not** modify canonical producer, seller, runtime,
release pointers, archive bytes, or submission state. It creates the physical
and economic certificate needed for a producer-owned P18 integration candidate.
Canonical admission still requires a bounded integration and the order's matched
full-game development screen plus untouched holdout. No playing-strength gain is
claimed from focused contracts alone.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
