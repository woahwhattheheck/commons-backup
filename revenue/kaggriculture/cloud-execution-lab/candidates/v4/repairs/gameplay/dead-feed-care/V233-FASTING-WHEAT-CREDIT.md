# ASTRA-LANTERN-STARVE — V233 FASTING WHEAT carry-credit

This packet is the **non-duplicative V233 consumer** of the already-landed FASTING admission helper. It does not decide when FEED may be skipped and it does not compose a second runtime/controller.

Authorities consumed:

- FASTING FEED→PASS planner: `dead-feed-care/uncared_eod_feed_skip.py`, Git blob `13aff8a675ebdb99f6d2c45e3e589d6e2c38e39e` (PR #12813).
- Existing W2 FEED→CARE salvage remains `dead_feed_care.py` blob `51c17ea3245755673ffead8e86d4b04e7766c949`.
- V233 source seam: `donor/overlay/r04_full_router.py` blob `a3e2fe87c717d128e43c9b65bae2265f40d1d76d`; committed V233 appends exact daily `BUY_PRODUCT WHEAT 6`, `HIRE`, `HIRE` and owns two workers over the six SE sheep sites `(5..7,5..6)`.
- Official Kaggriculture engine source: Git blob `3c202c7ee921da239356789e266b694635103fc4`; execution artifact `10175943272` engine SHA-256 `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`.

## Mechanism

FASTING may certify an hour-23 V233-owned sheep `FEED -> PASS`. That saves one WHEAT **in the worker inventory**. Official EOD semantics then call `_drop_inventories_to_shed(private, shed_cap)`, dismiss hands, reset `hires_today`, and reset per-worker inventories. Therefore a saved unit can become next-day shed stock rather than disappearing with the hand.

That does **not** mean arbitrary existing shed WHEAT should reduce V233's dedicated daily purchase. Parent/native work may own it. This helper creates credit only from an exact FASTING planner result on a V233-owned worker/site and carries that credit across exactly one EOD.

On the immediately following morning, it may shrink V233's own exact `WHEAT 6` row by one or two units only if all of these remain true:

1. exact default board/day/season/shed/market-cap configuration;
2. V233 is committed and all six V233 sheep are physically present;
3. the prior credit came from V233's exact two-worker / six-site partition;
4. the morning shed is **strictly below capacity**, proving the prior EOD drain had spare room;
5. physical shed WHEAT is at least the credit;
6. no intervening current-day unit or market row touches WHEAT before the V233 request;
7. the action contains one and only one exact committed V233 suffix `BUY_PRODUCT WHEAT 6`, `HIRE`, `HIRE`;
8. there is no simultaneous initial `BUY_LAND` / `BUY_ANIMAL SHEEP` investment and no other WHEAT market row.

The helper edits only the quantity of that exact V233 row (6→5 or 6→4). It never removes the row, so market row cardinality/index pairing is preserved. If custody becomes ambiguous—especially a full shed, missing physical WHEAT, or an intervening WHEAT touch—the credit is invalidated permanently rather than carried forward and accidentally revived.

## Why this is narrower than the rejected blanket idea

The fleet already retained a historical falsifier: broad interval feeding saved ~60.9 successful WHEAT feeds/game but lost substantial margin because CARE bonus economics are feed-dependent. FASTING therefore owns only a highly conservative final-hour theorem. This V233 helper consumes only those certified savings and recovers the *next-day purchase redundancy* they can create; it does not generalize to every animal, every feed, or every existing shed unit.

## Integration contract

No native composer is included here. Existing LOOM/native assembler authority should wire the packet in two places only:

- after the final composed action is available at hour 23, call FASTING's `plan_uncared_eod_feed_skip(...)`; after FASTING/W2 ownership is resolved, pass the **actual accepted FASTING changes** to `observe_v233_fasting_skips(...)` before state rollover;
- on the next day's V233 request path, after the exact V233 market suffix exists but before final market execution, call `apply_v233_fasting_wheat_credit(...)`.

Do not synthesize `fasting_changes` from heuristics. Do not count arbitrary shed WHEAT as credit. Do not run the helper if the exact V233 source signature has drifted.

## Validation

Authored exact bytes:

```bash
python -B -m unittest -v test_v233_fasting_wheat_credit.py
python -O -B -m unittest -v test_v233_fasting_wheat_credit.py
python -B -m py_compile v233_fasting_wheat_credit.py test_v233_fasting_wheat_credit.py validate_v233_fasting_wheat_credit.py
python -B validate_v233_fasting_wheat_credit.py "$TITAN_REFERENCE/engine/kaggriculture.py"
```

Result: **26/26 PASS** normal, **26/26 PASS** optimized, compile PASS. The source-bound engine witness executes the authenticated engine's exact `_drop_inventories_to_shed` function in isolation: two saved WHEAT survive when the shed has room; only one survives with a 99/100 prefilled shed. It also verifies the EOD source order `drain inventories -> dismiss hands -> reset inventories`. The full-shed case is intentionally fail-closed in the helper.

## Status / next gate

`SOURCE_BOUND + DEFAULT_OFF`. This is not current-native engagement or economics evidence and does not justify activation. Next gate belongs to the existing native assembler/gauntlet: exact FASTING+V233 materialization, natural engagement census, then both-seat paired economics recording credits offered/applied/invalidated, WHEAT bought/saved, market/capacity effects, CARE/product/fertilizer output, fallbacks/deadlines, and terminal margin. Zero engagement means `COLD`, not a kill.

No production/default/archive/workflow/Kaggle mutation.
