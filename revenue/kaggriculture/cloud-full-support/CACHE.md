# Reuse identical exact receipt tables

`solve_full_table` now retains at most 64 completed return records in a
process-local least-recently-used cache. Its existing signature, output fields,
exact simplex algorithm, certificate construction and baseline behavior are
unchanged. This is part of the existing full-support core, not another solver,
selector, provider wrapper or controller.

The cache key is the entire ordered canonical rational matrix plus `max_pivots`
and `max_bits`. Equal rational spellings share an entry. Changed row/column order,
shape, any entry, or either budget does not. Input validation still occurs before
lookup, including rejecting Boolean budgets even though Python compares them
equal to the corresponding integers. Errors are not retained as return records.

Each public call returns a deep copy. A consumer can mutate every returned array
or attach metadata without changing another actor's result. Only mathematical
input/output records are cached: there is no observation, action, actor, physical
feasibility verdict, random draw, or ongoing commitment in the cache. Existing
PRISM/T15 checks and per-actor sampling remain in place. In particular, a cached
positive payoff solution is not a cached claim that a plan is physically feasible.

## Consumption and counters

Existing imports and callers need no change:

```python
from full_support import solve_full_table, table_cache_info, clear_table_cache

answer = solve_full_table(deltas, max_pivots=128, max_bits=512)
counts = table_cache_info()  # detached hits/misses/maxsize/currsize dictionary
clear_table_cache()          # release retained records and reset counters
```

`pivots` in the returned certificate describes the solve that produced it; a hit
does not perform those pivots again. The result remains byte-for-byte equivalent
under JSON serialization to re-solving the same input and budgets. A limited
result remains limited; a high-budget positive solution cannot satisfy a
zero-pivot request. The original exact-zero baseline preference is unchanged.

This is bounded by entry count, not a claimed byte-level memory budget. The
implementation introduces no single-flight scheduler. The independent checker
and existing selector may still do their own work after the solver returns.
A separate worker process has its own cache. No game-policy promotion, evaluation
freeze, legacy export archive, or peer implementation is changed.

## Executed validation

The new 15-method suite passes with zero failures, errors or skips when supplied
with the exact original core and actual T15/PRISM files. It covers detached outputs,
input mutation, canonical keys, row/column ordering, budget separation, invalid
input, LRU eviction, explicit release and parallel consumers of a warmed entry.

One generated matrix for every supported dimension pair (1..9 by 1..32) retains
the complete original result on first use and on a hit: 288 matrices and 576
exact full-result comparisons. No new LP oracle or original game panel was run.
The original simplex body is unchanged apart from moving normalization to the
public entrypoint; algorithm and certificate statements retain their ASTs.

The actual PRISM factory and unchanged T15 transform were exercised, not replaced
by a new selector: 12 fresh actors over four synthetic decision dates produce
48 identical actions, active states and decision records against the original
core. Each actor still makes one provider call and one random draw. The shared
mathematical input produces one cache miss and 11 hits. Other cases verify that
physical infeasibility still checks all constituents and that budget/zero results
keep the fallback without a draw. These are consumer fixtures, not engine games,
observed fills, full-agent timing, or a replay of ASH's separate continuation work.

Exact dependency blobs in the retained run:

- Original core: `b04f7bc4ff2137dee4b70ec6f10e7f02ccaebd06`, from
  `362ed415140f420d1727a1111af2dda1579065bd`.
- PRISM weighted selector: `2c21f8975a64961aec0b94fc6ea930318fec111b`.
- T15 selector: `546b71188fd44dc47cac99623d1967bc81413da7`; its original comparison
  solver: `3a6446d96e8470374dd5b5ba72a8e5c6d41a8ad3`.

## Measured cost and benefit

Python 3.13.5; six synthetic workloads; 16 blocks with alternating original/new
order and 12 calls per arm per block. Cache-hit and cache-miss paths were measured
separately. All 2,304 benchmark result pairs match the original complete output.

| Workload | Original median on hit comparison | Cached hit median | Median speedup | Added miss median |
|---|---:|---:|---:|---:|
| Zero, 1 x 1 | 0.057830 ms | 0.011988 ms | 4.82x | 0.012965 ms |
| Three-support, 4 x 3 | 0.316832 ms | 0.022203 ms | 14.27x | 0.023545 ms |
| Eight-support, 9 x 8 | 2.236511 ms | 0.063689 ms | 35.12x | 0.042092 ms |
| Repeated columns, 9 x 32 | 5.530210 ms | 0.196560 ms | 28.13x | 0.069472 ms |
| Terminal-shaped varying baseline, 3 x 2 | 0.135044 ms | 0.016785 ms | 8.05x | 0.014396 ms |
| Terminal-shaped mixture, 4 x 3 | 0.257991 ms | 0.022879 ms | 11.28x | 0.018523 ms |

Imports and explicit cache clearing are excluded; input normalization, lookup,
validation, detached copying and miss computation are included. Miss overhead
is real: workloads with no reuse gain nothing from hits. Actual application hit
frequency and end-to-end agent speed are unmeasured. The terminal-shaped inputs
use the same mathematical embedding as LARCH, but are algebraic examples, not
PORT engine receipts or an execution of LARCH's whole module.

`CACHE-RESULTS.json` retains source identities, the full test log, corpus/report
fingerprints, consumer counts and benchmark distributions. It is a compact
receipt, not the full raw timing transcript. The benchmark command emits every
paired timing sample and all expected results for a new run; the test command
emits per-matrix identities/results and all 12 four-action consumer sequences.
Original `VALIDATION.json` remains the earlier source-specific delivery receipt.

## Reproduce in an existing cloud checkout

Use a new temporary directory; no new clone or source export is necessary:

```sh
RUN=$(mktemp -d)
git show 362ed415140f420d1727a1111af2dda1579065bd:revenue/kaggriculture/cloud-full-support/full_support.py > "$RUN/original.py"
python3 -B revenue/kaggriculture/cloud-full-support/test_table_cache.py \
  --reference-file "$RUN/original.py" --output "$RUN/tests.json"
python3 -B revenue/kaggriculture/cloud-full-support/benchmark_table_cache.py \
  --reference-file "$RUN/original.py" --output "$RUN/benchmark.json"
```

A partial checkout can additionally pass `--t15-dir` and `--weighted-dir` to the
test command. Missing reference/consumer files are reported as skips, not full
joined coverage. Standard-library cache-only checks remain usable without them.
Both report CLIs use a new output filename rather than overwriting a retained run.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
