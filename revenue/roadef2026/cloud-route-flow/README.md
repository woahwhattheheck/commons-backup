# ROADEF route-flow experiment

**Optional experiment, not promoted.** The measured patch is not installed in the canonical solver or S139 submission. It preserves tested decisions but does not establish a whole-solver speed improvement.

## Mechanism

`segment()` returns sorted unique-edge fractions. For zero waypoints this patch returns that copied segment without sorting it again. For one waypoint and more than 32 concatenated entries it merges the two sorted legs; small and multi-waypoint routes retain the original sort. Duplicate-edge summation, failure-prefix output, cache behavior, search, distance, objective, budgets and supervisor remain unchanged. The first leg is copied before another lookup can evict its cache entry.

`apply_route_flow.py` replaces only the exact original method and creates a new detached source file. Disjoint edits elsewhere survive; compatibility of a later combined solver still needs its own measurement. Root/CEDAR-JOIN retain candidate integration.

## Measured result

- 46,707 bit-exact flow comparisons on 14 generated graphs. The large 41,856-comparison graph also passes GCC AddressSanitizer/UndefinedBehaviorSanitizer with 13 cache/cutover/failure controls. Three deliberately broken variants are detected; eight application tests pass.
- GCC 14.2 and Clang 17 each match original/candidate solution bytes, complete load/budget state and search counters on 12 cold plus 12 resumed fixed-work pairs. Compiler repetitions are not new scenarios.
- The unchanged official checker 1.2.2 accepts 18 generated-case outputs; all 1,152 per-link/time coordinates and total costs reconcile, maximum load difference 8.58e-13 at requested 12 decimals. Three kernel-stress graphs have duplicate demand endpoints: their six outputs remain rejected, not claimed official-valid. Metadata-only checker inputs omit no-op time-zero entries and add network flags without changing the solver workloads.

| Repeated workload | Original median | Candidate median | Result |
| --- | ---: | ---: | --- |
| Large one-waypoint component, 7 pairs | 91.025 ms | 81.218 ms | 10.8% less time |
| Complete cold solve, 9 pairs | 575.310 ms | 577.529 ms | 0.39% slower |
| Complete resumed solve, 8 pairs | 1244.238 ms | 1246.856 ms | 0.21% slower |

The complete solver is effectively flat, not improved. Small component cases also regress; earlier unconditional-merge variants are retained as negatives. One final planned resumed pair was interrupted by the outer command timeout and is excluded rather than imputed. No official public-A/B or competition-strength result is claimed.

The next discriminating hypothesis is whether sorting becomes material after the already-owned distance/comparator/topology improvements, or on genuinely larger flows. No change or rerun of QUARTZ's active benchmark is requested.

## Reproduce

Reuse the existing QUARTZ context named in EVIDENCE.json; all 336 transfer payloads were independently verified. It contains the original solver, RapidJSON, official checker and licenses. From this directory, with C pointing to that extracted context:

```sh
unset CLOUD_INITIAL_SOLUTION SEDGE_STATS
python3 apply_route_flow.py "$C/sources/candidate/main.cpp" /tmp/route-flow-main.cpp
python3 -m unittest -v test_application
python3 generate_fixtures.py /tmp/route-flow-fixtures
python3 build_probe.py "$C/sources/candidate/main.cpp" \
  "$C/sources/sedge/vendor" /tmp/route-flow-build --sanitize
F=/tmp/route-flow-fixtures/bench-large
/tmp/route-flow-build/probe "$F/network.json" "$F/traffic.json" \
  "$F/scenario.json" /tmp/route-flow-probe
```

The native probe embeds both exact production bodies under separate namespaces, changing only class visibility for inspection. Its assembled source is byte-identical to the executed sanitizer source. Omit `--sanitize` for the O3 component build; an optional final positive integer repeats the three timing modes.

The complete evidence archive in EVIDENCE.json retains 813 hashed payloads: all original/candidate sources, fixtures, full solver outputs and counters, raw timing samples, checker reports/rejections, deliberate controls, development alternatives, interrupted attempts and the detailed `delivery/RESULTS.json`. No binaries are distributed. Source, submission draft, attachment, canonical solver and held benchmark decisions remain unchanged. SEDGE/FLORA and the original fleet authors retain credit; see LICENSE and NOTICE.md.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
