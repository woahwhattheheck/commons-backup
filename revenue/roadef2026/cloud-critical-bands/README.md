# Optional critical-rank expansion for ROADEF

This is a source-preserving, opt-in search variant of the existing fleet solver,
not a replacement portfolio or qualification submission. Root/SEDGE/FLORA retain
the routing kernel; ASTRA-PERF proposed the rank-band experiment; TRACE-9022
implemented and measured this component. QUARTZ supplied the exact source/checker
context, completed B12 incumbent, and unchanged process-resource observer.

## Mechanism

The original solver targets only the current top 32 link/time load coordinates
and stops after 64 stalled rounds. With `FLEET_CRITICAL_BANDS=1`, this variant
tries ranks 1–32, then 33–64, 65–128, and successively doubled ranges after two
unsuccessful passes over a range. Any accepted move resets critical selection to
the highest range. Sorting retains the original load/coordinate tie order.

The default is **disabled**. `FLEET_CRITICAL_BANDS=0` uses the original scheduling
and stopping rule. `FLEET_CRITICAL_MAX_RANK` optionally caps exploration; zero or
unset means every coordinate, subject to the original process/round limits.
`FLEET_BAND_STATS` optionally names a JSON diagnostics file containing exit reason,
largest critical rank visited, expansions, and proposals/accepts per band. Ranks
refer to the current sorted loads, not immutable initial coordinates.

The builder changes only one include and sections of `run()`. All other original
methods, including `moveTogether`, exact ECMP, route and budget checks, contributor
selection, waypoint ranking, ejection, checkpoint writing and ordinary statistics,
remain byte-identical. The strict full-vector objective is unchanged. This is a
new search schedule, not a claim of optimality or a computational speedup.

## Build and execute

Start from the exact fleet source at `2885d176373c33410148829fef93c310c3752c0b`
(`main.cpp` SHA-256 `322ec2e6bec9ab17c4cdf74c52d8e40414ce90cf60f9e53aaee2531cce652ab1`).
The already-delivered QUARTZ context provides original RapidJSON, checker and
Networktools sources with their licenses. No new download workflow is needed.

```sh
python3 build_candidate.py --base /path/fleet-candidate/main.cpp --output /tmp/rank-build
g++ -std=c++20 -O3 -DNDEBUG -I/path/fleet-candidate/vendor \
    /tmp/rank-build/main.cpp -o /tmp/rank-build/candidate
FLEET_CRITICAL_BANDS=1 FLEET_BAND_STATS=/tmp/bands.json SEDGE_SECONDS=60 \
    CLOUD_INITIAL_SOLUTION=/path/incumbent.json \
    /tmp/rank-build/candidate network.json traffic.json scenario.json /tmp/result.json
```

Use a new output directory and separate solution paths. The builder validates each
anchor once and refuses reapplication. Other independently changed kernel methods
can compose when those anchors remain intact; no such combined-kernel quality
result was measured here. `SOURCE.json` records exact generated/header/base hashes.
The generated measured source is `917874d5c9bb8e5ff1f8ebc0e0e0f459ea7d1cbab44473423809cd48cfdc5a0c`.

## Validation and observed results

Eighteen fixed-work/source tests pass. Original/default/disabled outputs preserve
solution bytes, complete native loads, budgets and search counters. Cases cover
rank caps 32/40/41, round/time boundaries, deterministic replay, resumed incumbents,
noncontiguous node IDs, improvement reset and source-preserving application.

A manufactured bidirected 5-node, 10-arc, 40-slot network places 40 unavoidable
load-2 coordinates above an improvable demand. Original and cap-32 controls stop
before that demand; expansion reaches rank 41 and changes its saturation from
1.0 to 0.1. The first 40 coordinates remain 2.0 and transition cost remains zero.
All four witness outputs pass the pinned official checker at 6 and 12 decimals.
Complete 400-coordinate correspondence is retained; this is mechanism evidence.

The public development study reuses only QUARTZ's completed B12 selected incumbent
`a1c4df68fd610c1ca0a65b5a6c7faab03202dfa53e8af2c4fb23c87fc6b83e53`.
No original full-budget execution or LANDING configuration cell was repeated.

| Run | Allowance | Actual native seconds | Rounds | Largest rank | Accepts | Official result versus incumbent |
|---|---:|---:|---:|---:|---:|---|
| Disabled, first pair | 30 | 30.0010 | 51 | 32 | 0 | Identical |
| Enabled, first pair | 30 | 30.0011 | 52 | 32 | 0 | Identical |
| Enabled, second pair | 60 | 60.0010 | 115 | 33 | 2 | Better at rank 33 |
| Disabled, second pair | 60 | 36.5755 | 64 | 32 | 0 | Identical; original stall exit |

The first pair did not reach the unchanged 64-round plateau. Before further
execution, the second pair was declared with the same source, thresholds and
incumbent, a 60-second allowance, and reversed enabled/disabled order. Neither
source nor the expansion threshold was tuned between the two pairs.

The enabled second arm improves the exact six-decimal vector at rank 33:
**0.296067 to 0.294548**. Peak 0.629742 and total transition cost 50 stay unchanged.
That lower band makes four proposals and accepts two ordinary moves, then resets
to top-rank priority. All four outputs pass the pinned checker at both precisions;
each of their 53,448 native load coordinates agrees within `1.00001e-12` at 12dp.
The three unchanged solutions are byte-identical to the incumbent.

These are single executions from **one public development incumbent**, not a
statistical generalization, qualification-rank result, or replacement decision.
The optional code adds no network, provider, team-specific or instance-name logic.
S139's draft, attachment and submission were not modified.

## Reproduce the component checks

The evidence package retains the working layout below. With `WORK` pointing to
that layout, compile the original to `$WORK/bin/original`, the generated candidate
to `$WORK/bin/bands`, and the checker to `$WORK/bin/checker`.

```sh
TRACE_CRITICAL_WORK="$WORK" python3 -B test_critical_bands.py
TRACE_CRITICAL_WORK="$WORK" python3 -B check_witness.py \
    --checker "$WORK/bin/checker" --output /tmp/new-critical-witness
# Data-only inspection of retained outputs, with no solver or checker calls:
python3 -B check_witness.py --output "$WORK/evidence/witness" --read-existing
```

For B12, the saved `EXPERIMENT.json`/`EXPERIMENT-60.json`, command arrays and
QUARTZ `measure_command.py` provide the original invocation/resource contract.
Unset `SEDGE_MAX_ROUNDS`; run the two flags separately with the same incumbent,
normal original directed/joint/waypoint defaults, and separate outputs. Compare
only exact native checker outputs using the unchanged `compare_checker.py`; cost
remains diagnostic rather than a tiebreak. Full raw files and inactive attempts
are included in the Library evidence package named in the delivery receipt.

## Execution scope

Solvers compiled with GCC 14.2, `-O3 -DNDEBUG -std=c++20`. The unchanged checker
compiled with `-O1 -DNDEBUG -DLANG_EN` after an earlier `-O3` compilation exceeded
the tool execution limit. That preparation attempt is retained, not a solver
failure or an official-image claim. No code or archive pin was substituted.

The measured container has a 4-CPU cgroup quota and 4 GiB memory limit. QUARTZ's
unchanged observer samples process-tree RSS at 0.5 seconds; observed peaks are
about 446,116 KiB, excluding page cache and possible between-sample peaks. The
native `seconds` measure includes model preparation but precedes final output/
statistics writing. Full outer wall/user/system measures are retained separately.
This is not the official resource environment, Docker validation, or hosted timing.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
