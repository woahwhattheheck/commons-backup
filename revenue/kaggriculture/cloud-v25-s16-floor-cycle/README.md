# S16 — floor-cycle rejection evidence

This directory implements the bounded shadow candidate requested by TITAN V2.5
order **S16**. It does not modify the canonical agent.

The pinned Kaggriculture engine quotes `BUY_PRODUCT` at the post-buy inventory.
A successful `SELL` at price `$1` pays cash but deliberately does **not** add the
unit back to public market inventory. Therefore, for FERTILIZER at the floor, an
isolated `BUY_PRODUCT 1` followed by `SELL 1` can restore own cash and stock while
reducing public inventory by one. Above the floor, the sale replenishes supply,
so this helper declines the cycle rather than assigning it a state benefit.

## Result

The strongest simple boundary is public FERTILIZER inventory `10494`: the cycle
leaves it at `10493`; one later public absorption moves baseline/cycle to
`10493/10492`, so a no-rival future FERT1 sale improves from `$1` to `$2`.
That is a real **local +$1 own-receipt distinction**, not immediate arbitrage.

S16, however, requires **strictly positive worst-scenario future value**. Under a
paired rival FERT1 sale in the same future market slot, both players receive the
same pre-commit quote in each arm. The cycle changes both players' receipts by
the same amount, so the own-minus-rival delta is exactly `0`. The candidate must
therefore decline.

The exhaustive deterministic scan covers inventories `10494..11000` and public
absorption `0..16`: **8,619 cases**, with locally positive no-rival examples but
**zero strict-family admissions**. This is sufficient for the S16 order's stated
`H only when real admissions improve outcomes` gate: no full-game panel is
warranted by this candidate.

## Physical and fail-closed gates

`admit_floor_cycle` additionally requires:

- enough cash for the `$1` buy;
- at least one shed slot of room;
- two free market slots;
- a downstream opportunity after the cycle;
- finite scenario values; and
- `min(scenario_delta) > 0`.

It always reports `immediate_profit_credit = 0`. A synthetic strictly-positive
control proves that the admission path itself is reachable; the exact floor
scenario family fails only on economic value, not because the helper can never
admit.

## Source binding

Executed against Commons main `655c85cb5843952fde68f85f3e4024bd9080a3f3`.
At publication, fresh main had advanced to `ff5ff0197def292d0d86b22091ad67dc84ba5547`,
while the active seller remained byte-identical. Current active seller blob at both pins:
`f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3`.

Official engine source is Kaggle/kaggle-environments commit
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`, `kaggriculture.py` Git blob
`3c202c7ee921da239356789e266b694635103fc4`. The relevant semantics are the
engine's `_process_market`, `market_price`, and `_commit_unit` definitions.

## Reproduce

```sh
cd revenue/kaggriculture/cloud-v25-s16-floor-cycle
python -B -m unittest -v test_floor_cycle
```

`RESULTS.json` records exact input identities, test counts, exhaustive counts,
representative locally-positive examples, and limitations.

No canonical source, archive, configuration, game seed, provider state, Kaggle
submission, spend, credential, or owner-PC state is changed by this component.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
