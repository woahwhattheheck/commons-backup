# Observation-only crop market forecast

`forecast_market(observation, configuration, horizons, *, contracts=None,
buffered_harvest_delay=None)` projects visible existing crops on both farms at
explicit **absolute market-sale action steps**. It uses ROWAN's exact production,
fertilizer, harvest and liquidation contracts plus extracted official pricing
functions. It reads no future shops, hidden seed, opponent private stocks or replay
labels. There is no policy selection, crop-cap change or new game simulation here.
FLORA owns integration and ablations.

## Interface

Place this directory on the Python module path and import `forecast`. The two
runtime dependencies are `forecast_events.py` and `forecast_market_mechanics.py`.
`contracts=None` uses the exact pinned ROWAN module; alternatively supply a module
or dictionary containing `production_events`, `harvest_contract`,
`fertilizer_contract`, `liquidation_window` with the same signatures. This lets
FLORA share its existing contract instance without duplicating event math.

```python
from forecast import forecast_market, market_price
result = forecast_market(obs, configuration, horizons=[sale_step], contracts=None)
row = result['frames'][0]['products']['STRAWBERRY']
# All three are scenario quotes, not calibrated confidence bounds.
quotes = row['price_scenarios']  # floor, base, ceiling
```

Each `frames[]` entry has `realization_step`, `realization_day`, exact current-copy
town-demand counts and `products`:

| Field | Meaning |
|---|---|
| `own_supply.observed_held` | Own currently visible tile-held units, possibly immature; not shed stock. |
| `own_supply.guaranteed` | Zero guaranteed future crop sales. |
| `own_supply.care_possible` | Maximum new accepted crop yield across the declared scenarios. |
| `own_supply.harvest_possible` / `sale_possible` | Maximum conditional harvested / market-arrived units across scenarios. |
| `own_supply.conditional` | Full per-scenario generation, clipping, held, harvest, decay and sale counts. |
| `opponent_public_supply` | Opponent observed held stock and the same conditional public-crop scenarios. No private inventory read. |
| `shop_copy_demand` / `town_center_demand` | Separate known-copy and center consumption in `[now, sale_step)`. |
| `price_scenarios.floor/base/ceiling` | Minimum / maintained-buffered / maximum scenario quotes. Base is not an expected value. |
| `scenarios[name].inventory_delta` | Admitted conditional crop market supply minus known town consumption. |
| `scenarios[name].conditional_crop_sale_units` | Cash-paying sale count, including price-1 sales. |
| `scenarios[name].conditional_crop_market_supply_units` | Units admitted to market inventory at executed price >1. |
| `scenarios[name].floor_sale_units` | Sales that pay 1 but add zero inventory. |
| `own_supply.conditional[name].market_supply_units` | Own admitted supply, distinct from own `sale_units`; opponent partition uses the same field. |
| `conditional_sale_timeline[name][product][]` | Dated batches with `sale_units_by_seat`, admitted `market_supply_units_by_seat`, and conditional cash. |
| `crop_witnesses[]` | Per-seat/tile contributions and exact ROWAN event/fertilizer/harvest contracts. |

Animal products are separate from the projected crop products. For other trades
in the same crop, combine dated sale batches and exogenous consumption and replay
`project_sale_timeline`; do not add raw sale counts to a final inventory. Then call `market_price(product, inventory, obs['market'].get('params'))`.
Do not add the old approximate town-demand term a second time. The all-product
output permits composition; animal products currently have **zero projected animal
supply**. This module does not forecast future planting or choose a static/dynamic
crop cap. FLORA can evaluate that separately.

## Three conditional scenarios

- `no_future_work`: no new water/fertilizer/harvest/sale; observed flags still apply.
  Crops can die or decay; future sale supply is zero.
- `maintained_buffered`: daily water, only currently observed fertilizer coverage,
  harvest near capacity/decay/full one-time growth with a configurable service delay
  (default half a day). Delays can forfeit production through clipping/decay.
- `fertilized_prompt`: future water/fertilizer availability assumed, with prompt
  ongoing harvesting and full one-time growth. This is an optimistic service case.

Maintenance cannot start before the closest currently visible worker could reach
that tile. Later service/prepositioning is conditional. Each tile is evaluated
independently: shared labor, cash, fertilizer inventory and shed capacity are NOT
reserved. The scenarios are therefore not a globally feasible action schedule.
No supply is asserted to sell perfectly; crop harvest and market arrival are separate
counts. Transport uses ROWAN's explicit DROP/SELL versus next-day automatic-deposit
window, capped by the last actionable step. No final-refresh cash is fabricated.

Known shop copies consume independently, including duplicate pizza shops and doubled
single-product shop consumption. Intervals come from configuration; center demand
excludes fertilizer. Consumption can drive inventory negative, as the engine allows.
Town consumes after market actions, so a quote at H includes consumption before H,
not H's later consumption. Scenario sales at H are included in the quote as
post-supply inventory. The quote is not sequential order-fill revenue; a large sale
must be repriced per unit by the integrating market policy.

## Verification and actual-state cases

```bash
python -B revenue/kaggriculture/cloud-market-forecast/test_forecast.py
python -B revenue/kaggriculture/cloud-market-forecast/test_engine_cases.py /path/to/pinned-engine-cache
python -B revenue/kaggriculture/cloud-market-forecast/run_cases.py
```

Twelve focused contract cases and four direct-engine primitive comparisons passed.
The two actual public leader observations are frame 224 (day 9, hour 8) and frame 430
(day 17, hour 22) from ROWAN's pinned episode 106392861. The fixtures contain current
observation only. Current tomato/strawberry prices 68/166 and 94/176 are preserved;
no later replay actions, prices, outcomes or shop labels enter the live call.
[RESULTS.md](RESULTS.md) separates those observed facts from forecast scenarios.
No performance win or leaderboard claim follows from these primitive checks.

Reproduce the bundled mechanisms with `build_mechanics.py /path/to/kaggriculture.py`.
It checks the engine Git blob and ROWAN SHA-256 before extracting/embedding the
exact reviewed definitions. `SOURCE_MANIFEST.json` records source and file hashes.

## Schema 2: sale count versus admitted market supply

The call signature and existing fields remain, but `schema` is now 2 and inventory
calculation is corrected. Each conditional batch is processed at its actual sale
step, with known town consumption before that step. A floor-price sale pays cash
and removes stock but does not increase inventory. Only above-floor sales carry
forward as cumulative supply. Older aggregate outputs are superseded by this
mechanics correction; they must not be interpreted as schema-2 results.

For each product and step, visible per-seat batches are flattened and assumed
aligned at one market order slot. Both seats quote the SAME pre-commit inventory
per unit, then both commit. This is an explicit alignment scenario: actual order
indices, cross-product interleaving and private orders are unknown. Neither the
conditional cash nor the final quote claims arbitrary one-side front-running.
`project_sale_timeline(initial_inventory, sales, horizons, quote, demand_before)`
exposes that bounded calculation; `sales` maps step to `{seat: quantity}` and
`demand_before(step)` supplies cumulative exogenous consumption before the step.
Snapshots and dated output distinguish cash-paying units from admitted supply.

To remove or alter a modeled own stream, replay its timeline: floor-dependent
admission of the opponent's sales can change too. Simply subtracting own sale
counts, or holding all previously admitted opponent supply fixed, is not an exact
joint counterfactual. Scenario supply remains conditional on the existing
transport, care and capacity assumptions; no future hidden orders are introduced.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
