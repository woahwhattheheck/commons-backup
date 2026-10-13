# ASTRA-BASELINE — no-action town/market baseline

Evidence package for the single TITAN V4 line. It answers the 100-seed full-season baseline request with both players taking no unit or market actions, so every market move comes from town-center demand plus RNG-driven shop instances.

## Source contract

Pinned official engine blob: `3c202c7ee921da239356789e266b694635103fc4`.
Pinned engine spec blob: `b354d06b742fe48402513792253f1a5c29366b20`.

`market_baseline.py` is a reduced model of only the official state reachable under no player actions. It copies the market formula, default cadence, town consumption, daily RNG formula, weed-before-shop RNG consumption, replacement shop unlocks and action-bearing callback horizon (`step 0..718`). This is **not claimed as a direct kaggle_environments interpreter run** because that package was unavailable in the authoring runtime.

The weed RNG is included because shop choice shares the same daily RNG stream after player-0 and player-1 weed draws. PASS-only farms begin with 25 empty NW tiles each; weeds persist, so the model tracks remaining empty tiles and therefore the exact number of RNG calls before each shop draw.

## Executed receipt

Fixed seeds: integers `1..100` inclusive.

```text
python -B -m unittest -v test_market_baseline.py
# 7/7 PASS
python -B market_baseline.py --out . --seed-start 1 --seed-count 100
```

`RESULTS.json` is the compact 100-seed aggregate. The source also emits `price_curve_steps.csv` and `price_curve_days.csv`; the full 719-step table is intentionally generated rather than checked in to avoid derived-table bloat. `VALIDATION.json` records its reproducible SHA-256.

## Findings

### `T` is not automatically a hinge

The request's STRAWBERRY/WOOL “spike at T” premise is false. `T` normalizes every curve; only `below_func == "hinge"` has a hinge knee there.

* STRAWBERRY: `sqrt`, T=100, target +70% at depletion 100.
* WOOL: `log`, T=105, target +20% at depletion 105.
* Actual hinge products: CARROT (T=450), TOMATO (T=200), EGG (T=332).

### Town-only final distribution at step 718

| Product | mean depletion | mean price | price range | seeds reaching depletion ≥ T |
|---|---:|---:|---:|---:|
| WHEAT | 536.16 | $47.87 | $34–54 | 84/100 |
| CARROT | 363.18 | $99.51 | $37–1,111 | 32/100 |
| TOMATO | 231.96 | $144.05 | $64–786 | 58/100 |
| STRAWBERRY | 393.60 | $282.29 | $166–361 | 97/100 |
| MELON | 30.00 | $280.00 | $280 | 0/100 |
| EGG | 240.42 | $71.35 | $52–246 | 27/100 |
| MILK | 303.24 | $305.24 | $208–398 | 85/100 |
| WOOL | 217.20 | $240.79 | $229–258 | 55/100 |
| FERTILIZER | 0.00 | $100.00 | $100 | 0/100 |

The large CARROT/TOMATO/EGG maxima are the real hinge effect: some replacement-shop multisets drive NPC-only depletion beyond T and the quadratic post-knee term dominates.

Among seeds crossing T, STRAWBERRY crosses first between days 10–28 (median 14.5), WOOL days 8–27 (median ~16.2), MILK days 12–28 (median ~18.7), TOMATO days 17–29 (median ~22.9), CARROT days 17–29 (median ~24.9), EGG days 20–29 (median ~25.8), WHEAT days 21–29 (median 25). MELON/FERT never cross.

Controls: FERTILIZER stays exactly inventory 10000 / price $100. MELON has no shop demand; 30 town-center ticks produce final inventory 9970 / price $280 in every seed. Shop unlocks occur on days 3,6,9,12,15,18,21,24 and stop at 8 instances.

## Use / non-use

Use this as a baseline demand oracle for sale-window, crop-mix, market-pressure and production-timing work. Do not attribute this NPC price drift to opponent behavior. This package contains no gameplay policy, key, default, archive or Kaggle activation.
