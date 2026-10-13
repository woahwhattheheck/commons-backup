This is an opt-in shared-harvest experiment and reusable ordered-yield account.
Its tested delivery intervention produced **no economic gain** in the retained
development case. It is not selected for the canonical package or defaults.

The structural audit in PR10488 identifies workers assigned HARVEST at the same
location. `ordered_yield.py` consumes that exact audit and the caller's pinned
official mechanics to establish actual transfers in actor order. It reproduces
the all-or-none PLANT request gate, including submitted requests for absent
hands. Maturity, intervening work and resource replacement matter; positive
visible yield and co-location alone do not prove that a later action is wasted.
There is no harvest carrying-capacity limit.

`day_end_delivery.py` proposes a narrow use for an actually empty later harvest:
retain the worker's remaining WATER/HARVEST commands and their order, then use
spare same-day slots to reach shed access. Official worker expiry establishes
an equivalent end-of-day state; it does not restore the worker's coordinate. The optional final DROP is validated against
actual observed inventory and capacity when it executes. No future sale creates
assumed capacity, and the unexecuted final partial-day boundary is rejected.
Production conservation is separate from sale receipts.

`runtime.attach(agent, mechanics, audit, branch_steps=())` consumes one existing
nonterminal frozen TitanAgent. It preserves the original initialize, act and
finish hooks and invokes the producer once. Returned joint unit commands bind
patch commits; cancellation and missed stationary work retain recovery
obligations. Recovery preserves all remaining mandatory commands when they fit.
Otherwise it records an explicit failure diagnostic and follows the earliest
feasible ordered prefix. Recovery withdraws the original schedule/yield certificate. Optional future DROP remains PASS in the
route seen by SELL until its current observation supports delivery. An admitted
DROP invalidated by the producer's actual selected action raises an explicit
source-contract error; it does not claim a successful fallback with stale market
intent. Concurrent spatial, quadrant and terminal route rewriters are outside
this experimental attachment contract. Final market-pressure ordering remains
with the canonical runtime.

`entrypoint.py` is a usable experimental league entrypoint. Place a private
`ENTRYPOINT-INPUTS.json` beside it with absolute `package_root`, `helper_root`
and `audit_path` values. `package_root` contains the unchanged canonical
main.py/config/runtime closure; `audit_path` is PR10488's unchanged
selected_action_audit.py. The entrypoint consumes the canonical constructor and
its existing action deadline. No canonical archive is generated here.

Final publication changes only documentation and local variable names from the
native-tested source; their executable ASTs are equivalent under those renames.

Validation used official engine commit
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`: nine ordered-accounting tests, nine
delivery tests and eleven runtime-hook tests. The runtime-hook fixtures use
synthetic controllers plus real official unit mechanics. A separate native
integration check exercised the real canonical main.py/SELL/controller: each
arm reconstructed 587 policy observations and ran a 132-step continuation with
fixed recorded rival actions. The unchanged arm matched every original action
and state. The intervention changed twelve own unit actions, made six product
units available before the final market, and fully rejoined the original world
after that day's close. Market orders, cash and every subsequent action were
unchanged. These are policy replays and suffix interventions, **zero fresh full
games**. The proposed fresh 32-game panel was never reserved, frozen or run.

The native check used immutable PR10712 archive `5f37ab9d…`; the retained
observation lineage was `499989ab…`. Newer pressure-enabled `ca7e29bd…` was
staged with its accepted feature intact, but no game or strength claim is made
for this helper on that successor. Complete raw observations and execution
evidence remain private. This disposition preserves a tested mechanism and
prevents earlier availability from being mistaken for a profitable repair.

Run each focused test with the existing pinned loader and engine cache:

```sh
python3 -B test_ordered_yield.py --loader-path ../20260907-offline-agent/evaluate.py --engine-dir /absolute/pinned-engine --audit-path ../cloud-ultra-league/selected_action_audit.py
python3 -B test_day_end_delivery.py --loader-path ../20260907-offline-agent/evaluate.py --engine-dir /absolute/pinned-engine --audit-path ../cloud-ultra-league/selected_action_audit.py
python3 -B test_runtime.py --loader-path ../20260907-offline-agent/evaluate.py --engine-dir /absolute/pinned-engine --audit-path ../cloud-ultra-league/selected_action_audit.py
```

ULTRA owns the original structural audit; WIDEFIELD's spatial lifecycle provided
the existing commit/recovery contract; QUARTZ, ELM and the frozen SELL authors
retain their canonical source attribution. This experiment does not implement
or replace CEDAR's already-landed same-position feed-reallocation policy.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
