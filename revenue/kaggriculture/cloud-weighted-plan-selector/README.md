# Weighted complete-plan selector

Optional runtime consumer for an existing `WholePlanSelector`. It extends only
`choose`; the original `transform` function is inherited without modification.
An injected provider supplies a complete-plan distribution. No solver, controller,
producer projection, continuation validator, or fill reconciler is implemented here.

## Use

Place the existing T15, full-support, and continuation directories on the Python
module path alongside this directory, then construct one instance per actor/match:

```python
import random
from selector import WholePlanSelector
from full_support import solve_full_table
from continuation import ContinuationPlanSelector
from weighted_selector import make_selector

selected = make_selector(
    WholePlanSelector, solve_full_table, rng=random.Random()
)
policy = ContinuationPlanSelector(selected)
action = policy.transform(
    observation, configuration, original_action,
    window=complete_window,
    post_unit_shed=actual_post_unit_shed,
    reservations=operating_reservations,
    feasible=complete_plan_feasibility,
    continuation_feasible=current_remaining_plan_feasibility,
)
```

The caller supplies all values in the transform call. The original action must
be the valid complete fallback from its single authoritative controller. Preserve
T15's window schema: `key`, `item`, `quantity`, `now`, `end`, `slot`, `plans`,
`deltas`, and optional `learned_start`. A plan has a distinct nonempty string `id`
and `sales=[[absolute_step, quantity], ...]`. Row zero is the unchanged zero-delta
baseline. Every row remains aligned with its original plan, and every column is
a complete correlated rival stream, not an independently resampled product.

`solution_provider(rows)` receives immutable tuples of exact Fractions. Its
result must have `status="optimal"`, exact `weights` in original row order,
and `value`. The tested provider is POLY's `solve_full_table`; it checks its own
primal/dual certificate. All provider fields, including budgets and source-table
identity, remain under `active['solution']['provider_result']`.

This adapter validates the probability simplex and recomputes the included-stream
floor, comparing it with `value`. It does **not** independently certify an optimum
or interpret dual weights as learned probabilities. An independent checker remains
a separate consumer; a cached-result provider should verify its exact table and
certificate before returning a result. Pass the published solver directly or wrap
that provider, rather than substituting a status label for certificate evidence.

Only positive-floor results reported optimal are sampled. A nonpositive floor,
computation-limit status, missing/invalid solution, or unsupported constituent
retains the complete fallback without a draw. All constituents, including baseline
and zero-weight rows, must return exactly True from the supplied feasibility check.
The exact rational sampler preserves baseline mass and zero-weight row positions;
no float rounding or support compression occurs. One live key has one solve and
one draw, not a new draw on each action. This optional adapter also retires a key
when it selects baseline or cannot support the decision; genuinely changed inputs
need a new decision key. Keys must be hashable, as for the original selector.

`mode="baseline"` and `mode="pure"` require no provider call. Pure mode retains the
existing positive-tail/nonnegative-column rule, extended to all supplied plans.
Factory defaults allow 32 plans and 256 streams; the injected POLY core itself
supports 9 plans and 32 streams. Exact-number and random-denominator bit budgets
are both 4096 by default. These are arithmetic bounds, not total agent-time bounds;
the caller accounts for provider work inside its actual runtime budget.

The inherited transform preserves current stock/slot handling and action layout.
ASH's separate wrapper is needed for remaining-plan validation, skipped due dates,
and time reversal. An emitted order is not a fill receipt. Observed-fill evidence
must bind the actual final submitted action, player, step, product, and slot. An
initial expected floor covers supplied streams at commitment; it is not a realized
cash guarantee, a guarantee after conditional abandonment, or a full-game result.

## Reproduce

From the repository root with the dependency directories present:

```sh
python3 revenue/kaggriculture/cloud-weighted-plan-selector/test_weighted_selector.py \
  --json-output /tmp/weighted-selector-validation.json
```

A partial cloud checkout can supply explicit paths:

```sh
python3 test_weighted_selector.py \
  --t15-dir /path/to/cloud-market-game-theory \
  --continuation-dir /path/to/cloud-plan-continuation \
  --full-support-dir /path/to/cloud-full-support \
  --json-output /tmp/weighted-selector-validation.json
```

The CLI imports the actual source classes and records each input's Git-blob and
SHA-256 identity. It neither downloads source nor launches provider jobs. The
retained `VALIDATION.json` includes the full action witness and dependency hashes;
`TEST-OUTPUT.txt` is the original executed 33-method output. `SOURCE.json` binds
those files and the runtime/tests by hash.

Validation covers an actual four-plan POLY result through the unchanged selector
and ASH, a nine-plan family retaining original index 8, computation-limit and
zero-optimum fallback, all-constituent feasibility, exact probability sampling,
original action-slot behavior, stock and continuation aborts, and 36 same-input
three-plan action comparisons with the original selector. The four-plan witness
has one provider call and one draw over four action dates. The 30-draw baseline-mass
fixture is a sampling-only injected record, not a claimed optimal solution. The
100-call warm sample includes the actual core plus factory/transform on the small
algebraic witness: maximum 3.040893 ms here, not a cold-start or whole-agent bound.
No original peer suites, LP panels, engine cases, full games, or game seeds are
rerun by this delivery. No selected policy or evaluation freeze changes.

## Exact dependency snapshots and attribution

All paths below are in `woahwhattheheck/commons`. Peer implementations are consumed,
not copied into this directory. Preserve their Apache-2.0 notices and the T15
[license](../cloud-market-game-theory/LICENSE) when packaging dependencies.

- T15 selector and original comparison solver at
  `46332a6b2ed2e3b329cca62faf85d2482c23000f`, directory
  `revenue/kaggriculture/cloud-market-game-theory/`:
  selector blob `546b71188fd44dc47cac99623d1967bc81413da7`;
  solver blob `3a6446d96e8470374dd5b5ba72a8e5c6d41a8ad3`.
- ASH continuation at `e71ba67613eae308f786cdc4dea6f7ee28214476`,
  `revenue/kaggriculture/cloud-plan-continuation/continuation.py`,
  blob `165890d9e2534785ee4114e39549528e3f14ad82`.
- POLY full-support source at `3457d8f149b2bb07de6d9993a41ae0e0f19eb57f`,
  `revenue/kaggriculture/cloud-full-support/full_support.py`,
  blob `b04f7bc4ff2137dee4b70ec6f10e7f02ccaebd06`.

The runtime uses the Python standard library, Python 3.10 or newer. It introduces
no second solver or controller and changes none of those source files.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
