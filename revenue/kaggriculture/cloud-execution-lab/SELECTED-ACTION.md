# Generic selected-action SELL callable

For a callable that also projects the caller's selected worker actions in engine order, see [ORDERED-SELECTED-ACTION.md](ORDERED-SELECTED-ACTION.md). It consumes the landed ATLAS projection and WREN reservation additions while retaining this generic interface.

`selected_action_sell.SelectedActionSell.transform` schedules SELL quantities over the action the caller already selected. It imports no Arlene module and constructs or calls no production controller. The accepted `scheduler.py` and its completed panels remain unchanged and separate.

```python
from selected_action_sell import SelectedActionSell

sell = SelectedActionSell()  # Retain one per actor/match for public rival history.
action = sell.transform(
    obs, cfg, selected_action,
    post_unit_shed=projected_private["shed"],
    projection=projection,
    arrival_contract=contract,
    reservations=reservations,
    fallback_action=valid_selected_fallback,
)
```

`transform(obs, cfg, selected_action, **kwargs)` is also exposed as a stateless module function; the class has `act = transform`. All return a complete action dictionary. Inputs are copied. `sell.diagnostics` reports the chosen conditional plan, scenario values, feasibility, or fallback reason. The caller still performs exactly one authoritative production pass.

## Caller projection

The post-unit shed and contract must describe the **same selected unit stage**. The transform neither replays a hidden baseline tape nor guesses alternative errands. Supply the selected producer's conditional, lossless shed changes through a horizon of at most eight future steps, shortened wherever the caller's continuation becomes unknown:

```python
projection = {
    "observed_step": 669,
    "end_step": 671,
    "stock_events": [
        {"step": 671, "phase": "after_market", "product": "MILK",
         "quantity_delta": 7},
    ],
    "future_market": {
        670: [],
        671: [["SELL", "STRAWBERRY", 3]],
    },
}
```

The numbers above illustrate the schema. They are not the retained669 producer trajectory. `future_market` maps absolute steps to already-selected conditional market orders. Missing steps mean no planned market orders; they do not authorize invention of a future route. Current market orders always come from `selected_action`.

`stock_events` contains signed **non-market** shed changes: positive requested DROP/EOD deposits, negative PICKUP/PLACE/input withdrawals. Include observed carried goods at their actual planned deposit date. Exclude current unit-stage changes, which are already in `post_unit_shed`. Exclude all SELL and BUY effects, which the ledger applies from market orders. Deposits must retain the requested whole quantity even if a full shed would discard some of it; otherwise a spill disappears from feasibility. Project only known selected actions and observed stock; no future RNG, opponent private stock, or rejected opportunities.

`before_market` deposits need space before that step's SELL. `after_market` deposits can use space freed by that step's SELL. EOD719 has no final sale opportunity in the pinned720-state engine; the last decision is718. Terminal carry value is zero only at the actual end. Short planning horizons retain the accepted optimizer's receipt-based continuation value.

## Committed producer contract

Pass T08's `build_arrival_contract(...)` output directly as `arrival_contract`. Its input snapshots must have been obtained relative to the caller's **post-unit** observation. The transform consumes `capacity_events` and reserves their `pending_capacity_units`, by absolute `step` and `phase`. The complete `units_total` and already-realized portion remain separate. `units_incremental` is economics metadata and never replaces whole-lot capacity.

Pending events must be contingent, with `guaranteed_stock_units: 0`. They reserve space cumulatively after their date; they never increase sellable inventory or modeled receipts. `realized_carried` is already in the observation, so it is not added a second time. Include that physical carried inventory once in the caller's stock projection. Stable `(owner, errand_id)` identifies duplicate commitment rows. Abort and completion are represented by the next fresh caller contract, not a persistent guessed arrival table in this transform.

The producer pins are T08 `021c0e60cc2af15a6606e51caddb870d1f680482`, Claude committed producer `1cd98ab36c5d2a5a5ab95e64607e1eacb055687f`, and retained ablation `39e439aced4406bc538bd361e9627f9e1c0a4254`. Exact targeted sources and hashes are under `reference/selected-action/`.

## Operating reservations and order positions

```python
reservations = {
    "stock": {"WHEAT": 12, "MILK": 2},
    "cash": [{"step": 671, "phase": "before_market", "minimum": 300}],
    "market_slots": {670: [0]},
    "order_cost_bounds": [{"step": 670, "slot": 0, "max_cash_cost": 300}],
}
```

Stock minima are shared standing minima over the supplied horizon; signed projection withdrawals describe actual future input use. Cash minima apply at the dated phase. Every projected `BUY_PRODUCT` needs an explicit total `max_cash_cost` at its absolute step and original slot, including any current one. Paired rival buys can raise later unit prices, which the caller's bound must cover. Missing funding bounds use the valid fallback. Known seed, animal, HIRE and successive land costs are accounted in order. For feasibility only, SELL earns the guaranteed lower bound of one dollar per filled unit. Exact market receipts remain the separate economic objective. When this cash lower bound covers the route's costs, the transform can optimize; otherwise it keeps the valid fallback.

Farmer and hand actions stay exactly selected. Non-SELL order values and indices stay selected. A SELL before any economic order retains its actual inherited fill, so the transform cannot newly pre-fund a purchase or remove its existing funding. Duplicate SELLs use one unreserved post-unit stock budget. Withheld SELLs leave empty slots; added sales append after inherited orders. Caller-reserved slots remain intact. WHEAT, FERTILIZER and animal stock stay under caller control; this transform optimizes only non-operating product SELLs.

Only one product's execution plan changes per call. Public standing yield and recent public yield decreases provide contingent rival supply magnitudes. `selected_sell_core.py` preserves the exact `absorption`, `MarketPath`, and `optimize_lot` function bodies from the accepted frozen scheduler. It scores the same no-rival and observed-supply scenarios with shared quotes, floor admission and own-minus-rival value. The separate producer obligations change feasibility, not sale valuation.

## Fallback and integration status

Without post-unit stock or a valid projection, the supplied fallback is returned unchanged. If omitted, the selected action is the fallback. A mismatched date, incompatible slot/stock reservation, missing product-buy bound, malformed projection, or absence of a certified feasible plan also uses the supplied fallback. With a valid projection and no explicit fallback, selected SELL requests may be normalized to their shared legal stock budget while preserving the original positions and actual economic prefix.

This is an executable integration component, with focused cases and committed development observations. It has no new full-game panel and does not inherit the standalone scheduler's20-game outcome claim. T08 owns selecting its authoritative continuation and benchmarking an actual composition on unused seeds.

Run only the focused examples when consuming the interface:

```sh
python3 -m unittest test_selected_action_sell -v
python3 selected-action-examples.py
```

`runtime/selected-action/examples.json` contains four executed examples and their actual official current-market cash receipts. In a synthetic known-consumption case, the same whole ten-unit commitment before market requires MILK10 now (receipts876); after market permits an empty current SELL slot and a planned sale next turn. These are different cash timings, not a game-win claim. Retained669 uses observed carried79 plus the actual committed EGG4 due671 after market: it keeps STRAWBERRY3 at unchanged continuation value552 and executes the inherited WHEAT2 sale for90. It does not reproduce the old envelope over every possible errand.

Runtime imports are `selected_action_sell.py`, `selected_sell_core.py`, existing `mechanics.py`, and pinned `reference/decision/decision.py`, all standard library. Preserve adjacent source licenses and the existing lab NOTICE. The original accepted archive was neither rebuilt nor replaced.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
