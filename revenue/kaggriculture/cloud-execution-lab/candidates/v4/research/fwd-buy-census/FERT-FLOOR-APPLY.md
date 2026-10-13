# Gemini FERT floor-buy/apply — full-path source certificate

Status: **constructed full-interpreter research / no current-native engagement or activation claim**.

The all-Gemini convergence ledger correctly separated this historical proposal from the false `$1 FERT warehouse` idea. The warehouse claim is false because a floor-price SELL destroys shed custody instead of creating recoverable public stock. A different seam survives: official `BUY_PRODUCT` can buy public FERTILIZER, and at sufficiently high public inventory the one-unit post-buy quote reaches the engine's `$1` price floor.

That price observation alone is not an exploit. Bought FERT lands in the shed; `FERTILIZE` consumes a unit from the acting farmer's carried inventory. A usable path therefore has real custody and action costs:

`BUY_PRODUCT FERTILIZER -> shed -> PICKUP FERTILIZER -> FERTILIZE -> WATER/production -> HARVEST -> sale`.

`fert_floor_apply.py` runs the relevant transitions through the already-authenticated full interpreter used by `opportunity_cost.py`. It does not implement another market model or donor policy.

## Two constructed witnesses

### Minimal one-WATER CARROT witness

The short witness retains a deliberately constructed day-3 CARROT state at the farmer's shed-access tile. Candidate buys one FERT at step 90, PICKUPs at 91, FERTILIZEs at 92, and then shares the control's WATER/HARVEST/DROP+SELL/DIG path. This isolates the complete FERT custody path and one boosted WATER. Its abbreviated crop prehistory is not a current-V4 reachability claim.

### Continuous source-planted three-day MELON witness

The stronger witness no longer injects a MELON tile or a zero-yield crop state, and it no longer jumps over the pinned fixture's remaining day-3 callbacks. `opportunity_cost.fixture()` starts at step 90 / day 3 / hour 18. Both arms begin from the same legal empty unlocked shed-access tile with one MELON seed and execute **every callback from step 90 onward** through the official interpreter:

- steps 90..95: common `PASS`, including the official EOD at step 95. After EOD95 the current tile must still be empty and the MELON seed must still be present;
- step 96 / day 4: common `PLANT MELON` consumes the seed. The official `_new_plant` constructor makes non-ongoing MELON start with **one** yield unit and `consecutive_unwatered == 1`;
- step 97 / day 4, step 144 / day 6, and step 192 / day 8: common survival `WATER` callbacks keep the crop live. These occur at ages 0, 2 and 4, before MELON's WATER-yield window begins at age 6, so the source-real yield remains one;
- every callback through step 239 is executed. After the day-9 EOD, both arms must still hold the same live MELON with `yield_units == 1`, `consecutive_unwatered == 1`, and `watered_today == false`;
- candidate alone buys FERT at 240, PICKUPs at 241 and FERTILIZEs at 242;
- candidate and control share production WATER at 243/day 10, 264/day 11 and 288/day 12;
- day 13 is allowed to pass unwatered. The day-12 WATER resets the streak to zero at EOD12, so EOD13 raises it only to one and the plant remains live;
- MELON's official `first_yield_day` is 10. A day-4 plant therefore cannot legally HARVEST on day 12 (age 8) or day 13 (age 9). The first legal harvest is **step 336 / day 14 / age 10**, followed by DROP+SELL at 337.

With official MELON max yield six, the authored source expectation is candidate yields `3 -> 5 -> 6` versus control `2 -> 3 -> 4` across the three common production WATERs. If exact execution confirms that trace and the legal day-14 harvest, FERT contributes **two** incremental MELON units, not three. The two candidate-only unit callbacks (`PICKUP`, `FERTILIZE`) are then amortized to **one extra unit callback per incremental MELON**, versus two extra unit callbacks for the one-unit minimal witness.

The earlier +3 / 2⁄3-callback claim was rejected because it depended on an impossible zero-yield MELON prestate. A later day-12/day-13 liquidation was also rejected because source HARVEST requires `day - planted_day >= first_yield_day`, and MELON's `first_yield_day` is 10. Finally, skipping steps 90..95 was rejected because it crossed the authenticated fixture's EOD95 without executing it. The certificate now preserves fixture chronology, constructor semantics and harvest-age rules directly from source.

## Exact floor boundary

The source-derived floor threshold is the lowest pre-buy FERT market inventory whose one-unit post-buy quote is `$1`. The helper searches the authenticated engine's own `market_price`, preserving source rounding and shape semantics rather than hard-coding a formula.

The minimal panel remains both seats × `{threshold-1, threshold, threshold+100}`. The amortized witness runs both seats at the exact threshold. These are source-mechanism fixtures, not evidence that current V4 naturally reaches those public inventories or has spare action capacity.

The declared full-panel callback count is **1,076**: six minimal cells × two arms × seven ticks = 84 callbacks, plus two amortized seat cells × two arms × 248 ticks (steps 90..337 inclusive) = 992 callbacks.

## What a positive witness would mean

A positive focused run establishes only that, under the constructed economics and idle-capacity assumption, the official interpreter can:

1. carry the authenticated fixture continuously through EOD95 without inventing crop state;
2. source-execute MELON planting and survival to the day-10 window;
3. buy floor-price FERT and preserve shed -> farmer -> crop custody;
4. apply the three-day fertilizer window to common WATER callbacks;
5. realize two incremental MELON units after the real source constructor's initial yield is respected;
6. keep the crop alive until the first source-legal harvest at age 10; and
7. converge candidate/control back to equal private/farm physical state after liquidation.

It still does **not** establish current-native profitability or activation authority. The candidate-only PICKUP/FERTILIZE callbacks may displace more valuable work, natural FERT-floor frequency is unknown, and live storage, financing, route, crop, service and opponent constraints remain outside this certificate.

## Promotion path

1. Execute `check_fert_floor_apply.py` against the exact authenticated reference engine in normal and optimized Python and compile both source/checker. The run must prove shared PASS 90..95 preserves the empty tile + one MELON seed through EOD95; literal `PLANT MELON` at step 96 consumes that seed; the source initial yield is one; the day-9 live prestate and day-13 survival state are valid; HARVEST at 336 is source-legal; and the final harvest delta is +2, not +3. The full panel must report **1,076 callbacks**.
2. Census current composed-V4 observations for natural FERT quotes and genuinely idle shed-adjacent capacity; do not synthesize field reachability from this fixture.
3. Charge the two candidate-only unit callbacks against the incumbent returned action while preserving funding, headroom and route obligations.
4. Only a both-seat current-native returned-action change with positive paired economics and no service/storage regressions may become a gameplay proposal.

Until then, the correct V4 form is a source-bound mechanism certificate, not a `price == 1` policy trigger.
