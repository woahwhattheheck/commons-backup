# V5 unit-before-market inventory ordering research

Default-OFF research/evidence only. No runtime hook, config/default change, archive mutation, package authority change, or Kaggle submission is introduced here.

## Pinned-engine theorem

The canonical pinned engine `reference/engine/kaggriculture.py` currently has Git blob `3c202c7ee921da239356789e266b694635103fc4`.

Its interpreter executes **every farmer/hand unit action before `_process_market()`**. Within those unit actions, `PICKUP` removes product from the player's shed immediately. Later, a market `SELL` can commit a unit only while that same product remains in the shed. Conversely, a sale-only product already carried by a shed-adjacent worker can be `PLACE`d into the shed during the unit phase and therefore become available to the already-selected same-turn SELL.

That order creates two mechanically real selected-action hazards/opportunities:

1. a final `PICKUP` can remove stock that the parent action also selected to SELL later in the same turn;
2. a final shed-adjacent PASS can strand carried sale-only stock while the parent SELL is short of shed inventory, even though PLACE-before-market would make those sale units executable.

`WHEAT` and `FERTILIZER` are excluded because they are operating inputs with separate feed/fertilizer policy value.

## Candidate boundary

`unit_market_bridge.transform()` is intentionally conservative:

- configuration defaults apply only when the configuration argument is `None`; any supplied non-mapping fails closed, and `boardSize`, `maxMarketOrdersPerTurn`, and `shedCapacity` must be positive plain integers when supplied;
- the executable market prefix uses the configured positive plain-int `maxMarketOrdersPerTurn` and only valid positive SELL quantities;
- only sale-only goods (`CARROT`, `TOMATO`, `STRAWBERRY`, `MELON`, `EGG`, `MILK`, `WOOL`) participate;
- **every supplied unit action before the final supplied actor must be shed-inert** (`DROP`, `PICKUP`, and `PLACE` in that prefix all block admission), so observed shed state is still exact immediately before the only edited action;
- the final worker must be at one of the four engine shed-access tiles and have a well-formed exact inventory;
- final PASS may become one `PLACE item qty` only when exactly one sale-only item has both a selected SELL shortfall and carried stock; quantity is clipped by SELL shortfall, carried quantity, and current shed room;
- final sale-only PICKUP is capped to shed stock in excess of the selected same-item SELL demand, or replaced with PASS if no excess exists;
- market bytes and every other unit action are preserved exactly;
- malformed/ambiguous shapes fail closed to parent identity.

The PASS bridge is not a claim that selling earlier is economically superior in every route. It is an executable experiment that lets current-route engagement/economics answer that question without confusing it with an engine-ordering bug.

## Focused controls

Exact authored-byte receipt after the configuration-ingress predecessor was folded:

```text
python test_unit_market_bridge.py      -> 15/15 PASS
python -O test_unit_market_bridge.py   -> 15/15 PASS
python -m py_compile unit_market_bridge.py test_unit_market_bridge.py -> PASS
```

The suite covers exact shortfall placement, shed-room clipping, stock-reserving PICKUP suppression/capping, parent immutability, operating-stock exclusion, earlier-shed-mutation refusal, executable market-cap prefix, trailing market metadata, non-list market identity, non-finite quantities, multi-item ambiguity, final-hand support, shed-adjacency refusal, and the falsey non-mapping configuration family (`False`, `0`, `""`, `[]`, `()`).

Authenticated branch blobs for that receipt are `unit_market_bridge.py@c3d8d48929f99e766b5c041fa6b9eb5c5d83f429` and `test_unit_market_bridge.py@4f2ed9be68cdc70cf2dea08b472e97a66f2c6b87`.

## Promotion gate

Do not hook this into production from static mechanics alone. A promotion attempt needs:

1. a current-route/current-native engagement census proving the transform actually fires on canonical V5 selected actions;
2. matched official-engine control/treatment cells with exact `v5c:` identity and an economics screen (money plus relevant retained inventory, not money alone);
3. no regression of the parent action's other unit/market topology;
4. composition through the single canonical V5 rather than a sibling controller/package.
