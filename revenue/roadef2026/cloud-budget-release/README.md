# Exact-flow reconfiguration-budget release

`budget_release.hpp` supplies one bounded secondary search move for the existing
ROADEF fleet solver. `build_candidate.py` binds it to the original solver without
changing its strict saturation-vector acceptance, ECMP implementation, transition
cost, primary neighborhoods, or portfolio entrypoint. This is an optional derived
candidate, not a replacement for SEDGE or a qualification submission.

## Mechanism

Inspect a maximal time interval on which one demand has the same segment route.
Remove one waypoint across that interval only when all of the following hold:

* The existing `routeFlow` returns exactly the same sorted normalized edge-flow
  vector at **every** affected time slot. This is an exact comparison, not an
  approximate total-load test. It remains conservative for zero-volume demands.
* Recomputed transition usage does not increase at either interval boundary or
  any other time, and decreases strictly at least once.
* The cooperative deadline still permits the move after its flow callbacks and
  after allocation of the staged replacement.

The operator returns a proposal without mutating its inputs. The native binding
allocates replacement route vectors before swapping them into the incumbent.
Cached routed flows and accumulated loads are unchanged. The primary acceptance
function never admits an equal or worse saturation vector; the neutral operator
is a separate, explicitly counted encoding change. Every accepted neutral move
reduces both waypoint count and total transition usage, so repeated neutral
moves cannot form a cycle.

This can free budget for a different demand's useful reroute even when the
neutral demand contributes nothing to the currently selected bottleneck. It
is not a proof that all future search choices or final scores improve: changing
an encoding changes subsequent neighborhoods, and the pass consumes time.

## Build and call

Use the existing exact fleet source at
`2885d176373c33410148829fef93c310c3752c0b`,
`revenue/roadef2026/fleet-candidate/main.cpp`, Git blob
`9354ec61fc32bb7ebbdaaa4a9bff7c7780a7e1df`, SHA-256
`322ec2e6bec9ab17c4cdf74c52d8e40414ce90cf60f9e53aaee2531cce652ab1`.
The already-delivered TRACE source/vendor package is
`ROADEF-WREN-build-inputs-2885d176.zip`, Library file
`file_0000000007c081fda1e225df8fd0e8ef`, SHA-256
`82785dc0ccbbd5daf0a77770faec95f02094a42aa40fb0dc84ad94e818765e6a`.
No new exporter or dependency download is necessary.

```sh
python3 -B build_candidate.py --source /path/fleet-candidate/main.cpp \
  --output /tmp/budget-release-build
c++ -std=c++20 -O2 -DNDEBUG -I /path/fleet-candidate/vendor \
  /tmp/budget-release-build/main.cpp -o /tmp/budget-release-candidate
CLOUD_INITIAL_SOLUTION=/path/incumbent.json SEDGE_SECONDS=30 \
  /tmp/budget-release-candidate network.json traffic.json scenario.json output.json
```

`SOURCE.json` records exact input/generated identities. The builder rejects an
unexpected source and duplicate/incompatible insertion seams. For a deliberately
composed newer source, supply its explicit `--expected-source-blob`; that only
selects an input identity and does not replace a new-combination validation.
Output must be a new directory. No caller source or current portfolio is edited.

The generated candidate defaults to enabled. `FLEET_BUDGET_RELEASE=0` retains
the original search algorithm and is the paired control. The candidate checks at
most4096 removal proposals per invocation (configurable by
`FLEET_BUDGET_RELEASE_LIMIT`, capped at1000000). Preparation accepts at most16
moves before primary search; later stalled searches may try another move before
the existing joint-demand ejection. `SEDGE_MAX_ROUNDS=0` still executes this
neutral preparation, deliberately allowing a zero-primary-search discriminator.
Neutral statistics are separate from the original `accepted` primary count.

The generic interface is:

```cpp
auto proposal = budget_release::find_release(
    routes, routed, horizon, used,
    flow_for, distance, stop, counters, max_proposals);
// optional Proposal<Route>{demand, left, right, next, used_after}
```

Routes and cached unit flows are demand-major/time-minor. The input incumbent
must already satisfy the solver's route and budget invariants. The component
validates dimensions and nonnegative usage, but is not a separate instance
parser. A callback is cooperative and cannot be preempted. A floating-point
rounding difference between mathematically equivalent routes can reject a move;
no approximate equality is substituted.

## Executed evidence

The standalone C++ test passes11 specific controls and5000 generated-model
comparisons against exhaustive removal enumeration.4152 returned proposals pass
independent full-transition and flow invariants. The same bank passes Address
Sanitizer and UndefinedBehaviorSanitizer with an empty diagnostic stream; that
is a different execution configuration, not another5000 independent cases.

The exact-fleet native driver passes39 cases: five hand-built flow/maintenance
cases,30 generated routing instances, and four interruption/expiry/disable/cap
controls. Across380 accepted neutral moves it independently reconstructs4882
native ECMP flows and recomputes all transition costs. Stored load bytes and
cached routed vectors remain unchanged; each accepted move decreases the
waypoint measure and uses no additional budget at any time. Test-only field
visibility exposes the real solver state without replacing method bodies.

A separate6-node/3-slot native discriminator compares four actual CLI runs:

| Run | Peak saturation | Transition usage | Primary improvements |
|---|---:|---|---:|
| Original fleet | 10 | [0,3,3] | 0 |
| Derived candidate, feature disabled | 10 | [0,3,3] | 0 |
| Neutral preparation only | 10 | [0,0,0] | 0 |
| Neutral preparation plus original search | 5 | [0,3,3] | 1 |

The neutral move removes a redundant waypoint from a disjoint demand, retaining
every load coordinate. It frees the budget needed for a different demand's
single-slot detour. Disabled source preserves the original solution, loads,
budgets and all preexisting counters exactly, excluding measured elapsed time.
The source extractor confirms the original `moveTogether` body is unchanged.

These are manufactured native instances, **not** public-B performance, official
checker validation, or a competition-rank claim. OSPREY's independent official
checker discriminator and ATLAS's independent invariant suite have their own
source and evidence; their results are not included in the counts above.

## Reproduce validation

Run without `-DNDEBUG` for the standalone assertion-based test:

```sh
c++ -std=c++20 -O2 -Wall -Wextra -Werror test_release.cpp -o /tmp/test_release
/tmp/test_release
python3 -B verify_native.py --source /path/fleet-candidate/main.cpp \
  --vendor /path/fleet-candidate/vendor --output /tmp/budget-release-native-check
```

The native driver uses explicit runtime checks even though its production
solver build uses `-DNDEBUG`. It retains source/binary identities, every command,
raw output/log, generated input, complete final solution and all native results.
`VALIDATION.json` is the compact source-bound record; the full driver output is
in the accompanying Library evidence package. No public instance or game was
rerun, no extra benchmark framework or workflow created, and no S139 draft,
attachment or submission action was performed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
