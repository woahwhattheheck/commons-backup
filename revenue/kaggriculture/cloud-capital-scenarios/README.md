# Dated capital-route scenario selector

`dated_scenarios.py` supplies the single `selector(offers, observation)` callback
for HAZEL's existing `choose_before_action`. It reprices dated variable cash rows
from caller-supplied scenarios, preserves all other quoted costs and their order,
and selects a fully covered alternative only when its worst paired own-cash gain
is positive and its nominal ordered budget never becomes negative. It creates no
route, controller, scenario model, probability, or new simulation runner.

The first offer is the incumbent. Missing settlements remain unknown; they do not
become zero and the incomplete scenario is not dropped. Ties keep the incumbent.
This component does not change the selected TITAN policy.

## Callable and receipt contract

```python
from dated_scenarios import CashScenario, DatedSelector

selector = DatedSelector([
    CashScenario("declared-world", flows={
        "route-id": {(step, market_slot): signed_total_own_cash_delta},
        # Supply every offered route, for every SELL and BUY_PRODUCT row.
    })
])
choice = selector(offers, observation)
comparison = selector.last_report
```

Values are total cash for the full order, not a price to multiply by quantity.
SELL totals are nonnegative; BUY_PRODUCT totals are nonpositive. An explicit zero
is a completed zero receipt or cost. Each key is the original integer step and
zero-based market slot. Different routes require their own settlements even
when their orders occupy the same slot. Fixed animal, seed, land and labor costs
come from the original offer. Any claimed successful future fixed order remains
conditional on its quoted assumptions.

`compare_routes` also accepts JSON-shaped offers (`route_id`, `orders`). Each
order has `step`, `slot`, `order`, and the original `delta`. The JSON CLI accepts
`offers`, `observation`, and `scenarios`; scenario `flows` are route IDs mapped to
lists of `{step, slot, delta}`. Optional `minimum_gain` is a nonnegative strict
improvement threshold.

```sh
python -B dated_scenarios.py input.json
```

The report contains coverage, final nominal cash, minimum nominal cash, first
negative step/slot, and worst paired gain. Comparison is against the incumbent
in each same scenario, not a difference between unrelated absolute minima.

## Joined ROUTE-FLOW / HAZEL usage

ROUTE-FLOW supplies trajectories, DATE ranks them, and HAZEL retains its existing
route-selection seam. The complete worker/service programs remain in the
existing controller; `RouteQuote.orders` alone is only a market program.

```python
from dated_flow import evaluate_scenarios, as_cash_scenarios
from dated_scenarios import CashScenario, DatedSelector
from capital_routes import choose_before_action

reports = {}

def select(offers, observation):
    receipt = evaluate_scenarios(
        offers, observation, configuration, mechanics, public_scenarios,
        seconds=0.05,
    )
    reports["trajectory"] = receipt
    if not receipt["complete"]:
        reports["comparison"] = None
        return offers[0].route_id
    ranking = DatedSelector(as_cash_scenarios(receipt, CashScenario))
    chosen = ranking(offers, observation)
    reports["comparison"] = ranking.last_report
    return chosen

# Use the existing producer object, before its ordinary single action call.
outer = choose_before_action(
    existing_controller, observation, configuration, mechanics, selector=select,
)
```

Here `configuration`, `mechanics`, `public_scenarios`, `existing_controller` and
`observation` are the caller's existing inputs. The example's 50 ms cooperative
budget is an application setting, not a measured hard real-time guarantee.
Mechanics callbacks cannot be preempted. Retain both reports: the trajectory
records declared demand, quantities and rival receipts; DATE's report records
nominal own-cash comparison. HAZEL's unchanged outer report still labels its
original current-quote marks and does not embed the custom comparison.

No future shop is treated as already observed. A scenario containing a later
YARN store is a hypothetical continuation, not a runtime feature. The existing
MAIN-to-SHEEP seam remains at decision 226; changing its timing is not part of
this delivery.

## Reproduce

Python 3.10 or later; the runtime and unit suite use only the standard library.
Tests consume external original source files rather than vendoring new copies.

```sh
python -B test_dated_scenarios.py -v
python -B check_real_routes.py \
  --arlene /path/to/vendor/base/arlene.py \
  --hazel /path/to/cloud-capital-bundles/capital_routes.py \
  --mechanics /path/to/vendor/sell/mechanics.py \
  --output real-route-results.json
python -B check_flow_join.py \
  --arlene /path/to/vendor/base/arlene.py \
  --hazel /path/to/cloud-capital-bundles/capital_routes.py \
  --mechanics /path/to/vendor/sell/mechanics.py \
  --flow /path/to/cloud-capital-route-flow/dated_flow.py \
  --output flow-join-results.json
```

Exact inputs: Arlene SHA-256
`1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4`;
HAZEL source commit `3708a125158b6e39ffaf61b6e9e54b632eb2760e`, blob
`00abee3c99641eb0ab1729fd80e6f9a5c783f373`;
ROUTE-FLOW source commit `4e8224e15e3a9d470d3326aa3740b62befce8abe`, blob
`dcb9250711e5f672a7adfa8a7ec3191895f4feea`.
Arlene and extracted official mechanics came from the already-existing Actions
artifact `10030763484`, ZIP SHA-256
`68f78694fa56976fa1476ffd1d1fb6b3bfd4935392dfd0023a170c7efcd35e62`,
inside `carrot-cap-checkpoint.tar.gz`. No new exporter or workflow was created.
Both checkers record consumed mechanics identity in their result.

## Executed results and limits

23 unit methods pass, including 1,000 independently calculated integer budget
comparisons. The actual Arlene/HAZEL route join covers 928 market rows and four
both-seat selection cases. A constructed current-quote witness selects SHEEP
with +6,875 nominal cash; adding a declared later-WOOL-37 scenario gives -3,005
worst paired cash and retains MAIN. These are explicitly constructed inputs,
not saved match states or predictions.

The additional exact ROUTE-FLOW join uses a price/inventory-consistent constructed
market. Two routes, four explicit demand/rival scenarios and both positions
produce 16 matching final/minimum/first-negative cash records and 3,480 complete
variable-order settlements. Unit-budget and elapsed-budget exhaustion both
refuse conversion. All comparisons retain original route tables and make zero
parent action calls. The constructed conditional route difference ranges from
-5,556 with existing shops only to +8,293 with a hypothetical YARN store. Including
all four scenarios retains MAIN; it does not predict which world will occur.

The ranker-only benchmark (100 iterations) measured median 0.992 ms and maximum
6.091 ms, excluding imports and quote generation. The two newly composed
flow-plus-ranking calls measured 65.392 and 25.802 ms, also excluding imports and
HAZEL quotation, with the cooperative deadline disabled for measurement. These
are container measurements, not an entire-agent timing guarantee.

All original result fields are retained in the two JSON records. There are zero
new games, game seeds, selected-policy changes, uploads or leaderboard claims.
HAZEL's prior positive/negative game panels remain its evidence, not this
component's validation. Neither a nominal cash trough nor conditional market
settlements establish that workers can produce and deliver the assumed stock.
FIR's complete route evaluator and public-state scenario model supply those
separate inputs. Runtime worst paired own cash is not terminal win probability
or a rival-adjusted objective.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
