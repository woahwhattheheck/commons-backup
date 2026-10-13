# Ordered selected-action SELL

`ordered_selected_sell.OrderedSelectedSell` joins ATLAS's selected-worker projection with the generic SELL transform. Production remains caller-owned: this callable imports, constructs, and calls no parent controller. Current units run once on copied state at real shed capacity. Prepared state can then supply the producer's commitment snapshots and be reused for the SELL decision.

```python
from ordered_selected_sell import OrderedSelectedSell

sell = OrderedSelectedSell()  # Retain per actor/match for public rival history.
prepared = sell.prepare(
    obs, cfg, selected_action,
    future_actions=selected_future_actions_by_absolute_step,
    end_step=known_end_step,
    contingent_harvests=committed_future_harvest_step_worker_pairs,
)

# Caller obtains its producer snapshots against this exact copied state.
post = prepared["post_unit_observation"]
snapshots = obtain_committed_snapshots(post, selected_action)
contract = build_arrival_contract(post, cfg, selected_action, snapshots)

action = sell.transform(
    obs, cfg, selected_action,
    prepared=prepared,
    arrival_contract=contract,
    reservations=caller_operating_reservations,
    fallback_action=valid_selected_fallback,
)
```

`obtain_committed_snapshots` and `build_arrival_contract` above are caller functions, not a second production pass. T08 owns that composition. `prepare` exposes `post_unit_shed`, `post_unit_observation`, and the original generic `projection` schema. `transform(prepared=...)` calls no unit projection again; its diagnostics report `unit_projection_calls: 0`. The direct path accepts `future_actions`, `end_step`, and `contingent_harvests` instead and projects once. Missing continuation uses the supplied valid fallback. An explicit empty future-action mapping means the currently selected action is the complete known prefix, rather than an invented future PASS tape.

Prepared packets bind to the same original observation, configuration, and selected action, including inventory insertion order relevant to DROP. Keep the original observation for `transform`; use the exposed post-unit observation only for producer snapshots. A changed selected action or same-step farm/private state uses the supplied fallback. Inputs are preserved.

## Ordered stock and market behavior

The vendored `reference/ordered-feasibility/atlas/projection.py` is byte-identical to ATLAS `project_selected` SHA-256 `0ab335604b46a415bfb61cc5494c2d6f83591b13f2aa61323af6cf4a6e90e002`. Its source is landed in PR9951. It projects farmer then hands through the existing pinned official mechanics. Current DROP/PLACE admission uses actual capacity; discarded current goods never enter post-unit sellable stock.

Future DROP/PICKUP/PLACE events preserve worker and inventory order and the whole requested quantity. The seller checks physical bounds after each event. Thus a later PICKUP cannot recover an earlier spilled DROP. A market BUY can use room released by an earlier SELL; it cannot use room released by a later order. BUY_SEED uses seed storage, while products and animals use shared shed storage. Non-SELL order positions and selected worker actions remain intact.

The supplied continuation stops at its first missing or stock-dependent action, eight future decisions, the first daily boundary, or the actual final decision. Future acquisitions are conditional on full funding and admission, which the seller checks separately. Product-buy cash bounds, dated cash/stock minima, protected market slots, and valid fallback retain the [generic contract](SELECTED-ACTION.md).

Committed pending lots are capacity obligations only. Explicit `(absolute_step, worker_index)` entries in `contingent_harvests` identify selected future HARVEST actions already covered by the separate commitment contract. Those operations clear their harvested tile but do not credit pending yield as guaranteed stock. Previously observed carried goods remain physical inventory and generate their actual deposit events exactly once. The caller matches exclusions to its committed plans; neither opportunities nor hypothetical errands are substituted. EOD is after market, and the actual final EOD has no sale window.

## Landed component chain

- ATLAS PR9951, merge `a4451975f5411d90e2e7324d2e24d64d78d7d0d6`: ordered producer and per-event physical bounds.
- WREN PR9949, merge `0f4facccb5a1ca9ec198d01049e56d2a873a7944`: stock minima remain enforced after the last executable market.
- ATLAS PR9954, merge `5b9d81cf6d01055084ecb6dbc36d7946dcc4d226`: existing combined workflow receipt,51 methods on seller `a3ca92cb7fabfb65bb660931fb6fa2623067809ac01ef44b55edd6ca3f5b422a`. Its accepted original/projection/market suites were not rerun here.
- WREN PR9964, merge `2bb759e78308e67b032b89d946195be9bb1bd3a5`: validate the literal selected market queue when no optimizable product lot exists. Final consumed seller SHA-256 `d78c08bd8312915bd72c9a31a6dc3e49906eb4ff53b12f04fb4c679ebf742ba5`. WREN's15 additional consumer methods are retained as source-specific evidence, not recounted as a local rerun.

The frozen standalone scheduler remains `32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9`, and its archives and completed panels remain unchanged.

## New wrapper examples

Five new wrapper methods passed in0.062s on the combined ordered/terminal seller. They distinguish:

1. Current PICKUP WHEAT10 followed by hand DROP MILK10 produces WHEAT0/MILK100, with one prepared unit stage reused for sale.
2. Future DROP MILK10 before PICKUP WHEAT10 requires CARROT10 sold now; reversing the order permits a smaller current sale. Both official transitions retain all ten deposited milk.
3. Terminal PLACE WHEAT1 followed by a market that would consume its reservation uses the valid fallback and retains that wheat.
4. An actual T08 contract for a six-unit lot with two observed carried eggs reserves only four pending eggs. The physical projection deposits the observed two once; pending eggs are never sold.
5. SELL-before-BUY_ANIMAL uses freed shed space while the reverse order uses the caller fallback, preserving the original market positions.

After consuming WREN's empty-lot addition, one new wrapper method passed in0.040s: selected PICKUP removes the last saleable carrot, and the inherited HIRE would reduce cash100 below the dated minimum100. The caller's fallback keeps the selected pickup, omits the hire, and official execution retains cash100 and the carried carrot. The earlier five-case result remains attached to its original source checkpoint.

`runtime/ordered-feasibility/WRAPPER-RESULTS.json` and `EMPTY-LOT-WRAPPER-RESULT.json` record these two executions separately. Their command timings include fixture setup; no per-action speed or new game outcome is inferred. To reproduce this small wrapper suite in a cloud checkout:

```sh
python3 -m unittest test_ordered_selected_sell -v
```

No full-game panel or new seed was consumed. T08 owns the assembled arm and seed registry; this VM can execute its published composed-versus-parent development job when assigned. The currently published T08 reservations were already consumed, so they remain untouched.

Runtime needs `ordered_selected_sell.py`, `selected_action_sell.py`, `selected_sell_core.py`, existing `mechanics.py`, pinned `reference/decision/decision.py`, and the exact ATLAS `projection.py` at the relative path above. These use the standard library. Preserve ATLAS attribution, the original seller/engine notices, and the lab Apache license. No accepted archive was rebuilt.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
