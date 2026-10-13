# Demand-loaded native history (ASTRA-FOUNDRY)

This source-only performance repair belongs to the ONE canonical `main:candidates/v4` workspace. It composes into the current `terminal_history_join.py` (Git blob `f878320d293dbf08fda24dc66f1805702a6c763c`); it is not another agent, feature key, V4 branch, or legacy r04 materializer. No production source, archive, configuration, or Kaggle submission is changed by this bundle.

## Mechanism

With `terminal_history=false`, a new join does not import or construct its mechanics/fill/history/flow/scenario dependencies until a real observed transition or an explicit public `bridge`/`m` access needs them. `remember(..., post=None)`, empty observations and disabled transforms stay dependency-free. With terminal history enabled, construction stays eager. Stateful bridge/ledger/history objects remain per-agent; only the existing completed path-keyed stateless module cache is shared.

First-use construction publishes one complete `(mechanics, bridge)` tuple. A canceled dependency or constructor publishes nothing. `observe` resolves the bridge BEFORE consuming the pending transition, so canceled first-use initialization can retry the same public transition. Normal public property reads and assignments are preserved. This does not change the deadline, selected actions, solver, fills, or market ordering.

## Executed evidence

New suite: **14/14 normal and 14/14 `-O`** on Python 3.13.5. Per mode: 43 full official-interpreter transition cases across both seats, 36 actual native runtime calls with exact returned-action/state parity, five dependency cancellation points, three constructor cancellation points, and actual main-thread signal plus worker-thread deadline cancellation/retry. Six broken implementations fail behavioral assertions in EACH mode (including the unchanged eager predecessor, premature pending consumption, wrong period, per-access reconstruction and shared agent state).

Eight explicit existing regression classes: **70/70 normal and 70/70 `-O`**. The broader module-discovery run is NOT green: both the unchanged archive and the candidate produce the same 107-test result, one failure plus five errors. The failure is the pre-existing idle-fertilizer entrypoint-prelude PASS-vs-SOUTH case; the errors repeat the missing packaged `checks/reference/selected-action/t08/arrival_contract.py` fixture through imported test classes. These baseline/package limits were reported to the existing CI/lifecycle owners and are not masked or repaired here.

Six paired cold-process runs per mode, alternating execution order, with no bytecode cache: median native initialization 69.72 -> 58.07 ms (16.7% lower); constructed step-0 whole-entrypoint 80.57 -> 69.92 ms (13.2% lower). All paired outputs match and all calls complete. These are LOCAL cold-start microbenchmarks, not full-game, production-load, deadline-rate, leaderboard, or economic-strength results. They shift first-use history cost to real demand rather than eliminating that cost.

## Reproduce

Set `RUNTIME` to an extracted canonical native archive and `HERE` to this directory. The composer refuses in-place CLI overwrites and rejects ambiguous, drifted or partial edits; unrelated source bytes are retained.

```sh
python "$HERE/build_lazy_history.py" "$RUNTIME/terminal_history_join.py" /tmp/terminal_history_join.py
python "$HERE/check_lazy_history.py" --runtime "$RUNTIME" --receipt /tmp/history-normal.json
python -O "$HERE/check_lazy_history.py" --runtime "$RUNTIME" --receipt /tmp/history-optimized.json
python "$HERE/run_lazy_history_controls.py" --runtime "$RUNTIME" --receipt /tmp/history-controls.json
python "$HERE/benchmark_lazy_history.py" --runtime "$RUNTIME" --pairs 6 --receipt /tmp/history-timing.json
```

For the existing regression suite, copy the runtime to a disposable directory, compose only its `terminal_history_join.py`, and run from that copy (repeat with `python -O`):

```sh
PYTHONPATH=.:checks python -m unittest test_terminal_history_join.Joined test_module_recovery.ModuleRecovery test_entrypoint_deadline.EntrypointDeadlineTests test_entrypoint_clock.EntryClock test_worker_deadline.WorkerDeadline test_idle_fertilizer.IdleFertilizerTests test_crop_release.CropPreparationContracts test_route_recovery.RouteRecovery
```

`RECEIPT.json` pins source, engine, artifact, generated output, new verifier/runner/benchmark bytes, and the executed result limitations. The current-runtime integrator should consume this ONE recipe after whole-current-package composition validation; it does not authorize production/archive/default changes. Scope is complete and released once merged, not an abandoned open claim.
