# Optional independent certificate binding

This additive binding consumes the original POLY solver and TRIAD checker;
neither is copied, replaced, or reimplemented. It leaves the six original PR9984
files and their 33-method receipt unchanged.

```python
from full_support import solve_full_table
from certificate_consumer import check_certificate
from checked_provider import checked_provider
from weighted_selector import make_selector
from selector import WholePlanSelector
from continuation import ContinuationPlanSelector

provider = checked_provider(solve_full_table, check_certificate)
selected = make_selector(WholePlanSelector, provider)
actor = ContinuationPlanSelector(selected)
# Supply the same full window, fallback, stock and feasibility arguments
# documented in README.md to actor.transform(...).
# provider.last_check retains the independent checker facts separately.
```

Only an exactly True `valid`, `completed`, and `positive_optimum` from the
injected checker allows its detached unchanged provider result through. Other
outcomes return None to the already-landed selector's complete-fallback/no-draw
path. The binding does not rewrite status, support, weights, table identity, or
certificate fields. In particular, equal exact bounds on a stopped computation
do not imply completed=True. Callback exceptions return a static unavailable
reason without exception text. The checker receives a detached result; retain
one binding and selector per actor/match. This does not replace caller-owned
physical feasibility, continuing feasibility, or observed-fill reconciliation.

## Actual additive validation

Nine new methods passed against actual source modules, without rerunning their
original test suites. The four-component path (POLY, TRIAD, selector, ASH) chooses
one complete plan and emits its dated actions with one provider/checker call and
one draw. Altered support metadata, a stale ordered table, and computation-limit
cases retain the entire original action with zero draws. A valid closed zero-gap
certificate at max_pivots=0 remains incomplete; a completed zero optimum also
keeps baseline. Detached inputs, strict boolean facts, and exception handling
are covered. These are consumer cases, not engine, LP-panel, or game results.

```sh
python3 revenue/kaggriculture/cloud-weighted-plan-selector/test_checked_provider.py \
  --json-output /tmp/checked-provider-validation.json
```

Explicit partial-checkout options are `--t15-dir`, `--continuation-dir`,
`--full-support-dir`, and `--checker-dir`, each pointing to the original source
directory. `CHECKED-VALIDATION.json` records the exact consumed and new source
hashes. `CHECKED-TEST-OUTPUT.txt` is the original nine-method output. The CLI does
not download files or start provider jobs. Dependencies are the README snapshots,
plus TRIAD `cloud-market-support/certificate_consumer.py`, Git blob
`9c448aae3b928affd26b050e6c66f2b6b1506ca4`, present at main merge
`722ca2e682ee64f69b72fd0ae9aae1f037ed46e5`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
