# Bind plan continuation to observed sale fills

This opt-in addition connects the existing `ContinuationPlanSelector` directly
to ESTUARY's existing `ObservedFillLedger` and `full_sale_verdict`. There is no
new wrapper, quantity-inference model, optimizer, or production-controller call.
Existing callers that supply only the selector retain the prior behavior. The
T15 adaptive policy, its recorded experiments, and selected defaults are not
enabled or rewritten by this change.

## Usage

Supply one fresh, exclusively owned ledger per adapter/actor/match. Do not share
its pending action with the separate adaptive-history consumer.

```python
from selector import WholePlanSelector
from continuation import ContinuationPlanSelector
from observed_fills import ObservedFillLedger, full_sale_verdict

policy = ContinuationPlanSelector(
    WholePlanSelector(),
    fill_ledger=ObservedFillLedger(),
    fill_verdict=full_sale_verdict,
)

# obs is the current own PRE-UNIT observation. Transform automatically checks
# any previously recorded due sale before advancing the remaining plan.
action = policy.transform(
    obs, cfg, valid_current_fallback,
    window=window,
    post_unit_shed=current_post_unit_shed,
    reservations=reservations,
    feasible=full_plan_feasibility,
    continuation_feasible=current_remaining_feasibility,
)

# AFTER all transforms: use the actual final queue and snapshots after that
# final action's unit stage, not another controller's projection or pre-unit
# shed. This records only a positive due sale emitted by this adapter.
record = policy.record_final(
    obs, cfg, final_action,
    post_unit_shed=final_post_unit_shed,
    post_unit_inventories=final_ordered_carried_inventories,
)

# At termination, observe the final result without asking for an extra action.
last_fill = policy.observe_fills(final_own_observation, cfg)
```

The variable names above are caller-owned inputs, not another simulator or a
source of inferred snapshots. Preserve the existing full-plan admission and
current continuation-feasibility callbacks. A past fill does not prove that a
future sale remains physically executable or profitable.

## Binding and lifecycle

`record_final` checks that the final action still requests the emitted plan's
product, quantity, slot, player and step, then delegates recording to the existing
ledger. Its SHA-256 binds the entire detached final action. Changes elsewhere in
the final queue are included in reconciliation; an earlier sale can therefore
exhaust stock before the committed slot. The caller must actually submit that
recorded final action. The method does not submit, replace or repair it.

The next own pre-unit observation must be adjacent. The adapter compares the
returned action binding and product, then consumes the existing quantity verdict.
A proven full fill allows the normal remaining-plan check. A proven short fill,
unknown result, absent final record, mismatched binding or observation gap retires
the key and returns the full caller-supplied fallback on the next `transform`.
No replacement draw, catch-up order or assumed fill is created. `last_fill`
retains the separate quantity report, including unknowns and null cash receipts.

Repeated same-step observations remain pending. Each repeated `transform` that
emits a due sale needs a new `record_final` after the final action is settled;
the existing one-draw behavior is unchanged. A later valid same-step record may
replace an earlier invalid record attempt. A deferral with no positive due sale
requires no record. Missing evidence at a positive due date is never interpreted
as successful execution.

`observe_fills` may also be called before a subsequent action or on a terminal
observation. It returns a report, not an action. If it finds a short/unknown fill,
the failure is retained until the next transform produces fallback. The
selector's inherited `completed` set means **retired keys**, including aborted
ones; membership is not proof of sale completion, revenue, or a win. A terminal
unknown remains unknown even when no further action will be requested.

Only quantities are reconciled. Exact final-unit snapshots are a caller
contract, not something this adapter can establish from a pre-unit state.
End-of-day carried-inventory mappings must preserve actual worker and item
order. Missing boundary deposits, purchase ambiguity, missing observations or
exhausted reconciliation budgets remain unknown. The existing ledger's budgets
are computational limits, not measured whole-agent latency guarantees. It is not
safe to substitute this quantity verdict for a future-feasibility verdict, cash
receipt, calibrated scenario probability, or continued expected-value bound.

## Executed checks

The new joined suite passes **28 methods**, with no errors, failures or skips,
using the actual unchanged selector, solver and fill ledger. Coverage includes
both positions, full/short fills, ambiguous buy/sell round trips, final-queue
replacement, action binding, retries, missing evidence, ordered daily deposits,
terminal observations, reconciliation budgets, detachment, and the separate
current-physics callback.

A separate default-disabled differential compares **1,312 paired invocations**
against the exact original ASH adapter across 12 schedule/fallback scenarios and
32 selection-RNG initializations. All returned actions, active state, draw counts,
retired keys and decision records match. These RNG initializations are not game
seeds. The differential does not run any old game panel or peer component suite.

`FILL-VALIDATION.json` contains the executed source identities, test counts, four
both-position full/short invocation witnesses and default-differential digest.
`fill-tests.log` preserves the successful run. These are synthetic consumer
sequences, not newly executed official-market transitions, full games, cash-gain
measurements or hosted-strength evidence. ESTUARY's prior official-market
validation remains attributed to that component and is not counted again here.

Inputs used for this run:

| Source | Exact Git blob |
|---|---|
| T15 `solver.py` | `3a6446d96e8470374dd5b5ba72a8e5c6d41a8ad3` |
| T15 `selector.py` | `546b71188fd44dc47cac99623d1967bc81413da7` |
| ESTUARY `observed_fills.py` | `cabe10ad3d683351077c9597ad7bb36cb58ce9c6` |
| Original ASH `continuation.py` | `165890d9e2534785ee4114e39549528e3f14ad82` |

T15 inputs are available at commit
`4d97474b0188b0373be1b52b610c0114ceb033c8`; ESTUARY at
`e3ab46552c7a6cd8f22d40a1d1007423a0d18ee3`; original ASH at
`433fc86590719fec9b489bf9570ef33478faa8fb`. The new test records actual input
hashes rather than assigning those commits to arbitrary changed dependencies.
All four local input blobs were matched before the retained execution.

## Reproduce

From the repository root, using its existing neighboring source directories:

```sh
python -B revenue/kaggriculture/cloud-plan-continuation/test_fill_binding.py \
  -v --report /tmp/ash-fill-validation.json
```

For the optional original-default differential, extract the original ASH file
from the existing Git history, then pass its path. This extraction does not
replace current runtime files:

```sh
git show 433fc86590719fec9b489bf9570ef33478faa8fb:revenue/kaggriculture/cloud-plan-continuation/continuation.py \
  > /tmp/ash-original-continuation.py
python -B revenue/kaggriculture/cloud-plan-continuation/test_fill_binding.py \
  -v --baseline-continuation /tmp/ash-original-continuation.py \
  --report /tmp/ash-fill-validation.json
```

A relocated existing cache can be supplied with `--dependencies DIR`, containing
the actual `solver.py`, `selector.py`, and `observed_fills.py` files. The historical
README, original test suite and witness remain unchanged. Source is Apache-2.0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
