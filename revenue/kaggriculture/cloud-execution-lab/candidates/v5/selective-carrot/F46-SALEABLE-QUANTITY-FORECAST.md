# TITAN V5 Wave-4 F46 — Saleable Quantity Forecast

Operation: `TITAN-V5-F46-SALEABLE-QUANTITY-FORECAST-ZFRJ7Q2-20260913`

## Scope

F46 is an additive, fail-open source carrier for one narrow terminal-market mechanism: remove only a contiguous **trailing** suffix of `SELL` rows that is provably incapable of selling any own product from the post-unit shed state.

The suffix restriction is intentional. The current loss frontier has already shown that changing market row alignment can retime lockstep interaction with the rival. F46 therefore never removes an interior dead row and never reorders a surviving row. It also never changes farmer/hand actions, cargo routing, `DROP`/`PICKUP`/`PLACE`, productive `HARVEST`/`COLLECT_FERTILIZER`, FORCE_END, or SELL priority.

## Authority and fail-open rules

- Source stack is pinned to the exact C02 `delivery_choice.py` postimage `f367b527c8570d3f9bdfe5c1062f58fb2b7636f31f035f9a4587bc35a1b292b3`.
- The injector rejects any different `delivery_choice.py` bytes and rejects an already-present F46 helper.
- The guard reads only own post-unit `private.shed` plus the already-authored market rows.
- A prior `BUY_PRODUCT` makes that product uncertain because a fill is not assumed; later SELL rows for it are preserved.
- Unknown or malformed market operations stop later classification rather than being guessed through.
- Partially executable SELL rows are preserved.
- Interior dead rows are reported but preserved so surviving row indices do not move.
- Inputs are copied; parent action and state are not mutated.

`post['private']['shed']` is used only after the parent has produced the post-unit state. Product still in hand, on a tile, or in future production is not counted as saleable unless another already-authoritative mechanism has actually moved it into that post-unit shed state. This keeps F46 disjoint from F43 cargo return and F45 productive-action protection rather than silently claiming their authority.

## Gate discipline

This package does **not** mint a candidate archive, launch games, rotate `CURRENT`, change defaults/releases, or submit to Kaggle. `build_f46_saleable_quantity_forecast.inject()` is a deterministic source transformation only. The Wave-4 RAW/superiority gate remains the authority for any remint and paired economics.

After that gate releases, the required first runtime check is exact engagement on the held WF1+C02 line: confirm the base carries the exact C02 postimage, inject F46, require at least one `trimmed_proven_dead_sell_suffix` receipt, then run at most the Wave-4 phase-1 panel before any broad gauntlet. Inert or negative economics terminalize the factor; positive standalone economics must still be tested incrementally after exact held leader `8b4b074012fe3bd731c218a4956f85ce8dadd74d5afe81a3e04c2795a2a533ee`.

## Verification

Focused test module: `test_f46_saleable_quantity_forecast.py`.

It covers trailing-only suppression, interior-row preservation, multiple dead suffix rows, partial fills, BUY_PRODUCT uncertainty, unknown/malformed rows, fail-open shed handling, input immutability, single-anchor source drift, stale-preimage rejection, and exact binding to the checked-in C02 component fixture.
