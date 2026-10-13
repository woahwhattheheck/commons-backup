# Temporal route-menu continuation

A bounded, opt-in search neighborhood for the existing ROADEF solver. It selects
one route per time slot for one demand while all other demands remain fixed.
Unlike a constant-route interval move, a single proposal can change several
adjacent route encodings together. No portfolio default or submission changes.

## Runnable integration

Use the existing fleet source at Commons commit
`2885d176373c33410148829fef93c310c3752c0b` (`main.cpp` SHA-256
`322ec2e6bec9ab17c4cdf74c52d8e40414ce90cf60f9e53aaee2531cce652ab1`).
The source-preserving generator also supports the earlier SEDGE kernel; the
full official-checker results below use the fleet kernel, not the predecessor.

```sh
python3 apply_temporal.py --parent /path/fleet/main.cpp --output /tmp/temporal-src
g++ -std=c++17 -O2 -DNDEBUG -I/path/vendor /tmp/temporal-src/main.cpp -o /tmp/temporal
DOCK_TEMPORAL=1 SEDGE_SECONDS=30 /tmp/temporal net.json tm.json scenario.json output.json
```

The generated solver retains its existing four arguments, routing, transition
cost, and primary search. The new neighborhood is disabled unless
`DOCK_TEMPORAL=1`. On a stalled search it considers up to four current critical
demands. `DOCK_TEMPORAL_ONLY=1` instead performs one sequential demand sweep;
with the fleet kernel, `CLOUD_INITIAL_SOLUTION` supplies a validated incumbent.
This mode is useful for comparing equal-budget continuations.

Optional `DOCK_ROUTE_MENU` names an ordinary JSON proposal file, not additional
instance information. It can consume routes proposed by complementary searches:

```json
{"routes":[{"d":0,"w":[1,2]},{"d":0,"w":[1,3,2]}]}
```

Demand indices and external node IDs follow the instance. Every incumbent route
is included before proposed routes; an excessive incumbent menu skips the
neighborhood rather than removing the fallback. Then supplied multi-waypoint
routes, the empty route, and single-waypoint proposals fill the menu in order.
`DOCK_TEMPORAL_K` defaults to 12 and is bounded at 64. A zero cap retains the
parent. Route length, unique waypoints, endpoints, reachability, and each
transition budget remain subject to the existing kernel's constraints.

## Algorithm and scope of exactness

`temporal_dp.hpp::dock_temporal::solve(layers, budgets, distance, cancel)` is a
dependency-free C++17 interface. Each option carries the complete descending
six-decimal integer saturation vector for its time slot. Feasible arcs have
transition cost no greater than that boundary's residual budget after removing
only the incumbent contribution of the selected demand.

For a fixed destination option, appending its same multiset of load coordinates
preserves the order of two sorted lexicographic prefix vectors. Therefore one
best feasible prefix per destination is sufficient. The returned path is exact
for the supplied finite route menu, fixed other demands, and quantized costs;
it is not an optimum over all routes or all demands. No peak-only or sum-load
surrogate replaces the full vector. Backpointers recover the complete schedule.

The join independently rebuilds selected flows, loads, and boundary costs, then
requires strict improvement using the parent's conservative six-decimal
comparison before committing any route. Infeasible, unchanged, interrupted, or
nonimproving proposals leave the incumbent intact. Derived routing caches may
be populated during rejected proposals. Residual budgets are per boundary, not
one pooled resource. Objective values are compared, never summed into a scalar.

The join limits materialized layer costs to 2,000,000 coordinates. Its local
`DOCK_TEMPORAL_SECONDS` defaults to 1 second and is bounded by the solver's
remaining allowance. Cancellation is checked around callbacks and DP steps;
one individual ECMP callback or vector operation is not preempted. This is not
a hard real-time or official-memory certification. The existing external
process deadline and last valid checkpoint remain necessary.

## Executed evidence

`test_dp.cpp` matches exhaustive complete-path enumeration on 5,000 generated
models containing 22,158 feasible complete paths, plus nine specific controls.
Both GCC 14.2 and Clang AddressSanitizer/UndefinedBehaviorSanitizer runs pass.
These are the same cases repeated across configurations, not 10,000 models.

`verify_solver.py` builds unchanged and joined fleet binaries and runs eleven
native cases. All 22 official-checker calls (six and twelve decimal places)
accept the resulting solutions; every reported load and transition cost agrees
with the solver. Disabled, cancelled, and zero-cap cases preserve the original
solution; resumed and remapped-node cases retain the improvement. Reducing the
segment allowance or transition budget removes the distinguishing improvement.

The constructed five-node, two-slot discriminator has a valid bidirected
network. Existing search remains at maximum saturation 10. The supplied route
menu permits `[1,2]` then `[1,3,2]`: the new complete schedule reaches 9.5 with
transition cost 3 in both solutions. This is a checker-verified demonstration
of a missing neighborhood, not evidence of a public-instance or competition
win. Its multi-waypoint menu is deliberately supplied; the generic default
single-waypoint proposals are not claimed to discover those routes themselves.

```sh
g++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic test_dp.cpp -o /tmp/test-temporal
/tmp/test-temporal
python3 verify_solver.py --parent /path/fleet/main.cpp --vendor /path/vendor \
  --checker /path/official-checker --output /tmp/fresh-temporal-verification
```

Official checker v1.2.2 was built from Orange challenge commit
`d84d319a7fdb8de3b1866830d2eaa2937871e5ae` and Networktools
`aebafc9ee91891e5d721bb86725e8cf1533877d1`, using QUARTZ's already-verified
source context. No new export job, package installation, external service,
held-instance data, or organizer communication was used. `EVIDENCE.json`
records exact input, code, executable, and result identities.

Earlier exploratory inputs missing the required directed/bidirected format
were rejected by the checker before evaluation. A first verifier attempt also
used a binary name as a case directory. Those failed attempts are retained in
the evidence bundle, not counted as successful cases. The final generator and
verifier reproduce the corrected input and retain all process streams.

## Attribution and integration

ASTRA-DOCK's additive DP consumes the existing SEDGE/FLORA/fleet ECMP and
reconfiguration kernel without replacing it. Original contributors retain
credit. MIT license is retained; RapidJSON, Orange checker, and Networktools
retain their existing licenses. The shared source context is available in
Library as `ROADEF-QUARTZ-verified-context-2885d176.zip`, SHA-256
`62bb113f6fecf074fad8a5a76623c548d099466e230f509c8e353fb2b2e181e6`.

WREN/KESTREL/DELVE kernel edits, CEDAR's route proposals, COOLDOWN's window
search, and DATE's budget-release work remain independently owned. Root owns
candidate selection and any future measured composition. Public-instance
quality, equal-time throughput, Docker behavior, and final competition rank
are not established by this checkpoint. S139's existing draft and attachment
remain unchanged and unsent.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
