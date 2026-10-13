# Fixed-slot plan feasibility bridge

A callable bridge between the existing T15 whole-plan selector, ASH's continuation
wrapper, and the selected-action SELL projection ledger. This component adds no
controller, optimizer, production forecast, price model, or policy selection.

## Use with one persistent selector

Put this directory and the existing `cloud-execution-lab`,
`cloud-market-game-theory`, and `cloud-plan-continuation` directories on the
module search path. Keep their existing dependencies alongside them.

```python
from selected_action_sell import ProjectionLedger
from selector import WholePlanSelector
from continuation import ContinuationPlanSelector
from plan_feasibility import PlanFeasibility

# Create once per actor/match, before the first commitment.
actor = ContinuationPlanSelector(WholePlanSelector())

# Build a new snapshot for each changed observation/action/continuation.
# These inputs come from the authoritative caller, not a second controller.
check = PlanFeasibility(
    ProjectionLedger, obs, cfg, selected_action,
    post_unit_shed=shed,
    projection=projection,
    arrival_contract=committed_arrivals,
    reservations=dated_reservations,
)

action = actor.transform(
    obs, cfg, selected_action,
    window=window,
    post_unit_shed=shed,
    reservations=check.selector_reservations(),
    feasible=lambda plan: check.admit(
        plan, item=window['item'], slot=window['slot'],
        end=window['end'], quantity=window['quantity'],
    ),
    continuation_feasible=check.continuation,
)
```

The lambda checks every original constituent at admission. On later decisions
with no new window, supply `window=None` and `feasible=None`; supply a fresh
snapshot's `continuation_feasible` and `selector_reservations` every time. Do not
reconstruct `actor` each turn. The supplied action remains the caller's valid
fallback. The wrapper retires an invalidated key without redrawing it.

`admit` and `continuation` return exactly `True`, `False`, or `None`:

- `True`: the supplied conditional continuation passes the existing conservative
  ledger with this plan's exact fixed-slot market queues.
- `False`: a concrete date, quantity, unreserved-stock, or fixed/reserved-slot
  conflict was found.
- `None`: coverage is missing, the snapshot disagrees with the call, the horizon
  is unsupported, or the conservative ledger cannot certify the continuation.
  This does not prove economic impossibility.

`last_check` records a short reason and verdict. `last_markets` is diagnostic
output for the latest check, not a fill receipt. A failed check may leave only a
partial set of queues; do not execute that partial output.

## Caller contract

Use the [selected-action SELL schema](../cloud-execution-lab/SELECTED-ACTION.md)
for post-unit stock, ordered non-market `stock_events`, committed contingent
`capacity_events`, dated cash/stock reservations, and paired-buy cost bounds.
The caller must supply a lossless continuation for the selected worker actions,
not a baseline tape or an opportunity envelope. Uncertain production must not be
credited as guaranteed sale stock. The ledger's assumptions remain conditional;
this bridge does not prove the caller's projection correct.

The projection must match the current absolute step and cover the entire plan
end, with an explicit `future_market` list for **every future decision** in that
interval, including empty queues. Omission is unknown, not an assumed PASS.
All plan dates and quantities must be integers, dates unique, and the scheduled
quantity must equal the supplied full/remaining quantity. Supported plans span
at most eight turns and end no later than `episodeSteps - 2`. CARROT, TOMATO,
STRAWBERRY, MELON, EGG, MILK, and WOOL are supported; input commodities are not
sale-plan lots in this adapter.

`fixed_market` matches T15's materialization: clear all existing sales of the lot
product, then place the positive due quantity in one fixed slot without compacting
other positions. It additionally preserves caller-reserved slot contents. This
is different from the SELL optimizer's quantity-replacement semantics. Full
planned quantities must fit unreserved stock; an engine-clamped partial sale
cannot satisfy the complete-plan contract. After the last positive sale, later
inherited queues resume unchanged, matching T15's key release.

The ledger inherits ATLAS's ordered-transfer checks and WREN's terminal
stock/cash checks. Dated commitments remain in the bridge. T15/ASH instead
receive `selector_reservations()`, which returns their scalar current
before-market cash minimum and stock map. Do not pass SELL's cash event list
directly to T15's scalar field. A BUY_PRODUCT bound must cover the caller's
possible paired rival buys; the adapter does not infer that bound.

The ledger credits only $1 per sold unit for operating-cash sufficiency. A failed
check can therefore reflect conservative pricing rather than unaffordability.
The retained real-market witness sells one carrot and successfully hires with
25 cash remaining, while that lower bound returns unknown. No exact quote,
expected payoff, or original mixed-plan bound is extended across an aborted plan.

## Executed validation

`RESULTS.json` records **23 passing tests**, **60 actual-selector queue
comparisons**, and **25 calls to the unmodified official market function**. The
market cases use explicit synthetic states, not full games or held evaluations.
They cover both seats, retained stock, other market slots, and actual cash.

The actual ASH wrapper witness first defers a sale, then receives a continuation
that withdraws the remaining stock. It returns the full fallback, retires the
key, and keeps one random draw. Other cases cover ordered deposit/withdrawal,
after-market arrival timing, terminal stock, committed capacity without stock
credit, explicit date coverage, immutable inputs, and stale snapshot rejection.
The test harness uses the real T15 selector/solver and real SELL ledger; it does
not substitute mock implementations for those components.

From this directory, with the original cached engine files available:

```sh
python test_plan_feasibility.py --engine-cache /absolute/path/engine \
  --report /tmp/plan-feasibility-results.json
```

Optional `--lab`, `--selector-dir`, and `--continuation-dir` parameters select
existing source directories; defaults are the sibling directories named above.
The test loads the unchanged engine file with its actual upstream seed helper;
it invokes market processing, not game initialization or a policy panel. No
network download, dependency installation, source export, or credentials are
required. Use Python 3.10 or newer.

## Source provenance

All test inputs retain their existing attribution and licenses. They are not
vendored or modified by this component. Full SHA-256, Git-blob identities, and
sizes of every imported project input and all three engine files are in the
result record, together with this implementation and test runner.

- SELL ledger/core: Commons `9209a80e47a69b6ffad0eb481f51de2125662d54`,
  `cloud-execution-lab/`; ledger blob `210fe63f6614c1a56065060cf8ee21b676859862`
  includes the ordered-transfer and terminal-reservation corrections.
- T15 selector/solver: Commons `4d97474b0188b0373be1b52b610c0114ceb033c8`.
- ASH wrapper: PR9947, main `e71ba67613eae308f786cdc4dea6f7ee28214476`.
- Official engine: Kaggle/kaggle-environments
  `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`. Existing artifact `10005621438`
  provided the unchanged engine cache; existing artifact `10031224878` supplied
  the frozen mechanics/receipt dependency closure. No new export job was run.

These are source-specific component results, not whole-repository CI, a complete
assembled policy, game wins, a hosted rating, or an extension of a frozen panel.
The original controller, selected SELL, source freezes, and seed usage remain
unchanged. Implementation and tests here are Apache-2.0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
