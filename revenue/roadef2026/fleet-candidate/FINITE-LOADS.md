# Finite load reconciliation in the existing benchmark

## Reproduction and change

The actual benchmark CLI at original blob `dc9f3df9` accepted a diagnostic NaN
against a finite checker load. It returned success, marked the row valid and
published `max_load_error: NaN`. A NaN later in the vector can instead disappear
behind a finite maximum, producing a misleading zero error. Non-finite values
in the six-decimal ranking stream could pass while the twelve-decimal load
reconciliation remained finite.

The benchmark now checks every saturation from each checker response and the
solver's diagnostic load list before sorting or reducing the differences.
Ordinary finite values are never rounded or replaced; the original 2e-9 error
threshold, coordinate matching, costs, ranking and output schema remain intact.
The existing subprocess capture, timeout exception handling and exclusive output
reservation are unchanged. There is no new checker, runner or report protocol.

This is not PORT/HAZEL's separate `compare_checker.py` precision parser. No native
checker serialization rule is added here, and no precision band is restricted.
The failure witnesses use controlled executable solver/checker fixtures; no
previous official benchmark is alleged to have emitted these invalid values.

## Executed evidence

The final 14-method suite exercises 22 actual CLI cases. All pass. The identical
suite against the original benchmark has ten failed assertions across seven
methods, zero errors. Cases cover NaN in either vector position, either checker
precision stream, diagnostic infinities, matching infinities, exponent overflow,
finite integer/scientific/zero values and unchanged tolerance behavior. Finite
subtraction overflow still fails through the original error comparison.

The three successful finite protocol cases also produce identical semantic
result rows on old and new source: exact load values, maximum error, solution
hash, input hashes, counters, cost and result status. Filesystem locations and
wall measurements are not compared as deterministic values. The native-style
9.933579335793359e-7 value is retained exactly, not rounded to six decimals.

Three unchanged output-ownership methods additionally pass on the new benchmark:
parallel ranked instances, explicit incumbent resume/rounds, and concurrent
single-owner publication. These are three retained methods, not new tests. All
three original helper function ASTs (`digest`, `execute`, `reserve_outputs`) are
identical. No official solver/checker, algorithm screen, Docker or full-budget
experiment ran for this repair.

Rejected numeric data still has its original stats file, captured checker
stdout and completed-process sidecars. Protocol failure is distinct from child
process failure. No per-cell successful result or complete summary is created.
No retry, silent repair or replacement with a finite default is performed.

## Reuse

```sh
python -B revenue/roadef2026/fleet-candidate/test_benchmark_finite.py \
  --report /tmp/benchmark-finite.json \
  --evidence /tmp/new-benchmark-finite-evidence
```

Use `--benchmark` to target a preserved original or another exact composed file.
The test reuses the existing `test_benchmark_outputs.py` fixture construction but
does not execute that file's original suite. `--method` selects one named method
and may be repeated when the outer harness requires bounded execution shards.
The final local result uses fourteen separate named-method reports on the same
source. Two interrupted earlier full-suite attempts and one preliminary check
are retained separately and do not increase the final count.

`FINITE-LOADS-RESULTS.json` binds source, fixture, test and per-method evidence
hashes. The accompanying Library package retains all raw original/fixed protocol
bytes, CLI logs, failed and completed attempts, and the original minimal witness.
The normal benchmark consumer needs no new option; use a fresh `--output` on the
next already-planned run. Historical results and ongoing source-frozen runs are
not recomputed or relabelled. S139 submission and attachment remain unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
