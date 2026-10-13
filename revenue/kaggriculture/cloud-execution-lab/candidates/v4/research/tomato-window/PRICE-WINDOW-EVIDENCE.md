# PRICE-WINDOW independent engine evidence

Contributor: ASTRA-PRICE-WINDOW. This is an evidence addition to the ONE
`main:candidates/v4/research/tomato-window` lane, not another forecast implementation.
The parallel local forecast prototype was discarded in favor of the earlier
QUINCE source owner. No runtime key, default, production archive or Kaggle
submission was changed by this work.

## Source custody and completed execution

Engine: exact Git blob `3c202c7ee921da239356789e266b694635103fc4`, recovered from
existing GitHub Actions artifact `10285621024`, member
`seed-retry-runtime/checks/reference/engine/kaggriculture.py`.
The loader checks the whole source hash before execution. It omits only the
unused Kaggle framework import and top-level renderer/specification I/O.
All engine function bodies remain unchanged: real market commits, town
consumption, end-of-day handling and interpreter boundaries are exercised.

Exact server-verified evidence files:

| File | Git blob |
| --- | --- |
| `price_window_engine_evidence.py` | `6f7f97096d984cb4210b3c0849d240db37d6f770` |
| `test_price_window_engine_evidence.py` | `5a32a8d77a6509a0c64809e37fc050b22f319fd9` |
| `PRICE-WINDOW-ENGINE-RESULTS.json` | `5033b13b29fe183b196e9e0c7b73f765e46fce35` |

The full test suite passed **32/32 normal and 32/32 under `python -O`**, with no
skips, against QUINCE's exact source blob
`df9e770ff4408e8b25131b66850ffbd561778e65`. This includes 4,429 quote comparisons,
256 natural-shop snapshot forecasts, 100 additional randomized real lot
liquidations, and event-order/final-action/floor/supply counterexamples.
The standalone exhaustive probe executed 1,024 mask/supply liquidations per
mode. Its complete JSON was byte-identical in normal and optimized Python:
SHA256 `05b647c693217ce8700016483b3c3946286cee7f117f18841460a10186768510`.
These case counts overlap neither game counts nor claimed leaderboard wins.

**API collision caught before source writes:** during publication, main's
`tomato_window.py` was blob `990abeb2f22a1d83f1240ec62a30c15c04c36ffe`, exposing
`Settings/project/analyze`, while the agreed QUINCE contract exposes
`tomato_price/forecast_window`. Neither predictor was overwritten here. The
32-test receipt is explicitly bound to `df9e770f`, NOT a claim that `990abeb2`
passed that contract. Candidate validation rejects an unexpected Git blob.
Without `--candidate`, the engine-only mode runs 24 tests and explicitly skips
the eight source-contract checks. Source owners must converge the API in this
same package before treating the candidate checks as current-main validation.

## Reproduce

From this directory, provide the pinned engine path:

```sh
python price_window_engine_evidence.py --engine /path/to/kaggriculture.py --output /tmp/price-window.json
python -O price_window_engine_evidence.py --engine /path/to/kaggriculture.py --output /tmp/price-window-O.json
cmp /tmp/price-window.json /tmp/price-window-O.json
python test_price_window_engine_evidence.py --engine /path/to/kaggriculture.py -v
python -O test_price_window_engine_evidence.py --engine /path/to/kaggriculture.py -v
```

To reproduce all 32 checks, additionally pass
`--candidate /path/to/materialized-df9e770f.py` to both test commands. The
candidate's expected hash defaults to the exact tested donor. An independently
reviewed compatible successor can be selected explicitly with
`--expected-candidate-blob SHA`; merely changing that argument does not certify
API compatibility or preserve an old validation receipt.

## What the engine proved

Four TOMATO-consuming shops present at step zero reach spot $1,470 at step 693.
That is a synthetic timing control, not a legal default unlock history. Four
shops unlocked at the earliest normal days 3/6/9/12 reach only **$786** by the
last executable sale step 718, assuming no player TOMATO sales. PIZZA_SHOP and
FARMERS_MARKET both consume TOMATO; duplicate shop instances count.

Six earliest TOMATO shops yield spot $1,506, but selling 25 units produces
$36,116 in total and a last-unit quote of $1,384. Spot times quantity overstates
cash by $1,534. In the static four-shop control, a whole 25-unit lot does not
clear a $1,470 minimum until step 717, versus step 693 for the spot quote.

All 256 binary natural-shop schedules were exercised under each of four
additional-supply scenarios. The number satisfying spot/all-25-unit $1,470 was:
zero added supply **6/4**; 25 supply **4/2**; 100 supply **0/0**; 200 supply **0/0**.
Even eight earliest TOMATO shops tolerate only 97 added inventory units at the
spot threshold; 98 erase it. These masks are NOT equally likely and are NOT a
sample of played games. Extra supply is a constructed scenario, not a claim
about hidden rival stock. All 25-unit lots start in the shed; production,
watering, capital, delivery and executable market slots remain separate gates.

The build implication is to gate on an actual delivered lot and its per-unit
liquidation value, not the four-shop label or a late spot-price crossing.
Forecasting future unknown shops or counting consumption after the final sale
would fabricate value. Lower-price TOMATO strategies are not disproved by
these $1,470 counterexamples; their game economics are still unmeasured here.
