# Preserve the continuation incumbent during initialization

The continuation solver formerly wrote an empty-waypoint solution to its output
before reading `CLOUD_INITIAL_SOLUTION`. If the input and output named the same
file, the solver read that newly emptied file instead of the incumbent. It could
exit successfully with `resumed=true` while losing a better existing solution.
The same ordering overwrote an existing output before a malformed, missing,
over-budget or unreachable input was rejected.

The repair moves initial publication after topology and incumbent validation.
The first output is still available before search, using the existing atomic
temporary-file rename. With no supplied incumbent, a validated empty-waypoint
solution is still written. Search, objective comparison, budgets, routes,
neighborhoods, random seed, signal handling and final publication are unchanged.

## Actual witness

A constructed three-node network has a direct 0→2 link of capacity 1 and two
links 0→1→2 of capacity 10. Each link has metric 1; demand volume is 10. The
incumbent waypoint `[1]` gives loads 1 on the two detour links. Using that same
filename as output with `SEDGE_MAX_ROUNDS=0` formerly replaced it with no
waypoints and reported maximum load 10. The repaired binary retains `[1]` and
reports maximum load 1. Zero search moves are involved.

This is a constructed initialization witness, not a new official-checker or
competition score result. Existing SEDGE and FLORA benchmark receipts retain
their original source/time qualifications.

## Reproduce

Extract the updated `source.zip` and build in its `cloud-optimizer` directory:

```sh
make
python3 -B test_incumbent_preservation.py
```

To exercise an independently built source revision:

```sh
ROADEF_SOLVER=/absolute/path/to/solver python3 -B test_incumbent_preservation.py
```

The suite creates temporary actual network, traffic, scenario, incumbent and
output files and invokes the complete compiled solver. It covers exact and
relative/absolute input-output aliases, input/output symlinks, hardlinks, distinct
outputs, zero time/round limits, fixed-round correspondence, malformed in-place
JSON, seven rejected incumbent structures, transition-budget rejection, missing
incumbents, unreachable topology and ordinary nonresumed initialization.

## Source-specific result

Executed September 8, 2026 UTC in the existing cloud workspace using GCC13.3.0,
`-O2 -std=c++20` and the unchanged bundled RapidJSON headers:

| Source | Git blob | Actual result |
| --- | --- | --- |
| Before | `944608368469a84358b3d0e958de32a90678d110` | 14 methods; 17 assertion failures across 10 methods, 4 methods pass |
| Repaired | `b5fe421fe86ed7d7800a74624a1eab4d4fbce1e3` | All 14 methods pass |

The distributed source archive includes the same repair and tests. Its existing
vendor files, wrapper, Makefile, license, historical benchmark summary and
official-checker replay tool are retained byte-for-byte. The original archived
benchmark results are not relabeled as results from the new source. Exact source
and test hashes are in `INCUMBENT-PRESERVATION-VALIDATION.json`.

This is a correctness repair for continuation reuse, not an algorithm-selection
decision or a claim of stronger hidden-instance performance. The separate S139
qualification attachment and submission state are untouched. SEDGE retains base
solver credit, FLORA continuation credit, and the coordinator candidate-selection
ownership. Original Slack claim: `1788838451.219639`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
