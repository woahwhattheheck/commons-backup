# Shared-capacity refinement for prior sale history

## Change

`SelectedActionHistory.observe` now intersects the prior-turn sale intervals of non-buyable products with their one shared pre-market shed capacity.

Workers finish before market processing. During the market phase, CARROT, TOMATO, STRAWBERRY, MELON, EGG, MILK, and WOOL cannot be purchased to replenish the rival shed. Their total sold quantity therefore cannot exceed the shed capacity present at the start of that market. WHEAT and FERTILIZER are excluded because their market buy/sell ambiguity remains unresolved.

For existing marginal sale bounds `lower[i] <= quantity[i] <= upper[i]` and capacity `C`, the helper applies:

```text
new_upper[i] = min(upper[i], C - sum(lower[j] for j != i))
```

This is the exact marginal projection of the existing intervals intersected with the single capacity inequality. It preserves every previously feasible joint quantity vector. Returned endpoints remain correlated; callers must not combine them independently.

Examples:

- A proven MILK sale of 100 from a capacity-100 shed forces a formerly floor-censored WOOL interval `[0, 100]` to `[0, 0]`.
- A proven MILK sale of 80 tightens WOOL to `[0, 20]`, which remains uncertain.
- A request to sell 100 MILK is not proof of 100 sales. When native floor behavior proves only 76 admissions, WOOL remains bounded at `[0, 24]`.
- Missing product records remain missing. Quiet or generally censored history is not converted into a guessed zero.

When capacity establishes a singleton sale quantity, the existing `FlowHistory` can consume that exact prior quantity. The result is still not a cash receipt, current rival stock, a current rival order, or a future probability. The diagnostic retains the original censoring reason and before/after sale and admission bounds.

Both maintained copies are changed together:

- `cloud-market-response/selected_action_history.py`
- `cloud-execution-lab/reference/titan-history/selected_action_history.py`

The focused test asserts that those copies remain byte-identical.

## Validation

### Repository-focused suite

Command:

```sh
python -B revenue/kaggriculture/cloud-market-response/test_joint_sale_capacity.py
```

Result: **10 tests passed**, zero failures or errors.

The suite includes bridge-level supplied-fill consumption, impossible-joint-bound rejection before history append, canonical-reference parity, and exhaustive integer enumeration across 14,745 interval/capacity inputs. It retains all 56,604 feasible integer portfolios and reproduces the exact marginal bounds for every feasible case.

### Recovered source-bound native package

The separately retained reproduction ran successfully again immediately before publication:

- 21 methods passed, zero failures or errors.
- 14,745 interval/capacity inputs; 9,109 feasible and 5,636 rejected as inconsistent.
- 56,604 feasible integer portfolios retained.
- 19 targeted native historical transitions.
- 336 additional native portfolio transitions across both positions, capacities, and price regimes.
- 2,352 actual-sale containment checks passed.
- Eight downstream terminal market cells matched eight full native-interpreter terminal transitions.
- The exact original source reproduced seven expected failures across nine new native-consumer requirements, with zero execution errors.

These are component, interpreter, and conditional-consumer results. No policy actor, full game, or provider operation is part of this change.

### Retained phase data

The saved PR10134 phase-study data show no natural coverage change:

- prior transitions: 55
- non-buyable intervals: 385
- exact intervals: 334 before and 334 after
- ready joint families: 1 before and 1 after

That negative result is retained. This patch supplies a correct conditional inference for histories where shared capacity actually discriminates; it does not establish policy strength or justify enabling terminal history by default.

## Source identity and scope

Base source Git blob: `59d85cefb4cb793f8d7a3fc79d8e5675449956fb`.

Changed source Git blob: `7967fb43c64bc3154fe7da609497873163c773eb`.

Changed source SHA-256: `f83bf0804eadee97b91250ec0f93c44332cc2269d38b66aa25568873c46694d4`.

Focused test Git blob: `1c0dcafd3936dd675ce710a376453922465742ed`.

Focused test SHA-256: `0a8ba0e8cdf946a6792e94ca68f8cd6a414e955ae138d88c637cbf1d6852ae78`.

The production delta is one helper plus its call in `SelectedActionHistory.observe`. Existing controller, solver, scenario, market, history, fill-ledger, and policy-default behavior is unchanged outside the refined prior-quantity intervals. The canonical release is not rebuilt by this delivery; the single release builder retains that responsibility.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
