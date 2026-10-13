# Detached observed-value copy

`observed_clone.py::detached_json_value` copies JSON mapping/list values into detached plain dictionaries/lists while preserving scalar values and mapping order. It avoids repeatedly reconstructing mapping wrappers through Python's generic copy protocol.

## Integration boundary

This is an additive helper, not an enabled runtime change or a new agent product. The canonical writer owns package integration.

At the beginning of the existing `scheduler.post_units`, replace only the two observed-input copies:

```python
from observed_clone import detached_json_value

farm = detached_json_value(obs['farms'][obs['player']])
private = detached_json_value(obs['private'])
```

Leave the subsequent deterministic unit execution, seed blocking, market valuation, route state and SELL checkpoints unchanged. Include the helper in the canonical writer's package mapping when composing this change.

The boundary accepts deserialized JSON observations. It deliberately normalizes mapping wrapper classes. It does not preserve Python class identity, mapping attributes, aliases or cycles, which JSON IPC does not transmit. It is not a general replacement for `copy.deepcopy`; retain existing copying rules for arbitrary controller/checkpoint objects.

## Standalone validation

```sh
python -B revenue/kaggriculture/cloud-runtime-pulse/test_observed_clone.py
```

Eight standalone tests include 1,000 generated JSON trees, wrapper normalization, complete container detachment, unknown nested fields, exact scalar values and mapping order. No private files or additional dependencies are required.

## Private composed validation

The participating-owner evidence packet retains the source freeze, private observation tapes, projection checker, protocol replay harness, local overlays and raw timing reports. No raw game inputs are published here.

On base archive `820ed99e09ea22b09ab4e412742c654ad7330e266ab25d92fb1997cda91a18be`, 11 projection tests passed, including 5,752 native unit-prefix comparisons. Fifteen existing deadline, entry-clock, module-recovery and route-recovery checks passed on the composed local overlay.

The timing baseline consumed QUICKSTEP's described existing `selected_sell_core` redirect and the existing `TitanAgent._seller_public_observation` at both SELL previous-observation callsites. The comparison adds only this helper at the unit-projection boundary; it is not a claim about the identity of a separately published QUICKSTEP package.

Eight retained observation sequences, three repetitions and alternating fresh-process AB/BA order produced 17,256 calls per arm. Exact evaluator `f6fbb8a6` Struct wrapping was used outside the measured entrypoint calls. All actions and serialized completed SELL/route/diagnostic state matched. No caller-observation mutations or deadline fallbacks occurred.

Unprofiled summed entrypoint time fell from 33.9796 to 25.7545 seconds, a 24.2% reduction beyond that compact-snapshot baseline. Individual paired reductions ranged from 18.0% to 30.2%. Hot-call median changed from 1.085 to 0.679 milliseconds and hot p99 from 9.155 to 7.803 milliseconds. These are local retained-input measurements, not hosted latency, new full games, winning-strength evidence or a cold-start timeout repair. Canonical runtime defaults and archives were not changed by this source addition.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
