# Terminal runtime recovery and composition

This is one source-candidate packet inside `main:candidates/v4`, not a new V4 branch, controller, production package, or activation. Production `main.py`, `titan_runtime.py`, `deadline_adapter.py`, defaults, archive and Kaggle state are unchanged.

## Recovered work and new build

The unpublished terminal-slot repair was recovered from `titan-v4-terminal-fallback-custody.patch` (SHA256 `c138c5aeca2c09476d127d81bc23ce1e4679c9951739945fc177729da46fe549`). Its transformer and 25-test engine suite are preserved byte-for-byte. The transformer matches the engine's minimum-one market-order clamp and fills otherwise-inert animal SELL slots with omitted products without moving any already-executable product SELL's raw row index.

Cross-channel review also recovered the distinct terminal-precedence donor #11913 and its outer-entrypoint evidence child #11927, both closed without merging. Their exact source files are preserved under `legacy/`; no old workflow or sibling V4 tree is revived. The legacy generator accepts pinned source blobs, not a particular checkout commit. Its `base_commit` field is historical provenance only. Do not run its in-place two-file writer on a production checkout.

`test_terminal_composition.py` is new. It tests four arms: predecessor, slot-only, precedence-only, and composed. It executes the exact current `main.agent`, the real main-thread signal timer and worker-thread trace timer, and the pinned official interpreter. Only the producer is a test double. Tests cover both seats, preselection and post-selection cancellation, step-717 parity, successful-call parity, one producer call, foreign-sentinel identity, instance invalidation, observation non-mutation, and trace/context/signal-handler restoration. Worker tests reject all process-global signal writes.

The important interaction is executable: fixing slots alone does not help when a post-selection timeout returns the raw producer action instead of liquidation. Conversely, fixing fallback precedence alone can still leave product lots crowded out. Both mechanisms are needed for the constructed combined witness.

## Fresh execution, Python 3.13.5

| Suite | Normal | `-O` | Scope |
| --- | ---: | ---: | --- |
| Recovered engine regressions | 25/25 | 25/25 | Exact adapter and full pinned interpreter; includes 704 constructed randomized cells per mode |
| New real-timer composition | 6/6 | 6/6 | 80 entrypoint invocations per mode: 72 recorded cases plus 8 foreign-sentinel cases |
| Existing compatibility checks | 11/11 | 11/11 | Older materialized runtime; worker deadline, entrypoint clock, module recovery |

Total: 42 passed in each mode, zero failures or errors. Counts across modes repeat the same scenarios, not independent games. The compatibility artifact's other runtime files are older than current main; those 11 tests are not full-current-V4 evidence. The new six tests do not execute the full current `TitanAgent` implementation. No natural hosted activation or ladder-strength gain was measured.

Constructed finalization-timeout results, reproduced in both seats and both thread modes:

| Arm | Product-first fixture cash | Crowded fixture cash |
| --- | ---: | ---: |
| Predecessor | 0 | 0 |
| Slot-only | 0 | 0 |
| Precedence-only | 730 | 700 |
| Composed | 730 | 11,268 |

These are fixture outcomes, not per-game gains. `validation.json.gz` contains all fresh logs, focused receipts, and complete composition rows. Its SHA256 is `739036806321c5f0e8b46ecf744bcb37044445e5751408df40614388e5840f57`.

## Reproduce

Use a source/package `LAB` containing the pinned adapter and offline engine/evaluator cache. `CURRENT_MAIN` must be current source blob `4a8cf7bcda1f0fea231a144692cb84a779a9e73e`, not the older artifact entrypoint. The source and donor checks reject drift.

```sh
HERE=revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/runtime/terminal-fallback
python "$HERE/test_terminal_fallback.py" --lab-root "$LAB" --receipt /tmp/terminal-normal.json
python -O "$HERE/test_terminal_fallback.py" --lab-root "$LAB" --receipt /tmp/terminal-optimized.json
python "$HERE/test_terminal_composition.py" --lab-root "$LAB" --main-source "$CURRENT_MAIN" --receipt /tmp/composition-normal.json
python -O "$HERE/test_terminal_composition.py" --lab-root "$LAB" --main-source "$CURRENT_MAIN" --receipt /tmp/composition-optimized.json
```

The offline source/engine artifact used here is Actions artifact `10285621024`, SHA256 `5ff92183fedce1ff8071b35e8e97dc23dc1ea7762ee47260c7ff2be2d0d2bc94`. Its adapter matches current source exactly. Engine blobs are recorded in `RECOVERY.json`.

## Integration boundary

Main source pins were rechecked at `c42f8bea0604ef4a37ced51105ffb9e6f3c84a32`. Keep this packet in the existing V4 workspace. Complete-current-runtime/packaged-entrypoint validation remains NOT_RUN. Before activation, compose against the current three source pins, rerun the actual current runtime and package, and reconcile the existing #11913/#11927 review lineage. A changed source or equivalent earlier repair must be reconciled, not overwritten. No production promotion is implied by preserving these sources or by the component-level test results.
