# Continuation-aware whole-plan consumer

An optional runtime adapter for T15's existing `WholePlanSelector`. Use it when a
consumer's authoritative production/stock continuation can change after initial
plan admission, or when calls may skip a sale date. The original selector,
solver, source freezes, and experimental results are not modified or replaced.

## Interface

```python
from selector import WholePlanSelector  # existing cloud-market-game-theory source
from continuation import ContinuationPlanSelector

policy = ContinuationPlanSelector(WholePlanSelector())  # one per actor/match
out = policy.transform(
    obs, cfg, valid_selected_action,
    window=window, post_unit_shed=current_shed, reservations=reservations,
    feasible=full_constituent_feasibility,
    continuation_feasible=current_remaining_feasibility,
)
```

Construct the wrapper before the first commitment and route every invocation of
that selector through it. This does not construct another production controller.
The runtime adapter imports only the standard library; supply the existing T15
selector rather than another copy. The caller remains responsible for a valid
fallback action and the original constituent-feasibility callback.

`current_remaining_feasibility(remaining_plan, context)` receives detached copies:

- `remaining_plan`: original plan metadata, with only sales dated at or after the
  current decision; previously emitted dates are omitted on later decisions.
- `context`: `key`, `item`, `slot`, `original_quantity`, `remaining_quantity`,
  `now`, `end`, `decision_step`, `plan_index`, and the supplied `observation`,
  `configuration`, `post_unit_shed`, and `reservations`.

Return exactly `True`, `False`, or `None` for feasible, infeasible, or unknown.
Check the actual remaining dates/quantities against the caller's current
production, cash, capacity, and ordered-slot commitments. This adapter does not
supply that economics model, infer prices, or convert unknown facts into a point
estimate. A raised callback exception also returns the supplied action; arbitrary
exception text is not placed in decision records. Non-boolean truthy objects are
not interpreted as feasibility.

On an infeasible/unknown continuation, a reversed decision time, or a missed
positive-quantity due date, the wrapper retires the current key and returns an
unchanged deep copy of the supplied action. It never samples a replacement under
that same key or invents a catch-up order. Retrying the same decision step retains
the committed choice and one draw, provided current feasibility still holds.
Skipping dates with no due sale is allowed. Original stock/slot obstructions and
all-constituent admission checks still apply.

An **emitted order is not a fill receipt**. The caller must execute the returned
action and use current observations/receipts in its feasibility model. The
wrapper cannot undo earlier deferrals, establish realized cash, or carry an
initial expected-value bound across an aborted/truncated plan. It makes no
win-rate or full-game improvement claim. Do not insert it into a frozen panel
and attribute changed behavior to the old source freeze.

## Reproduction and exact source

From this directory, once the neighboring T15 source is present:

```sh
python test_continuation.py --source-dir ../cloud-market-game-theory -v
```

The executed reference is Commons commit
`4d97474b0188b0373be1b52b610c0114ceb033c8`:

| Input | Exact Git blob |
|---|---|
| `cloud-market-game-theory/solver.py` | `3a6446d96e8470374dd5b5ba72a8e5c6d41a8ad3` |
| `cloud-market-game-theory/selector.py` | `546b71188fd44dc47cac99623d1967bc81413da7` |

The test runner imports those actual source files, not a mock solver or selector.
An alternate source location can be supplied explicitly. A regenerated witness sets
`source_commit` to the reference only when both actual input blobs match; changed
inputs retain their actual hashes with a null source commit and an explicit
reference mismatch. The local source copies
matched both published Git blob identities before execution. They are test inputs,
not vendored or modified files in this component.

**28 focused tests passed** in the cloud runtime. Coverage includes changed and
unknown continuations, callback isolation/error handling, null keys, exact mixed
weights and choice preservation, retries, skipped/terminal due dates, stock/slot
obstructions, all-constituent admission, completed-key retirement, and window
rollover. These tests do not rerun T15's solver proof, game panels, or held seeds.

`witness.json` records two executed synthetic invocation sequences against the
real T15 runtime: a newly infeasible continuation after initial deferral, and a
skipped first sale in a two-date plan. It records action differences, not official
market fills or game outcomes. To regenerate a separate witness:

```sh
python test_continuation.py --source-dir ../cloud-market-game-theory \
  --witness /tmp/continuation-witness.json
```

No policy selection, original source, game seed, hosted submission, or provider
operation is changed by this additive component. The implementation and tests are
Apache-2.0; the original T15 source and licenses remain with that directory.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
