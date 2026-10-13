# B7 EOD cargo custody successor

This is a narrow successor inside the existing canonical `b7-shed-overflow` family. It does not activate B7, add a gameplay key, create a sibling controller, or claim current-native economics.

## Source fact

Pinned official engine Git blob: `3c202c7ee921da239356789e266b694635103fc4`.

At EOD the engine's `_drop_inventories_to_shed` walks `private["inventories"]` in list order: main farmer first, then hands in index order. Within each actor it walks that inventory's insertion order. Each item deposits only into remaining shed capacity; every remainder is discarded. Unit actions happen before market, market SELL removes shed units, and EOD auto-drop happens after market.

That makes cargo **custody** economically relevant when the shed is full during unit actions but SELLs free capacity before EOD. Earlier actors consume the newly freed room first even when later actors carry more valuable product.

## Existing B7 counterexample, closed mechanically

The already-landed `EOD_PRIORITY.md` counterexample has:

- shed: 100 CARROT;
- farmer carries 10 WHEAT;
- later hand carries 10 MILK;
- EOD unit rows PASS;
- market sells 10 CARROT.

With the default visible prices used by the focused witness (`WHEAT=25`, `MILK=160`), actor-order EOD auto-drop retains the farmer's 10 WHEAT and discards the hand's 10 MILK: carried value retained = `$250`.

If the shed-adjacent farmer instead DROPs while the shed is still exactly full, the engine destroys those 10 WHEAT before market. The same ten CARROT sales then free ten slots, and the later hand's 10 MILK fills them at EOD: carried value retained = `$1,600`, a **+$1,350 current-price custody delta**. Market orders and sale cash are unchanged.

`eod_cargo_custody.py` models that deposit order exactly and exposes only this narrow admission class.

## Admission contract

A rewrite is considered only when all of these hold:

- exact EOD callback under strict positive `turnsPerDay`;
- shed occupancy is exactly `shedCapacity` during unit phase;
- every farmer/hand row is literal `PASS`;
- the market queue contains only strict positive integer `SELL` rows;
- at least one SELL can actually remove current shed stock;
- every carried item is one of the nine PRODUCTS and has a finite non-negative visible price;
- candidate actor is currently shed-adjacent, so `DROP` is legal even on a locked shed-access tile;
- replacing exactly one PASS with DROP yields a unique strict increase in current-price value of cargo deposited by the later EOD auto-drop.

Everything else preserves the exact parent action object.

The helper does **not** project future prices, future actions, BUY/HIRE/LAND capacity changes, HARVEST/COLLECT mutations on the boundary callback, non-product cargo, partial-room DROP semantics, or multi-actor discard combinations. Current visible price is only an admission shadow value; this is not an EV theorem.

## Validation status

Published branch source blob: `a74d7f195d5ceb0b1565dd64da28c6b8b925b45a`.
Published focused test blob: `fb6a32d008bc1d91a0d6eedcedf132fb584c1eb5`.

The exact published source text was compiled/executed in-session and the 14 source-independent focused behaviors were replayed successfully, including the +$1,350 witness, OFF object identity, actor/item order, reverse-value refusal, non-EOD refusal, partial-room refusal, non-PASS refusal, BUY/HIRE/LAND refusal, no-capacity-release refusal, oversized SELL stock cap, shed-adjacency requirement, non-product refusal, nonfinite-price refusal, and deterministic multi-actor handling.

The isolated execution container could not resolve public GitHub, so the test file's filesystem source-pin case was **not** locally executed. The authority itself is independently verified by GitHub: canonical `reference/engine/kaggriculture.py` is exact Git blob `3c202c7ee921da239356789e266b694635103fc4`, which is the helper's fail-closed expected blob. Hosted CI is not claimed green unless a later receipt says so.

## Handoff

B7-CUSTODY is an admission/oracle, not a runtime promotion. Any current-native assembler may consume it only inside the existing B7 family and should first census natural EOD full-shed + PASS + SELL engagement. CARRYBANK retains deliberate intraday hoisting, FLOORDRAIN/FLOORSINK retain sale-based room creation, and LABORFLOW retains generic hand economics.