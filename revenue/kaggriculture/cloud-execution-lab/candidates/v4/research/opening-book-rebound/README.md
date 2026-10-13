# Opening-book rebound (independent reauthored experiment)

This directory reopens the old **MELON / STRAWBERRY opening-book question** without pretending the unrecovered historical bytes are available.

## What it is

`opening_book_rebound.py` is a deliberately small schedule consumer of the already-landed PRICE-PATH admission primitive:

- exact dependency: `../price-path-seed-budget/seed_budget.py` Git blob `7cbef20f942d78e9e2bea318c74dbe06ac2f0d13`;
- source crop: authored `PLANT WHEAT` on the **next** callback;
- target order: MELON, then STRAWBERRY;
- default quota: at most two successfully proposed plants of each target;
- opening window: purchase proposals only at steps `0..71`;
- default: disabled.

The adapter does **not** implement its own cash math, raw-slot allocator, fill inference, site legality, or returned-action checkpoint. Those all remain owned by `SeedBudget`. A quota advances only after `SeedBudget.apply()` returns `plant-proposed` from a real committed prior return plus newly observed seed stock.

That matters because the official interpreter executes unit actions before market orders. Buying a seed and changing a plant on the same callback is not a valid funding theorem. This rebound stages the buy on callback `t`, authenticates the actual outer return, observes fill on `t+1`, and only then asks PRICESEED to change the incumbent plant.

## What it is not

The original opening-book source/receipt was not recovered from Git. This directory is therefore labeled `independently_reauthored_not_historical_donor` in every proposal/apply report. It is **not** evidence that the historical candidate behaved this way.

There is no production/default/archive/Kaggle wiring here and no profit claim. Before any runtime activation, a separate current-main gate still needs natural engagement plus matched both-seat official-engine economics against the exact control and current dependency set.

## Focused checks

```bash
python -m unittest -v \
  revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/opening-book-rebound/test_opening_book_rebound.py
python -O -m unittest -v \
  revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/opening-book-rebound/test_opening_book_rebound.py
```

The suite locks dependency custody, disabled identity, two-callback purchase→fill→plant custody, returned-action rejection, fill shortfall, MELON→STRAWBERRY quota order, bounded opening window, and episode reset.
