# ASTRA-SLOTLOCK — current market-pressure raw-row proof

This is an additive proof inside the existing `research/market-pressure` authority for the single TITAN V4 line. It does **not** revive the legacy V224 materializer or introduce a new runtime key.

## Live question

Current production ships `market_pressure=true`. The live pressure transform may compact known empty/zero sale-only slots behind positive SELL rows. That preserves row cardinality but changes which rival raw market row is lockstep-paired with our sale. The official engine processes each raw row per-unit: both players' current units are quoted from the same pre-commit inventory, then both units are committed.

Legacy V224 evidence was therefore directionally relevant, but its old `apply_v4` repair is not current ABI and must not be transplanted. This package tests the **current** theorem directly.

## Bound sources

The executable tests refuse source drift from these Git blobs:

- official engine `3c202c7ee921da239356789e266b694635103fc4`
- live pressure transform `7261674962d10fc8bc6af5ff73ff9212c40f61ad`
- production `main.py` `4a8cf7bcda1f0fea231a144692cb84a779a9e73e`
- production `titan_runtime.py` `6d9720f4aa1e6b46e92ee5183897074d8e9ea5a0`
- production `TITAN-CONFIG.json` `3a3bef83899d3010fad623b628d9e95d9978111b`

The tests also assert the live config still enables `market_pressure`.

## Why direct buys do not break the compaction theorem

The current compactor admits only `CARROT/TOMATO/STRAWBERRY/MELON/EGG/MILK/WOOL`. The official engine's direct `BUY_PRODUCT` grammar is only `WHEAT/FERTILIZER`; the sets are disjoint. Moving one of the admitted SELLs across an own empty row therefore cannot cross a rival direct buy of that same item. Rival actions on unrelated resources commute with the admitted sale price/inventory state. Same-item rival SELL units are the remaining lockstep coupling.

For those same-item rival SELLs, moving our sale earlier changes only relative sale timing. The compactor already requires a checked nonincreasing public quote curve far enough to cover the admitted own quantity plus the full default shed capacity. Under the engine's quote-both-then-commit rule, earlier own same-item units weakly improve own-minus-rival receipts.

## Executed proof

Run from this directory:

```bash
python -B -m unittest -v test_slotlock_oracle.py
python -O -B -m unittest -v test_slotlock_oracle.py
python -B slotlock_oracle.py
```

The standalone oracle exhaustively enumerates changed prefixes of length 1..3 using three representative curve families (`CARROT`, `STRAWBERRY`, `WOOL`) against asymmetric rival SELL/empty rows:

- 504 changed own prefixes
- 165,816 paired lockstep comparisons
- minimum own-minus-rival margin delta: `0`
- 78,560 strictly positive cases
- zero counterexamples

Separately, all seven admitted official price curves pass 2,100 adjacent nonincrease checks across inventory `I0-100 .. I0+200`; the smallest total drop across that 300-unit window is 15.

`test_slotlock_oracle.py` additionally imports the **live** `pressure_priority.py`, verifies its compactor matches the independent structural model, verifies WHEAT remains a barrier, and authenticates all five source blobs above.

## Disposition

**PROVED / NO CURRENT PATCH.** The current sale-only empty-slot compaction is not the legacy V224 deletion bug: it preserves cardinality, excludes same-item direct-buy coupling, and is margin-nonnegative on the source-bound lockstep model exercised here. Keep the current market-pressure family as the sole implementation.

This does **not** prove full-game EV, the economics of pressure ranking among nonempty SELL lots, arbitrary future market grammars, or safety after any source-pin drift. If any bound source changes, rerun rather than inheriting this result.

No runtime/default/archive/Kaggle change.
