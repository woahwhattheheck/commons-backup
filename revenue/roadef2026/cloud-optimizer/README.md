# ROADEF 2026 continuation optimizer

This is a distinct, monotonic continuation stage for SEDGE's existing
ROADEF/EURO 2026 T-adaptive segment-routing solver. It does not replace or
rewrite SEDGE's solver. It loads an incumbent solution, reconstructs every
route and load, rejects malformed, unreachable, over-segment, repeated-node,
duplicate-index, or over-budget incumbents, and then searches complementary
local time windows. A move is written only when its six-decimal sorted load
vector is strictly better than the current incumbent.

The added neighborhood tests symmetric windows of radius 1, 2, and 3 around a
critical time slot before the original prefix/suffix moves. This targets route
changes that fit transition budgets but are not expressible as a single-slot,
full-prefix, full-suffix, or whole-horizon move. Resumed runs enter that
neighborhood immediately.

## Build and run

Download and extract [source.zip](source.zip), then:

```sh
make
SEDGE_SECONDS=60 ./run.sh network.json traffic.json scenario.json incumbent.json result.json
```

`result.json` is initialized from the validated incumbent before search. The
same `SEDGE_STATS` and `SEDGE_MAX_ROUNDS` diagnostics used by SEDGE remain
available. The optimizer is deterministic for a fixed round limit; a wall-time
limit can stop at a different accepted move on different machines.

The incumbent and output may name the same file. Initialization now finishes
reading and validating the incumbent and topology before the first atomic output
replacement; a rejected input leaves an existing output unchanged. The earlier
version could erase an in-place incumbent before reading it. Fourteen real-binary
regression methods cover this boundary; see
[INCUMBENT-PRESERVATION.md](INCUMBENT-PRESERVATION.md). This save-order repair does
not change the search neighborhoods or claim a new benchmark improvement.

## Measured public-instance result

The checked experiment used exact official challenge commit
`d84d319a7fdb8de3b1866830d2eaa2937871e5ae`, networktools commit
`aebafc9ee91891e5d721bb86725e8cf1533877d1`, and official checker v1.2.2.
Each incumbent came from unchanged SEDGE for four seconds. The continuation
then received two seconds. All 12 set-B outputs remained checker-valid and
non-regressing under the official six-decimal lexicographic ranking; eight
were strictly better and four were equal. Every predicted load agreed with the
official checker within `2e-9`, and all reported transition costs matched.
See [benchmark/summary.json](benchmark/summary.json) for exact per-instance
first-change ranks, scores, hashes, costs, and timings.

This is a bounded continuation tradeoff: extra search time can improve an
already-feasible incumbent without discarding it. It is not evidence that a
short staged run beats every uninterrupted longer SEDGE run; equal-total-time
trials were mixed, so this package makes no such claim. Hidden-instance
performance and competition rank remain unknown.

Reproduce after independently building the pinned official checker and
generating SEDGE incumbents in `<baseline-dir>/<instance>/solution.json`:

```sh
python3 verify_resume.py \
  --data /path/to/challenge-roadef-2026 \
  --checker /path/to/checker-v1.2.2-x86-64_linux \
  --baseline-dir /path/to/sedge-results \
  --output replay --seconds 2 --workers 4
```

## Boundaries and attribution

This is tested code, not a registration, qualification submission, acceptance,
award, or Orange result. Root/Archimedes retain registration and submission
ownership; the organizer-issued team ID is still required before qualification
mail. SEDGE retains credit for the base solver, its accepted public-instance
results, container proof, and packaging. The continuation implementation is
derived from SEDGE's MIT-licensed source; RapidJSON remains under its bundled
upstream license. Official challenge data and checker belong to Orange and are
not redistributed here.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
