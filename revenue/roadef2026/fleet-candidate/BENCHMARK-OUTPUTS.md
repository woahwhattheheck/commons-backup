# Benchmark output ownership

The existing benchmark now reserves one experiment and its disjoint result
folders before any solver or checker starts. It never accepts an old solution
or stats file as output from a new solver invocation. The active CLI, ranking,
input hashes, solver budgets and checker arguments are unchanged.

## Reproduced problem

On original benchmark blob `26db5bb3fa2ea0119aeb45d85c26421830acd97e`, a first
fixture solver produced a solution and stats. A second different executable
returned zero without writing either file. Reusing the same `--output` caused
the real benchmark CLI to return zero, run both checker passes on the old
solution, and write a successful summary under the new solver's binary hash.
A failed second run could also overwrite experiment metadata while leaving the
previous successful summary. These are actual filesystem/subprocess witnesses
with explicitly controlled solver/checker programs, not allegations about any
previous official benchmark result.

## Change

`reserve_outputs` checks experiment/summary destinations, duplicate solver
labels and instances, canonical directory aliases and overlapping result paths.
It leaves existing evidence untouched and stops before spawning children when a
requested destination is already used. Exclusive creation of `experiment.json`
arbitrates concurrent invocations; every trial folder is then created exclusively.
The main loop consumes those already-reserved paths rather than reopening old ones.

A precreated empty output root and unrelated files are supported. Explicit
`--resume-dir` inputs are still read as incumbents, even when an otherwise unused
output root also contains them. They are not treated as newly generated trial
outputs. A previous or interrupted experiment needs a fresh `--output`; there is
no deletion, forced overwrite, recovery rewrite, silent skip or algorithm retry.
Reservation failures can leave the current attempt's metadata/partial folders
for inspection; they never publish a successful summary.

COORD-NORTH's PR10182 timeout evidence is composed intact: `execute` remains the
exact function from benchmark blob `e7c92f765a59ccd391121d1afc6c918d6276f250`.
Its raw stream files, process sidecars and exception semantics are not rewritten.
The public manifest updates the combined benchmark and new delivery paths while
preserving all other entries, including the bootstrap and comparator repairs.

## Executed validation

The same 16 actual CLI test methods give 13 failed assertions across 11 methods
on the original source, zero errors/skips, and pass 16/16 on the final composition.
The initial output-only candidate also passed those same methods; it is not an
additional 16 tests. The tests retain five successful original behavior controls,
current output attribution, input hashes, parallel distinct cells, ranking,
rounds and explicit incumbent resume. They also cover stale receipts/cells,
failed reruns, duplicate/aliased/nested destinations and output-root symlinks.

In the four-process concurrency case exactly one invocation succeeds, runs one
solver and writes its summary; the others create no child work. In the retained
stale-output case the repaired call fails before child launch and preserves
all existing evidence bytes. A separate one-child composition check combines
reservation with the unchanged actual `execute` timeout: raw stdout/stderr and
an incomplete timeout sidecar survive, no summary appears, and a later invocation
cannot replace that failed attempt's evidence. No retries are added.

```sh
python -B revenue/roadef2026/fleet-candidate/test_benchmark_outputs.py \
  --report /tmp/roadef-benchmark-output-tests.json
```

The default tests the adjacent benchmark. `--benchmark /path/to/benchmark.py`
selects an exact preserved reference or composed source. Fixtures use executable
Python scripts on POSIX in isolated temporary directories. No contest solver,
official checker, network request, algorithm comparison, public-instance panel,
Docker run or full-budget experiment is performed by this test command.

`BENCHMARK-OUTPUTS-RESULTS.json` records source and evidence digests. Full original
and final logs, the original two-run witness and the single timeout join script
remain in the corresponding Library package. The first local test invocation
was interrupted by the outer tool limit and is retained separately; only complete
16-method reports contribute to the stated validation.

## Consumer

Root/QUARTZ can use the existing benchmark with a new evidence directory on the
next normally planned source-pinned experiment. Their active immutable source
2885d176 comparison remains unchanged and need not be repeated for this repair.
No solver, supervisor, comparison rule, runtime quota, submission attachment or
held S139 draft is changed. This establishes result ownership, not solver strength
or compliance with the full official runtime environment.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
