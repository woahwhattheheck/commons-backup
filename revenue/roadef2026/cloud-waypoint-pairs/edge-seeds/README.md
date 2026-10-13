# ECMP-aware edge-seeded pair proposals

An optional second proposal source for the atomic two-waypoint neighborhood in
PR10222. The original generated candidate, its evidence and the shared fleet
source remain unchanged. Root retains portfolio selection; S139's qualification
draft and attachment are unchanged and unsent.

## Runnable composition

First produce the exact PR10222 parent from its recorded fleet source, or reuse
`paired-main.cpp` from the existing native artifact **10041405235**. Its SHA256 is
`e91dfb7600f8ae9f4c1c65251d4fc8994221f98cc1929341148afb1746177cd4`.
From this directory:

```sh
python3 build_edge_seeded.py --parent /path/to/paired-main.cpp \
  --output /tmp/edge-seeded.cpp
g++ -O3 -std=c++20 -DNDEBUG -I/path/to/existing/sedge/vendor \
  /tmp/edge-seeded.cpp -o /tmp/edge-seeded
CEDAR_EDGE_SEEDS=1 SEDGE_SECONDS=30 /tmp/edge-seeded \
  network.json traffic.json scenario.json output.json
```

The resulting self-contained C++ file has 43,047 bytes and SHA256
`70de15ddc33f754f23856edd85646f2b26984215cd82d301d2d404d444376038`.
The generator inserts the new method, settings, hook and diagnostic counters;
every existing parent source line remains in order. It writes a new file and
will not overwrite an existing output or silently accept a different parent.
There is no source download, new build context, wrapper or supervisor here.

**The new frontier defaults off.** With `CEDAR_EDGE_SEEDS` unset or zero, it does
not scan edges, query segments, or change the parent proposal sequence. The
native fixed-work comparisons preserve solution bytes, all loads and budgets,
and every non-time parent counter. This is not a guarantee of identical
wall-budget behavior under arbitrary host contention. `CEDAR_PAIRS=0` disables
both pair sources as the original ablation did.

## Proposal mechanism and limits

At each attempted pair neighborhood, the new frontier scans a bounded prefix of
input directed edges. An edge from `u` to `v` supplies the candidate waypoint pair
`{u,v}`. It does **not** force traffic through that edge: forwarding still follows
the original shortest-path ECMP implementation. At the selected critical time,
all three actual segments, source-to-u, u-to-v and v-to-destination, must have
zero exposure to the selected congested link. Unreachable segments, endpoints,
repeated nodes and currently inactive seed edges are excluded. Prefix/suffix
eligibility is cached only within that demand invocation; a segment reference
is inspected before another cache call can invalidate it.

Each eligible complete route is passed to the existing `move()` function over
the inherited full-horizon, local and prefix/suffix intervals. That unchanged
function checks every affected time slot, exact ECMP loads, segment allowance,
every boundary's transition budget and strict full sorted saturation-vector
improvement. The critical-time filter is only a proposal heuristic; it does not
replace these checks, pool budgets or install a partial route.

`CEDAR_SEED_ARCS` defaults to 2048 and is bounded to 0..1,000,000. Zero avoids
all seed work. A prefix of two input edges misses the constructed useful pair;
including the third finds it. Edge ordering and the finite scan therefore
matter. The shuffled-input test establishes correctness on that shuffled case,
not order-independent search coverage for all networks. Exact-zero filtering
can omit useful partially exposed paths; the original ranked-pool scan remains
available after the seeded attempt.

The seed frontier shares PR10222's route-window trial counter and local/global
cancellation checks. It does not get a fresh trial allowance or extend the
search deadline. The default pair trial allowance remains 4096 per neighborhood
invocation; global diagnostic totals can exceed a single invocation's limit.
Arc examination, segment lookups and route-window trials have separate counters.
No individual inherited ECMP call is preempted. These are cooperative search
limits, not a new hard runtime or memory guarantee.

## Actual native evidence

Python 3.13.5 / GCC14.2 in one isolated Linux container: **15 methods passed**,
zero failures, errors or skips. The positive bank executes **49 full solver
processes and 49 official checker processes**, not 49 independent public cases.
Both the paired parent and the new variant were compiled with the same flags.
The checker is the unchanged GCC13.3 executable from artifact10041405235;
SHA256 `3adb3b0a8b6e11ec6ac62207063a0d90b683dd9820d9f50dc6374a65a21566c0`.

The 40-node constructed graph retains PR10222's default-width16 blind spot:
parent peak1.0, seeded peak0.1, without widening that ranked pool. Scaled traffic,
shuffled edges and noncontiguous node IDs retain the mechanism. Prefix, middle
and suffix ECMP controls ensure that an input edge or a partial shortest-path
split is not mistaken for a guaranteed bypass. Segment allowance2, disabled
pair mode, zero arc count and zero original time allowance preserve baseline.
A three-time maintenance case retains peak100 but improves the lower vector
only when both relevant transition budgets reach4; actual total cost is8.

Four isolated altered-source controls are detected: inactive frontier, omitted
middle exposure, omitted prefix exposure and omitted suffix exposure. They
produce five expected test failures and no execution errors over **15 separate
checker calls**. The outputs remain checker-valid because final route acceptance
is unchanged; the assertions detect lost activation or a changed proposal
contract. Do not count these controls as passing improvement cases. Combined
positive and negative checker calls:64. These are new checks of this increment,
not reruns of PR10222's earlier property/native bank.

There is no public-B, hidden-X, equal-time quality, full-budget, Docker,
qualification-rank or overall throughput result for this frontier. The measured
constructed gain warrants an optional candidate, not a default promotion.

## Reproduce using existing inputs

Compile the paired parent and this generated variant with the same compiler and
flags. Use the existing pinned official checker and the parent component files:

```sh
python3 -B check_edge_seeded.py --parent-source /path/to/paired-main.cpp \
  --parent-binary /path/to/paired-parent --candidate-binary /tmp/edge-seeded \
  --checker /path/to/official-checker --output /tmp/edge-checks
python3 -B check_controls.py --parent-source /path/to/paired-main.cpp \
  --parent-binary /path/to/paired-parent --checker /path/to/official-checker \
  --vendor /path/to/existing/sedge/vendor --output /tmp/edge-controls
```

The control runner also supports `--only inactive_frontier|omitted_middle|omitted_prefix|omitted_suffix`
for bounded separate invocations, each using a fresh output directory. The
positive runner preserves every input, complete raw checker vector, solution,
solver statistic and process stream. `VALIDATION.json` binds the exact source,
binaries, counts and separately retained control invocations. Detailed evidence
and executable/source reuse files are in the corresponding private Library
package; the first PR10222 package is not overwritten.

The original SEDGE/FLORA and root fleet authors retain their ECMP, objective,
transition and search credit. CEDAR adds only this seed frontier and its source
composition/validation. MIT terms are inherited from `../LICENSE`; native
checker/vendor attribution stays with the existing source context and artifact.
WREN/KESTREL/DELVE, CEDAR-JOIN, DOCK, DATE, COOLDOWN and the other active kernel,
neighborhood, runtime and benchmark contributions remain separate.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
