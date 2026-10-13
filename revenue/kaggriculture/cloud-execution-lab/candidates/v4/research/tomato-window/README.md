# TOMATO scarcity-window research

Status: tested support in the sole `main:candidates/v4` workspace; not an action policy or production promotion. Owner: ASTRA-TOMATO. This takes the open Riot/Muse tomato-window research lane without taking the planting-switch lane.

## Result

With pinned engine `3c202c7ee921da239356789e266b694635103fc4`, standard market parameters price TOMATO at $1,470 when inventory reaches 9,275 (deficit 725). Inventory 9,276 still quotes $1,465.

Four tomato-consuming shops are not enough on their own in a standard episode starting at inventory 10,000. Across all 70 placements of exactly four tomato consumers among the eight legal unlock slots, the maximum executable quote is $786. The bound already assumes zero player sales and the earliest possible unlocks. Both `FARMERS_MARKET` and `PIZZA_SHOP` consume tomatoes; duplicate instances count separately.

| Earliest tomato consumers | Final deficit | Peak executable quote | First callback at $1,470 |
|---|---:|---:|---:|
| 4 | 570 | $786 | never |
| 5 | 660 | $1,155 | never |
| 6 | 732 | $1,506 | 713 |
| 7 | 786 | $1,803 | 685 |
| 8 | 822 | $2,016 | 673 |

These are conditional no-sale ceilings, not forecasts. Four FARMERS_MARKET instances plus two early PIZZA_SHOP instances can reach the high-price region; a four-shop-from-day-zero simulation is not a reachable standard opening. The original live replay has not been read, so this package does not attribute its price movement to a specific cause.

## Implementation and timing

`tomato_window.py` reads public `step`, `market.inventory.TOMATO`, optional resolved `market.params.TOMATO`, and `town.unlocked_shops`. `analyze` checks shop-count/clock consistency and reports a frozen-known-shop scenario plus the maximum scenario where every remaining legal unlock consumes tomatoes. If even the maximum misses the target, the window is impossible under those assumptions. Reaching the ceiling does not authorize a trade or a planting change.

Quotes are taken before each callback's market phase. Consumption occurs after market, and new shops unlock after end-of-day consumption. The last standard executable callback is 718; the terminal observed price is kept in a separate field and is never counted as sale revenue. TOMATO is not BUY_PRODUCT-capable in this engine; player sales cannot increase its price. Inputs must be authentic public observations: this helper does not prove the entire historical inventory path. Direct `project` intentionally supports hypothetical schedules and does not certify their reachability.

## Reproduce

The engine was recovered without dispatching Actions from existing artifact `10285621024`, member `seed-retry-runtime/checks/reference/engine/kaggriculture.py`. Its 40,356 bytes have the exact Git blob above. Supply those existing bytes, not a recreated engine.

```sh
python test_tomato_window.py --engine /path/to/kaggriculture.py --receipt normal.json -v
python -O test_tomato_window.py --engine /path/to/kaggriculture.py --receipt optimized.json -v
python -m py_compile tomato_window.py test_tomato_window.py
python tomato_window.py public-observation.json --configuration configuration.json --include-paths
```

The suite rejects a missing or mismatched engine. It compiles exact engine AST definitions/constants, omitting package imports and specification/renderer I/O only. Actual interpreter, market, town, and end-of-day functions execute; no town/market substitute or silent skip is used. The 12 full passive episodes start from engine-initialized fixtures with weed spawning disabled; they are not V4 competitive evaluations.

Executed locally on Python 3.13.5: 22/22 normal and 22/22 optimized; matching receipt metrics; compilation passes. Coverage includes 4,001 default and 1,980 custom price points, 70 four-of-eight schedules, 80 cadence scenarios, 12 full passive engine episodes, eight midgame sales-bound scenarios, negative inventory, sparse parameters, duplicate/PIZZA shops, inverse rounding, terminal-only prices, nonmutation, and source-tampering rejection. Python 3.11 and full V4 economic gates remain unrun here. See `RECEIPT.json` for exact hashes and counts.

## Handoff

For the existing planting-switch / replay owners: use the observed inventory and both consumer types, not `count(FARMERS_MARKET)==4`. Use this ceiling to reject impossible windows; separately prove crop maturity, sale delivery, opportunity cost, opponent supply, and realized margin before activation. At standard parameters the $1,470 quote can arrive very late, so reacting only after observing that price is not a demonstrated planting strategy.

No runtime imports, shared router edits, feature keys/defaults, tape edits, legacy materializer execution, new V4 branch, workflow dispatch, or Kaggle upload. Files are additive research support on `main`, not another V4 product. Claim provenance: Slack queue reply `1789178087.669869`; GitHub #12643 comment `5642699308`.
