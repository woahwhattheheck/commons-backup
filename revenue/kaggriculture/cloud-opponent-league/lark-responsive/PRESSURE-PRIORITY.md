# Public-curve supply-pressure opponent

`pressure_priority.py` is an additive league-opponent transform. It preserves
every requested order, quantity, duplicate, non-SELL index and unit action, while
reordering only contiguous supported SELL blocks. It does not modify the
canonical controller or the earlier visible-quote transform.

## Disclosed hypothesis

For a requested lot of `n` units at public market inventory `I`, define:

```text
pressure = max(0,
    sum(price(item, I + k)     for k in range(n))
  - sum(price(item, I + n + k) for k in range(n)))
```

The second sum assumes a hypothetical rival sale of the **same lot size**. This
is a proxy, not an observation or estimate of hidden rival stock. Rank blocks by
descending pressure, keeping equal-pressure ties in parent order. Absolute quote
and expected deterioration are different: an expensive product on a flat part of
its public curve can be less urgent than a cheaper product on a steep part.

This calculation is not an optimal joint-market solution. Actual rival orders,
interleaving, stock availability and later decisions can differ from the proxy.
In particular, preserving issued production instructions does not guarantee
unchanged future economic decisions or stronger play. Treat the resulting
opponent as a stress arm in the unchanged parent's lineage.

## Integration

Place both this directory's `sell_priority.py` and `pressure_priority.py` on the
import path. Inject the exact frozen engine's **pure** public price function:

```python
import pressure_priority
import sell_priority

# engine.market_price takes (item, public_inventory, public_market_params).
# It must not inspect the evolving game state or either player's private data.
evaluator.Actor = pressure_priority.actor_class(
    sell_priority.actor_class(evaluator.Actor), engine.market_price
)

intact = '/absolute/path/parent_adapter.py'
quote_arm = intact + '|sell-priority'
pressure_arm = intact + '|supply-pressure'
```

Fresh actors use the existing official parent-file loader and process teardown.
Only the marked transform runs; the two markers are alternative arms, not a
combined policy. Alternatively call
`transform(action, observation, configuration, quote=engine.market_price)` inside
a compatible existing adapter. The supplied callable is part of the frozen
source closure and is responsible for the official curve's semantics.

The transform reads only the public market's `inventory`, `prices`, optional
`params`, and the configured executable market prefix. It never reads private
inventories, a future shop schedule, policy seeds or rival actions. Every quote
calculation is checked against the observed current quote before ordering.

Unquoted, inconsistent, malformed or unsupported orders are barriers. Lots above
256 units are left in place rather than quantity-clamped; executable prefixes
above 64 orders produce an unchanged action. Those bounds limit computation and
are not a claim to support arbitrary larger game configurations. The default
prefix follows the existing engine's ten-order rule. Unexpected callback errors
are not hidden as successful actions.

The wrapper records `pressure_priority_enabled`,
`pressure_priority_changed_turns`, `pressure_priority_transform_seconds`, and
`pressure_priority_total_seconds`. Parent RPC and transformation share the
original action deadline; overdue results become timeout responses. It does not
remove existing parent timeout, isolation, teardown or resource reporting.

## Validation

Run in this directory:

```sh
python -B -m unittest -v test_pressure_priority.py
```

Twenty-five focused tests cover the proxy calculation, public parameter changes,
price floors, stale quotes, stable ties, preserved orders and units, bounded
prefixes and lots, data errors, copy isolation, actual wrapper activation,
combined deadlines, and composition with the original visible-quote arm.

An additional private native check evaluated 378 product/inventory/lot/public-
parameter combinations against the pinned official market's transaction receipts.
The closed-form sums matched native unit commits, including the price floor.
That is a mechanics check with zero policy calls and zero full games, not a
strength certificate. The source-bound three-arm development panel retains its
full results, failures, source closure and original trajectories in the owner's
private TITAN evidence handoff. Do not infer promotion from the transform's name
or from successful activation alone.

Native mechanics pin: `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.
Upstream mechanics and parent license notices remain in the pinned source
closure; this module neither vendors them nor downloads dependencies.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
