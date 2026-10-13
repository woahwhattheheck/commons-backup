# TITAN V3 forced-feasibility economic floor

Operation:
`titan-v3-forced-feasibility-economic-floor-20260910-sol-pro-01`

## Exact current-source defect

At scheduler Git blob
`a483b24dd72b580d7d8811636b54d2d44f391575`, an infeasible authored
reference waives the optimizer's strict scenario-improvement rule. Any
physically feasible replacement can become the winner, including one with a
negative modeled value in every scenario. The caller then ranks the Boolean
`forced_feasibility` flag before `worst_relative_gain`, so a losing or
value-neutral forced row can suppress a different product's positive plan.

The executable predecessor witness is intentionally small and uses the current
scheduler's real `MarketPath` and `optimize_lot`:

- product: `WOOL`, quantity `1`;
- public inventory: `10058`;
- step range: `576..577`;
- eight unlocked `YARN_STORE` shops;
- authored reference: sell one unit at step `577`;
- physical callback: require at least one unit sold at step `576`.

Town absorption makes the delayed reference worth `$102`; the forced immediate
sale is worth `$5`. The predecessor emits four `-97` scenario deltas and still
selects the immediate plan.

## Repair boundary

`materialize.py` copies and patches one exact current `scheduler.py` into a
temporary location. It does not edit canonical source.

The repair:

1. keeps the predecessor's strict all-scenario relative improvement rule when
   the authored reference is feasible;
2. when the reference is physically infeasible, requires both nonnegative
   worst-case relative gain and nonnegative worst-case own-cash gain;
3. records physical-candidate discovery and economic-floor rejections
   separately;
4. ranks cross-product candidates by economic gain first, with the forced flag
   only as a same-gain tie-break annotation.

A value-neutral feasible repair may still be selected. A negative repair remains
diagnostic-only until a separate exact, product-level avoided-loss certificate
exists. The present Boolean `capacity_ok` interface cannot establish that value,
so this lane does not manufacture it.

## Executable contracts

`test_economic_floor.py` imports both the exact current scheduler and the
materialized repair. It proves:

- exactly five cardinality-checked source replacements;
- source immutability and fail-closed blob/needle drift;
- the real current-source `$102 -> $5` / `-97` predecessor;
- rejection of a negative forced candidate;
- positive-product selection over negative or zero forced candidates;
- gain-first selection when a forced plan is genuinely positive; and
- own-cash non-regression for an otherwise positive forced plan.

The fake controller used only by the cross-product tests preserves the production
route-bank shape (`R = [route]`), avoiding the historical fixture error where a
single route was mistaken for the complete route bank.

## Scope

This is an additive repair carrier for composition and review. It mutates no
canonical runtime, archive, selected pointer, configuration, game bank, provider
state, Kaggle submission, or leaderboard state. Passing contracts establish the
bounded source semantics above; they do not by themselves establish population
strength or promotion authority.
