# Conditional dated market receipts

This directory supplies the market-flow producer for HAZEL's complete route quotations and DATE's existing dated-cash selector. It does not add a second selector, controller, route generator, search kernel, game runner, or default agent.

## Callable interface

```python
from dated_flow import Scenario, evaluate_scenarios, as_cash_scenarios
from dated_scenarios import CashScenario, DatedSelector

# offers are HAZEL RouteQuote objects for the same current public observation.
# mechanics is the existing pinned mechanics/engine module.
report = evaluate_scenarios(
    offers, observation, configuration, mechanics,
    declared_scenarios, max_units=100_000, seconds=0.2,
)
if report['complete']:
    selector = DatedSelector(as_cash_scenarios(report, CashScenario))
    selected_id = selector(offers, observation)
    # Keep report AND selector.last_report in the consuming evidence.
else:
    selected_id = offers[0].route_id
```

Use the resulting DATE callback through HAZEL's existing `choose_before_action(..., selector=...)` seam. The original controller is still called normally once by its owner. `example_route_flow.py` executes the complete source join without invoking a parent action. HAZEL's outer diagnostic still describes its original current-quote marks; DATE's `last_report` and this trajectory report are separate evidence and must not be relabeled as that old quote screen.

`Scenario(name, rival_orders={}, shop_additions={})` specifies conditional future flows. Rival orders use integer turn keys and exact market-slot queues. Use explicit PASS entries to preserve slots occupied by rival fixed-cost orders; their cash costs are outside this market-only model. `shop_additions` names shop instances first active BEFORE a supplied future turn. Duplicate shops are meaningful. The caller supplies the scenario family and must respect the actual public reveal schedule when modeling possible futures. There is no hidden seed, private opponent inventory, shop oracle, inferred probability, or built-in calibration.

`value_route` retains own and rival market receipts/spending, fixed costs from the offer, nominal cash trough, final shared market inventory, and a signed total for every dated SELL/BUY_PRODUCT row. Explicit zero quantities retain explicit zero rows. `as_cash_scenarios` constructs DATE's exact `CashScenario(name, flows={route_id: {(step, slot): signed_total}})` schema without ranking. DATE currently compares nominal OWN cash; relative-margin consumers must also use the separately retained rival net effects.

## Meaning and limits

Supplied trade quantities are **assumed to execute**. The producer reprices them under shared supply and declared demand; it does not certify that the physical route produces the goods, that every purchase fills, or that rival cash and stock support the declared flow. Negative nominal own budgets remain visible, not silently funded. HAZEL's dated fixed animal/seed/land/labor costs and order identities are preserved. Later controller route changes and physical worker service are not replayed here.

The implementation preserves simultaneous pre-commit unit quotes, post-buy inventory pricing, exact slot order, floor-price sale non-admission, town consumption after all market slots, duplicate-shop demand, and the last executable turn `episodeSteps - 2`. It calls the supplied source's `market_price`, market parameters, and shop catalogue rather than substituting a linear price model.

The shared cooperative budget covers all route/scenario pairs. Missing, invalid, nonfinite, or incomplete inputs return no consumable vector; do not drop the unfinished scenarios and rank only the survivors. The engine's 99,999-unit per-slot ceiling is retained. A delegated price callback cannot be preempted, and component timing is not a whole-agent deadline guarantee.

## Executed validation

18 focused methods pass, including 96 comparisons of own cash, rival net market cash and the entire inventory against the pinned official market-plus-town phases. These cases use explicitly stocked synthetic states; they are not full games. Both player positions, floor non-admission, duplicate demand, post-buy prices, configured prices/intervals, terminal turn, incomplete budgets and invalid-flow negatives are represented.

The separate actual-source join uses unchanged Arlene `1dc166ae`, HAZEL `3708a125` and DATE `206e01c2`. Eight route/scenario pairs and all 1,740 variable cash rows reconcile exactly with DATE's final cash and ordered minima. The checkpoint is explicitly constructed, not recovered from HAZEL's historical losses. Four declared scenarios change future shop composition and rival flow. MAIN is retained because SHEEP's worst paired nominal own-cash difference is -11,068; one no-rival/future-YARN scenario instead favors it by +5,392. These are conditional marks, not realized game scores or a strength improvement.

The final source's complete eight-pair trajectory took 86.9 ms in this cloud container on one measurement. No parent action was called; original routes and inputs remained unchanged. No new gameplay panel, held seeds, hosted result, source-default promotion, Kaggle upload or provider spending occurred. `RESULTS.json` records exact source identities, numerical comparisons and deterministic receipt digests. The commands below regenerate the full per-order receipts.

## Reproduce with the existing source road

Use the unchanged source artifact `10030763484` and engine artifact `10005621438`; no new workflow/exporter is needed. Engine ref: `Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`. The loader requires all three engine files to exist before execution and performs no download in this use.

From repository root, with `ENGINE_DIR` pointing at `kaggriculture.py`, `kaggriculture.json`, and `utils.py`:

```sh
ROOT=revenue/kaggriculture
python3 -B "$ROOT/cloud-capital-route-flow/test_dated_flow.py" \
  --engine-dir "$ENGINE_DIR" \
  --loader "$ROOT/20260907-offline-agent/evaluate.py" \
  --report /tmp/route-flow-engine-results.json

python3 -B "$ROOT/cloud-capital-route-flow/example_route_flow.py" \
  --engine-dir "$ENGINE_DIR" \
  --loader "$ROOT/20260907-offline-agent/evaluate.py" \
  --arlene "$ROOT/cloud-frontier-policy/next-panel/vendor/arlene.py" \
  --capital "$ROOT/cloud-capital-bundles/capital_routes.py" \
  --dated "$ROOT/cloud-capital-scenarios/dated_scenarios.py" \
  --output /tmp/route-flow-source-join.json
```

For the exact historical join, restore HAZEL `capital_routes.py` from commit `3708a125158b6e39ffaf61b6e9e54b632eb2760e` and DATE `dated_scenarios.py` from `206e01c2f742ae5f4e8d6b909cc496da34e3fd3c` in the isolated checkout; their exact blobs are in RESULTS.json. New code in this directory is Apache-2.0. Imported engine, route and peer components retain their existing source and license attribution.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
