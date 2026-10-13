# MEASUREMENT.md — replay evidence for r04_shop_first

All measurements from Kaggle replay `ep-108114108.json`
(v3 56159263, −6,938 vs QQ Farming, SHOP-FARMER archetype),
cross-checked against eps 108124129 and 108114745.

## The shop tick (mechanism confirmed in-replay)

Step 341 → 342, opponent (QQ Farming):
- step 341: shed = {WOOL: 24, STRAWBERRY: 8}, money = $9,957, policy action = []
- step 342: shed = {} (emptied), money = $17,050 (+$7,093)

The engine auto-buys shed inventory outside the market: no policy SELL was
issued, yet 32 units cleared and $7,093 credited in one transition
(≈$222/u blended). The replay records the procurement as synthetic SELL rows.

## Shop buy prices vs market quotes (autopsy-measured)

| Product    | Shop $/u | Market $/u (step-400 quote) | Multiple |
|------------|----------|-----------------------------|----------|
| WOOL       | 123      | 1.93                        | 64x      |
| STRAWBERRY | 92       | 2.04                        | 45x      |
| MELON      | 79       | 1.67                        | 47x      |
| EGG        | 52       | 0.53                        | 98x      |
| TOMATO     | 50       | 0.71                        | 70x      |
| CARROT     | 49       | 0.48                        | 102x     |
| FERTILIZER | 47       | 0.45                        | 104x     |
| WHEAT      | 42       | 0.43                        | 98x      |
| MILK       | 40       | 0.01                        | 4000x    |

Our d27–29 bulk market dumps realize ~$0.6–0.66/u; our full-game average
market realization is $0.59/u ($69,860 / 118,294u). Every shop price is
60–4000x better per unit.

## Tick cadence

37 detected major procurement ticks; modal inter-tick gap 24 steps (matches
the pinned config default `townCenterSellInterval=24`). Minor 4-step ticks
exist but are not separately modeled (conservative).

## Tick size

The confirmed tick cleared 32 units (24 WOOL + 8 STRAWBERRY) — the anchor
for the per-tick per-product cap and the reserve floors.

## Shop demand finiteness

Observed full-game shop receipts: opponent ~$73,208 (25+ ticks) + us
~$18,565 ≈ $92k. Model demand cap: $100,000 (rounded up).

## Pinned-engine absence (verified)

- `reference/engine/kaggriculture.py::_town_consume` only decrements *market*
  inventory (demand-side consumption); no shed-procurement code path exists.
- `town_procurement.py` (v4 tree) is BUY-side only (retiming our own WHEAT
  purchases); it never prices or executes shed buys.
- Therefore no pinned-engine gate can measure this lane; see GATE-DESIGN.md.
