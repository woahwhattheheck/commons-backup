# DEMANDVEL × COMEBACK — state-custodied residual public-supply pressure

This is research-only evidence inside the existing V4 market-baseline authority. It does not sell, retime, choose a product, add a runtime key, or authorize an action.

## Why v5 exists

The earlier composite correctly pinned its helper bytes and later bound Apex timing, max-quantity semantics, q, seeds, and current shop-state custody. Two independent source-real gaps then surfaced:

1. immediate COMEBACK/no-event arithmetic was conditioned on supplied `unlocked_shops`, while the unwind budget originally came from unconditional seed1..100 trajectories whose shop histories were different; and
2. pinned COMEBACK `predump_counterfactual()` floors town-consumption intermediates with `max(0, ...)`, while the official engine town path can drive market inventory below zero. In the floor-active domain, the reduced helper can change immediate swing and residual public supply.

This package fails closed on both gaps rather than widening a research helper into an engine reimplementation.

## State custody

`pressure_certificate()` requires a complete current shop tuple.

For the pinned source-exact town model, shop instances unlock every three days and persist. The tuple therefore must contain exactly

`min(MAX_SHOP_INSTANCES, (pre_step // TURNS_PER_DAY) // SHOP_UNLOCK_INTERVAL)`

known shop names. Duplicates are allowed because unlock sampling is with replacement. A filtered product-only tuple, empty tuple at a mature step, impossible cardinality, unknown shop name, list coercion, or other malformed state rejects.

This removes the old unreachable 380 stress fixture with eight shops. At step380/day15 exactly five shop instances exist. The canonical 380 example uses a reachable five-instance STRAWBERRY-consuming multiset.

## Authoritative unwind budget

The certificate counts only demand guaranteed by already-known state:

1. every future sale tick from the exact current shop instances, because those instances persist; plus
2. every future town-center tick for the product.

Unknown future unlocks are deliberately counted as zero because this module does not bind current RNG/empty-tile state.

The unconditional seeded p10 panel remains visible as `remaining_absorption_tail_context`, but carries:

- `state_conditioned=false`
- `authority_for_certificate=false`
- `context_only=true`

It never determines the disposition.

Current DEMANDVEL also exposes horizon-window public-pressure helpers. Those helpers remain passive-baseline context and do not convert a different seeded shop history into state-conditioned authority.

## Reduced-helper underflow custody

Pinned COMEBACK uses `max(0, ...)` around town consumption in `predump_counterfactual()`. The official engine does not impose that market-inventory floor during `_town_consume`.

For this helper, SELL never decreases market inventory. Therefore one conservative precondition dominates every inherited clamp site: the no-event inventory must stay nonnegative across the two local town-consumption callbacks.

The certificate computes:

`required_start = town_drain(pre_step) + town_drain(pre_step + 1)`

and rejects before COMEBACK execution whenever:

`starting_inventory < required_start`.

At equality, the no-event path reaches exactly zero and every inherited `max(0, ...)` is inactive rather than corrective. The output records this as `reduced_helper_domain_custody`; it explicitly sets `official_negative_inventory_domain_certified=false`.

Source-real killer: at pre380 with the reachable five STRAWBERRY-consuming shops, `d0=5`, `d1=0`. Starting inventory 0 or 4 is rejected. Starting inventory 5 is the exact accepted boundary. This closes the case where the reduced helper previously reported a positive immediate counter from inventory 0 even though official unbounded town-consumption semantics change the result.

This is intentionally narrower than rewriting COMEBACK globally. Other consumers of the shared COMEBACK research helper are untouched.

## Current examples

With the pinned sources and outside the rejected underflow domain:

- 380/381, five reachable current STRAWBERRY-consuming shop instances: residual public supply 16; guaranteed remaining current-shop drain 420 + town center 14 = **434**; positive immediate swing and guaranteed tail headroom.
- 402/403, five reachable current shops with no STRAWBERRY consumer: residual supply 16; guaranteed town-center-only budget **13**; slack -3; `POSITIVE_IMMEDIATE_COUNTER_TAIL_UNWIND_NOT_CERTIFIED`. Unconditional p10 127.3 is context only.
- 402/403 synthetic starting inventory 9,700 with our128 + rival max8: residual 136 against the same guaranteed budget 13; slack -123; not certified.
- saturated `$1` sales still add zero invented public supply.

The useful invariant is unchanged: positive immediate counter economics are not enough to certify public-inventory unwind.

## Other evidence-coordinate custody retained

The certificate fails closed unless:

- `pre_step + 1` is one of the pinned Apex STRAWBERRY source event steps;
- `rival_units` equals that event's source-declared `max_sell`;
- the source event is treated as a conditional maximum envelope, never a replay-realization claim;
- q is exactly 0.10 and seeds are exactly the canonical tuple 1..100;
- the supplied current shop tuple is structurally reachable; and
- the inherited reduced-helper town clamp is provably inactive for the supplied starting inventory.

Custom seeded tails remain available only as context/sensitivity. They never become certificate authority.

## Source custody

The module captures and Git-blob authenticates all three helper snapshots before execution and binds DEMANDVEL to the same in-memory market baseline:

- `market_baseline.py` `8c62e0161152910ee365596577b59a9cea36eb2c`
- `demand_velocity.py` `9be0aacee012251e32902536c92d24f64c09ab8a`
- `counter_ambush.py` `041b47d3741bdb1f4bd676325fb9949c36ffe51e`

The DEMANDVEL pin is the current V4 convergence successor containing horizon-aligned public-pressure primitives. Its `DEFAULT_SEEDS` and passive `market_baseline.simulate` semantics used by this certificate remain compatible with the predecessor.

The official engine identity carried by COMEBACK remains `3c202c7ee921da239356789e266b694635103fc4`; this package does not claim engine-equivalence inside the rejected negative-inventory domain.

## Limits

A structurally reachable shop tuple is not itself proof that a particular replay observed that tuple. Real replay promotion still needs exact observation/replay custody.

The guaranteed budget is intentionally conservative because unknown future shop unlocks are ignored. `NOT_CERTIFIED` means this proof cannot discharge unwind pressure; it is not a direct "do not sell" action rule.

The underflow guard deliberately refuses states where the reduced COMEBACK helper can diverge from the official engine. Future work may replace that rejection with a separately authenticated source-exact engine counterfactual, but this certificate does not do so.

No runtime/default/config/COMPOSITION/INTEGRATION/archive/Kaggle mutation is authorized here.

Validation from this directory:

```bash
python -B test_tail_pressure.py
python -O -B test_tail_pressure.py
python -m py_compile tail_pressure.py test_tail_pressure.py
python -B tail_pressure.py
```
