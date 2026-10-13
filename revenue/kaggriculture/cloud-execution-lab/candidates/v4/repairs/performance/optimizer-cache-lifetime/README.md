# Native optimizer cache lifetime

Source-component repair for the single `main:candidates/v4` integration line.
Status: **SOURCE_COMPONENT_TESTED_NOT_RUNTIME_PROMOTED**.

## Change and ownership

`MarketPath.single` and `.joint` are instance-owned `lru_cache` wrappers around
bound methods. The wrappers keep their owner alive after a private `optimize_lot`
call returns, retaining receipt tables until cyclic garbage collection. This is
collectable retention, not a permanent leak.

`repair_cache_lifetime.py` preserves every original optimizer statement and wraps
only use of its private model in `try/finally`. The finalizer clears the quote,
single and joint tables, then deletes the two bound-method wrapper attributes.
Clearing tables alone would leave the owner cycles intact. Public standalone
`MarketPath` caching remains unchanged. Production GC settings are never changed.
The transformer rejects model rebinding, suspension, and model escape beyond
immediate `score` calls, plus source-pin/constructor drift and double application.

Native selected core: `f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3`
-> `aab42542442dafaf9853a06fb057460526f777c6`.
Optional scheduler optimizer: `a483b24dd72b580d7d8811636b54d2d44f391575`
-> `329668f963133b94443577723fe559210446d552`.

**No `frozen_selected` receipt wrapper is delivered.** FUNDING-PERF's earlier
call-local model-pool owner retains that surface. A borrowed model must not be
disposed after each receipt; dispose owned pool models at the enclosing funding
call's exit. The overlapping baseline-only experiment was withdrawn in claim
thread `1789180616.027249` before publication.

SIEVE retains incumbent-bound pruning; MEADOW/EVENTPATH/PRESSURE-PERF retain their
math and quote optimizations. To compose a reviewed optimizer successor, supply
its full Git blob explicitly. The transformer proves original statement/module
AST preservation after stripping only its new scope. An explicit pin is an
identity check, not an independent review of arbitrary source. Real SIEVE
composition is **not** included in this receipt.

## Reproduce

Use the existing complete native source package, not the legacy R04 materializer.
`ROOT` below denotes the package root containing `selected_sell_core.py`,
`scheduler.py`, `mechanics.py`, and `reference/decision/decision.py`.

```sh
python test_cache_lifetime.py --runtime "$ROOT" --receipt tests-normal.json
python -O test_cache_lifetime.py --runtime "$ROOT" --receipt tests-optimized.json
python benchmark_cache_lifetime.py --runtime "$ROOT" --receipt benchmark.json
python repair_cache_lifetime.py "$ROOT/selected_sell_core.py" /tmp/selected-core-candidate.py
python repair_cache_lifetime.py "$ROOT/scheduler.py" /tmp/scheduler-candidate.py \
  --expected-source-git a483b24dd72b580d7d8811636b54d2d44f391575
```

The CLI exclusively creates its output and refuses overwrites/aliases. It does
not update imports, source mirrors, manifests, production files, or archives.
Compose outputs using the existing package owner and its current-head gates.

## Executed evidence

CPython 3.13.5: **16/16 normal and 16/16 optimized**; each mode checks 364 selected
optimizer plus 45 scheduler complete result/diagnostic/ordered-capacity pairs.
Tests include all nine products, all three acceptance rules, forced/no feasible
capacity, terminal/carry boundaries, custom quotes and scenario weights,
reentrancy, unchanged GC settings, public cache reuse, and exception identity.
Both ordinary errors and `BaseException` interruptions empty the owned tables.

Two unchanged native control suites also pass with the scoped optimizer modules:
`test_joint_market_slots.py` **28/28** and `test_funded_prefix.py` **8/8**, normal
and optimized. The temporary native package's attributed selected-source mirror
was updated to match its derived core; frozen vendor controls were not changed.

One 32-call, quantity-24 WHEAT microbenchmark with automatic GC enabled measured
peak traced allocations **1,409,671 -> 167,383 bytes**, with retained models
**9 -> 0**. With cyclic GC paused only for the diagnostic, retained models were
**32 -> 0**, and peak allocations **3,558,751 -> 167,383 bytes**. Timings were
measured separately without tracemalloc, alternating arm order over five rounds:
automatic-GC median **1.756 -> 1.707 ms**, p95 **2.315 -> 2.023 ms**. These are
bounded workload measurements, not generalized speed, deadline, or strength
claims. Full details and provenance are in `VALIDATION.json`.

## Explicit limitations

The artifact's old-vendor `test_selected_pruning.py` already fails 50 subcases
against its active core's extended output schema; the same count occurs with the
candidate. `test_ordered_selected_sell.py` already lacks its `arrival_contract.py`
fixture; its one error also reproduces on the untouched baseline. Neither suite
is claimed green. The complete gate is not replaced by this component evidence.

Python 3.11 and full-game A/B were not run. No production/default/config/archive,
Kaggle, opponent/evaluator, provider, or Actions-dispatch change is included.
