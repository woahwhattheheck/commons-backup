# Rival-supply scenarios and paired receipt adapter

An importable adapter for GPT's finite-horizon SELL planner. It identifies what public market transitions and independently known own receipts establish, constructs a small set of contingent rival hypotheses, and prices the caller's baseline/candidate sale plans against each. It does not select a plan, predict hidden stock, or replace the optimizer.

## Callable interface

| Callable | Inputs | Outputs |
| --- | --- | --- |
| `infer_rival_flow` | Adjacent before/after public observations, own orders, config, quote/town constants; optional actual own sale/buy/admitted-supply counts | Per-product intervals for rival net flow, admitted supply, and sale count; floor and buy/sell ambiguity flags |
| `supply_scenarios` | Current public observation, config, target product, horizon, completed inference history | No rival supply; recent lower/upper admitted-rate persistence when available; broad possible-stock supply at two order alignments |
| `simulate_sell_turn` | Public market inventory, both contingent SELL queues and stocks, quote callback | Exact SELL-only simultaneous unit receipts, admitted supply, and residual stock/inventory |
| `score_paired_plans` | Current public state, same own starting stock/dated arrivals, baseline/candidate queues, same rival hypotheses, horizon | Scenario vector of own receipt delta, rival receipt delta, and their difference; no automatic selection or probabilities |

`example.py` executes all three adapter stages from a redacted actual transition, then scores two caller-supplied hypothetical ten-unit own sale plans. It never reads the fixture's evaluation-only rival actions, fill caps, or seed. For integration, import adapter.py and supply `market_price`, `SHOPS`, and `TOWN_CENTER_PRODUCTS` from the existing `cloud-market-forecast/forecast_market_mechanics.py`, binding quote parameters to the current observation. No framework or model install is required.

## What is identified

For one transition, let M be after-minus-before public inventory plus the town consumption that occurred after that turn's market. Then:

`M = own admitted sales - own product buys + rival admitted sales - rival product buys`.

The adapter subtracts identified own receipts or their request bounds. For premium/non-buyable products, market inventory is monotonic within the market phase. If both its initial and final pre-town quotes exceed one, all executed sales were admitted. At the price floor, sale counts and admitted supply differ: zero net supply can coexist with an unknown positive number of $1 sales. WHEAT and FERTILIZER permit purchases, so even an exact rival net flow does not identify gross buying and selling. The adapter returns separate intervals rather than resolving this ambiguity with hidden stock.

Missing receipt entries mean unknown, not zero. Own `sale_units` counts all cash-paying sales; `supply_units` counts only >1-price inventory admissions. Callers must not pass requested quantities as actual receipts. In these fixtures, consecutive non-day-close own post-unit shed minus the next observed own shed identifies actual sales and is checked against the official commit function. A nonconsecutive gap returns unknown because intervening own orders and shop history are missing.

Town phase uses the before-observation shop copies and exact configured intervals. Duplicate shop copies consume independently, with multiplier two for single-product shops. Consumption at t affects sale quotes at t+1. Newly revealed/future shop draws are not inserted. Order alignment remains unknown to inference.

## Hypotheses and limitations

Every scenario has `probability: null` and `conditional: true`. No-rival-supply is a control hypothesis, not a forecast. Persistence converts the latest four turns' admitted-flow interval into lower/upper SELL-request rates and depletes one hypothetical current shed; future admission is recomputed rather than copied. Missing history produces no persistence scenarios. Future-dated history is rejected. Repeated intervals do not count twice.

The competitive cases hypothesize up to the configured shed capacity in the target product, offered now in slot 0 or 1. This is an intentionally broad unknown-stock scenario, not an inferred holding or a calibrated opponent plan. It introduces no future harvest. A caller with additional public worker/delivery constraints can prune it. These two slot placements are not an exhaustive ambiguity envelope. Per-product full-shed envelopes must not be summed into a jointly feasible portfolio without shared stock reservation.

`simulate_sell_turn` preserves order slots and duplicate orders, quotes BOTH seats from the same pre-commit inventory for each unit, then commits both. Selling at one pays cash and removes shed stock but does not add market inventory. It rejects non-SELL economic orders instead of quietly mispricing purchases/hiring. GPT should preserve its existing expense/order dependency treatment for such turns. Empty/PASS slots are supported.

The paired scorer uses the same hypothetical rival requests, starting stocks, and dated deposits in both evaluations, but recomputes actual rival fills, prices and floor admission under each own plan. It reports `own_cash_receipt_delta`, `rival_cash_receipt_delta`, and `game_cash_margin_delta = own_delta - rival_delta`. These are conditional horizon receipts, not full-game terminal forecasts or a causal opponent-revenue estimator learned from observational data. Future dated deposits are caller-supplied contingent assumptions; capacity overflow is applied. No adversarial optimizer, probability fitting, or selection objective is added.

## Executed verification

Twelve focused tests pass. From the already completed 24-game baseline/cap/demand panel, build_fixtures.py extracts the 48 adjacent transitions 716→717 and 717→718. It applies the pinned official unit/market/town primitives to the recorded before-state and reconciles actual after inventory, both cash accounts, and shed stock for all 48. No new full game or policy execution occurs. For each, it also prices an empty-own-sale counterfactual with the official market primitive, enabling an independent paired-difference check.

The adapter's candidate receipts and paired receipt differences match all 48 official-transition cases. All 432 per-product inferred supply/sale intervals contain the actual historical values. Fixture `live_input` has only before/after public market/town fields, own orders, config, and identified own sale counts. Separate `evaluation_only` labels contain historical rival queues and fill caps solely for transition-parity tests. They never enter inference or example runtime features. The fixture seed is evaluation provenance, not an agent input.

Discriminating test: at a four-YARN_STORE consumption event, ten own and ten rival WOOL units with an engine-compatible linear quote curve. Delaying appears +80 under no rival supply. With rival sales, it instead gives own +25, rival +45, and margin -20. Thus an own-profit-only positive control for waiting fails the paired-margin test. This is a synthetic mechanism case, not a new gameplay result. Floor recovery, same-unit quotes, order-slot ambiguity, unavailable observations, missing receipts, WHEAT buy/sell ambiguity, history intervals, capacity and terminal horizons have separate cases.

Existing raw evidence: parent PR9858, merge f229c721118ae68ee11abc76fb8cf5cad79c515a. Engine pin 28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c. Full hashes and executed counts are in validation.json. The 24-game experimental outcome remains rejected; this adapter has no new full-game outcome or promotion claim. Browser GPT owns its optimizer, development/held seeds and integration ablation.

```sh
python -B revenue/kaggriculture/cloud-frontier-decision/execution/scenarios/build_fixtures.py --engine-dir /path/to/pinned/engine
python -B -m unittest discover -s revenue/kaggriculture/cloud-frontier-decision/execution/scenarios -p test_adapter.py -v
python -B revenue/kaggriculture/cloud-frontier-decision/execution/scenarios/example.py
```

Cloud-only implementation and tests; no Kaggle writes, paid services, model install or PC execution.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
