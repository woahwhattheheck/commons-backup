# Complete-controller physical replay consumer

`physical_replay.replay_routes` binds offered **complete existing producer
continuations** to SABLE's unchanged T04 `oracle.simulate_bundle`. It returns
conditional owned-state results and actual whole-market-queue cash/inventory
transitions. No route generator, selector, simulator, probability model, or
policy default is added. Only independent speculative controller snapshots are
called; the live producer and input observation stay unchanged.

## Use with HAZEL and FIR

```python
from physical_replay import ReplayLimits, replay_routes
from oracle import Scenario, simulate_bundle  # Existing cloud-service-value module.

# This closure supplies the complete live producer, not only RouteQuote.orders.
def execute_offers(offers, observation):
    return replay_routes(
        existing_controller, [offer.route_id for offer in offers],
        observation, configuration, official_engine, simulate_bundle,
        scenarios={"known_shops": Scenario()}, end_step=718,
        limits=ReplayLimits(seconds=5, decisions=5000),
    )
```

The result is execution input for FIR's existing economic/search callbacks. It
is **not** HAZEL's ranking callback: that callback must return a route ID using
its actual objective. DATE and ROUTE-FLOW keep their own receipt/ranking split.
This report must not be passed off as a `CashScenario` whose nominal fixed-cost
orders all filled. Our recorder includes the actual successful fixed-cost
transactions too; an unaffordable HIRE, animal, or seed is not assumed paid.

Supply the original producer **before** its authoritative current action.
`route_ids` identify existing entries in its `R`; an alternative uses the
unchanged `_switch_ok` at the current step. The default deep copy is exercised
with the exact Arlene implementation. Other controller families must provide a
validated independent `fork_controller` callback. Future public-feature route
switches, weed responses, stock-sensitive sales and terminal settlement still
run in each copy. Merely replaying the raw route tape would omit those behaviors.

Each route/scenario case returns the delegated oracle `result`, all executed
`active_routes`, an action digest, and `market_rows`: complete orders, actual
cash, hire counts, own private inventory and market state immediately before
and after the market. Whole-queue cash reconciles exactly to the oracle's cash
gain. Rows are not per-order fill certificates: purchases and sales of the same
product can offset in the aggregate. The complete own terminal farm/private
state is retained in `result` for subsequent valuation.

No ranking is produced (`selection=null`). Incomplete, incompatible, malformed,
or failed cases have no scored cash gain. Ordinary dependency errors preserve
an incomplete record; external `BaseException` cancellation propagates. One
cooperative wall/decision budget covers the entire route/scenario grid. It can
overrun by an individual dependency call and is not a whole-agent timing limit.

## Model and horizon distinctions

The existing T04 oracle simulates the official owned-worker mechanics, ordering,
production, input availability, capacity, purchases and cash. It assumes
specified external inventory changes **before** the own market. These are not
simultaneous paired rival orders; rival cash remains null and rival public farms
remain frozen at their observed values. It must not replace ROUTE-FLOW's paired
receipt model without explicitly changing the question being tested.

Unknown shop reveals, weeds and external flows are hypotheses in the injected
`Scenario`, not future replay facts or calibrated probabilities. Default
`Scenario()` holds the observed shops, with no future external supply or weeds.
Recorded dates in that scenario are post-action end-of-day event dates, using
the existing oracle contract. This adapter adds no information-window model.

Cash before the final executable step is **not terminal economic value**.
For example, an installed sheep bundle can leave cash lower because its output
is still in the future. Use the returned productive state with FIR's economic
valuation, or an explicit terminal continuation. No promotion or winning claim
follows from a short cash prefix.

## Executed integration

The retained T10 decision121 observation was replayed through260 for actual
Arlene MAIN and YARN continuations. There are 140 projected decisions per route.
Each result matches direct invocation of the original T04 oracle in every field,
including actions, cash ledger, own farm/private state and market. Original
controller state and input observation remain unchanged. This is conditional
continuation testing, not a full game, a HAZEL226 observation, or a leaderboard
result. No game seed was initialized or reserved.

Under the explicitly unchanged-shop/no-rival scenario, MAIN ends with16,321 cash
and YARN with15,721, a600 capital difference at260. Both bundles install. The
actual241 queue is SELL FERTILIZER2, HIRE, HIRE, BUY_ANIMAL2, BUY_PRODUCT FERTILIZER3.
This is distinct from226's wool/feed/animal queue. The result is not a conclusion
that either whole policy is better. The separate15-method regression suite
covers actual paid versus rejected hires, independent snapshots, identical
scenario replay, partial budgets, cancellation, missing programs and unchanged
original inputs. `VALIDATION.json` binds the source and exact output bytes.

## Reproduce using existing inputs

Dependencies are not copied here:

* T04 `cloud-service-value/oracle.py`, Git blob
  `49640c27862d3d132c828fbafc6a8b4957527736`.
* Arlene `cloud-frontier-policy/next-panel/vendor/arlene.py`, SHA256
  `1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4`.
* Existing source-pack commit `7f92f6c0f4e3961be8109b2e3dc6da3e4e356d9f` includes
  `cloud-eval/evaluate.py` and its existing loader. Restore the normal sibling
  directory layout from `titan-pinned-source-pack-v2.zip` rather than exporting
  another source bank.
* Official engine `Kaggle/kaggle-environments` commit
  `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`, existing artifact10005621438.
* T10 `astra-dock-t10-evidence.zip`, member `source/evidence/decision-121.json`,
  file SHA256 `5a39be040a49e22747b96c1dc916e6071d04e5e58da45d62e2223b8f15c23e61`.

```sh
export TITAN_SOURCE_ROOT=/cloud/source/revenue/kaggriculture
export TITAN_ENGINE_DIR=/cloud/engine
export T04_ORACLE=/cloud/source/revenue/kaggriculture/cloud-service-value/oracle.py
export T10_OBSERVATION=/cloud/t10/source/evidence/decision-121.json
python -m unittest -v test_physical_replay
python check_existing.py --source-root "$TITAN_SOURCE_ROOT" \
  --oracle "$T04_ORACLE" --engine-root "$TITAN_ENGINE_DIR" \
  --observation "$T10_OBSERVATION" --end-step 260 --output physical-result.json
```

Source-only test discovery
explicitly skips the integration class when these external input paths are not
supplied; such a skip is not a passed engine check. The published validation was
executed with all four real dependencies. Full recorded queue/state evidence
is retained in `titan-capital-physical-replay-evidence.zip`, with its exact report
hash in the manifest. Original engine/Arlene/T04/T10 attribution is preserved;
these new consumer files use the repository's Apache-2.0 license.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
