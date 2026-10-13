# B7 $1 EOD same-product replacement

## Status

Default-OFF, unwired research successor inside the single canonical `repairs/gameplay/b7-shed-overflow/` family. It does not modify the legacy B7 donor, `multicargo_drop_guard.py`, `eod_cargo_custody.py`, `fert_floor_disposal.py`, runtime/default/configuration, `COMPOSITION.json`, `INTEGRATION.json`, archive, or Kaggle submission surfaces.

## Strict-dominance theorem

The pinned official engine orders a callback as unit actions → market → town consumption/plant decay → EOD refresh/drop. A successful `SELL` always removes one unit from the player's shed and credits the quoted cash. At the exact `$1` price floor, `_commit_unit` deliberately does **not** add that sold unit to public market inventory. EOD later drops actor inventories into the shed in actor/insertion order and discards overflow.

For the narrow admitted state:

1. The supplied configuration explicitly carries plain-integer `turnsPerDay`, `shedCapacity`, and `maxMarketOrdersPerTurn`; no theorem-critical field is synthesized from a default. This is an EOD callback under that observed clock/capacity and every authored unit row is literal `PASS`, so the observed private shed/inventories are the exact pre-market private state.
2. The player's existing market queue is an exact canonical positive `SELL`-only prefix (possibly empty) with one official effective market slot still free. The helper projects any private-shed removals exactly. `maxMarketOrdersPerTurn` follows official `max(1, raw)` for the observed plain integer.
3. Projecting official EOD actor/insertion-order drops after that common prefix discards `E > 0` units, and **all discarded units are the same product X**.
4. X is non-buyable through `BUY_PRODUCT`: X is one of CARROT, TOMATO, STRAWBERRY, MELON, EGG, MILK, WOOL. WHEAT and FERTILIZER are refused.
5. The post-prefix private shed still contains at least E units of X.
6. The complete observed public price map is authenticated against the supplied official `market_price` ABI, and X's exact quote is `$1`.

Then appending `SELL X E` is a strict cash-dominance replacement:

- each added sale removes one shed X and credits exactly `$1`;
- the added floor sale does not change X public inventory;
- because X is not BUY_PRODUCT-buyable, unknown rival lockstep cannot reduce X public inventory before the appended row and lift its quote; rival floor SELLs of X also leave public inventory unchanged;
- the extra E shed slots admit exactly the E carried X units the baseline EOD would discard;
- final private shed contents after EOD are identical to baseline, and EOD resets carried inventories in both branches;
- public market inventory and refreshed prices remain identical. Full observed price-map authentication makes even an empty baseline market prefix safe: the candidate's otherwise-extra `_refresh_prices` recomputes the exact already-observed map;
- later town/EOD phases see identical non-cash state, while player cash is exactly `+E`.

The result is a source-level full-callback cash-dominance theorem for the admitted slice. The helper still advertises no runtime promotion/activation authority: composition needs its own current-native ABI binding and natural-engagement/economics evidence.

## Fail-closed boundaries

Admission returns exact parent identity for missing/partial/malformed theorem configuration, non-EOD callbacks, any unit mutation, non-SELL/malformed market prefixes, no free effective market slot, mixed discarded products, WHEAT/FERTILIZER discard, non-floor X quote, stale or malformed public price maps, insufficient post-prefix shed X, over-capacity/malformed private state, actor/inventory shape mismatch, malformed money, missing or throwing market-price ABI, or any non-literal enable token.

There are deliberately **no implicit configuration defaults** inside the certificate path. `turnsPerDay`, `shedCapacity`, and `maxMarketOrdersPerTurn` must be observed on the supplied mapping/object as plain integers. Positive custom capacities are supported when supplied explicitly; missing authority is rejected rather than silently interpreted as 24/100/10. Raw market cap `0` remains valid and normalizes to one row exactly as the official engine does.

## Evidence

- `test_eod_floor_replacement.py` covers the positive theorem, empty-prefix admission, exact parent immutability, literal-True-only authority and ABI-aware install metadata, missing/throwing ABI, **missing theorem-config fields and type poison**, an explicitly observed non-default capacity, EOD/unit/prefix/cap boundaries, mixed/buyable/non-floor/insufficient-stock rejection, numeric poison, full price-map drift, and an existing floor SELL of X in the common prefix.
- `check_eod_floor_replacement_engine.py` pins three execution authorities: official engine Python Git blob `3c202c7ee921da239356789e266b694635103fc4`, adjacent official `kaggriculture.json` Git blob `b354d06b742fe48402513792253f1a5c29366b20`, and the helper blob. Each file is captured **once**; the checker hashes those captured bytes and compiles/executes those exact source bytes. During engine import, the engine's JSON read is bound to the captured JSON bytes rather than a later pathname reopen. A temp-directory regression replaces all three backing paths after capture and requires execution to remain bound to the captured engine/config/helper authority.
- Against those captured authorities the checker executes official `market_price`, `_commit_unit`, `_refresh_prices`, and `_drop_inventories_to_shed` for every non-buyable product across pre-EOD room 0–3 and discarded quantity 1–4 (**112 cells**). Every cell must preserve final shed, inventories, and public market while increasing cash by exactly E. It separately proves an unknown rival's floor SELL of each X leaves public market state unchanged.

No activation or current-tape frequency claim is made by this source package. A green checker is evidence only for this default-OFF source theorem; runtime promotion still requires a separate current-native binding/economics gate.
