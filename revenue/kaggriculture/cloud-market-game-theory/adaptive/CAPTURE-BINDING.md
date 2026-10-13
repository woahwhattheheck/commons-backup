# Scoped optimizer capture

`runtime.Agent` now installs its collector only around its own single parent
call and restores the previous binding in `finally`. Construction no longer
mutates `selected_action_sell.optimize_lot` or binds one actor to another.
Baseline and already-active-plan turns use the same optimizer without building
new offers that the existing admission path does not consume. New-admission
capture, optimizer results, offer order, recourse and continuation logic are
unchanged. The `feasible_candidate_windows` diagnostic now counts only useful
new-admission collection, not discarded baseline/active-turn work.

## Executed regression evidence

The original runtime is Git blob
`580009b4023e17130e7169445aae3639e34529b9` in PR10008, unchanged on base
`c6682ec47a50f32faff9181961f8f5c995f3bf6a`. The repaired runtime blob is
`2408104e5014ed006eea60066c762eaa67dd6a1a`.

All 22 focused methods pass on the repair. The same suite fails 18 methods on
the exact original. It covers sequential and nested actors, record ownership,
error identity and single invocation, restoration on normal return and
exceptions (including BaseException), previous binding preservation, unused
offer suppression and actor garbage collection.

A constructed 64-actor boundary witness causes 192 capacity checks and updates
64 collectors on the original, versus 3 checks and one collector after the
repair. Both execute one parent call. This is an operation-count comparison,
not a measured whole-game speedup.

The actual frozen optimizer is also executed on 108 product/quantity/inventory
cases: all complete plan and receipt results match direct invocation. All 108
cases activate offer capture. In the retained actual-optimizer example,
baseline and active turns use 27 capacity callbacks rather than 30, while
new-admission capture keeps all 30. Tests reuse the existing source artifact,
not a new engine or exporter. Exact source and deterministic output hashes are
in `capture-binding-validation.json`.

The tests compile the verbatim production `Agent` class with explicit parent
and observation fixtures so this binding boundary can be exercised without
loading unrelated controllers. They separately import the actual optimizer.
These are component tests, not full-agent integration or games.

## Reproduce

From a repository checkout with the existing dependency layout:

```sh
python -B revenue/kaggriculture/cloud-market-game-theory/adaptive/test_capture_binding.py
```

The default optimizer is the existing `cloud-execution-lab/selected_sell_core.py`.
To reproduce the original local evidence exactly, pass `--optimizer` with the
frozen scheduler SHA256
`32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9`,
already present in artifact10030763484's `carrot-cap-checkpoint.tar.gz` as
`vendor/sell/scheduler.py`. `--runtime` accepts the original runtime for the
negative control; `--report` writes a JSON execution summary. No game seeds are
consumed by this command.

## Remaining runtime question

The two PR10008 held COK attempts remain incomplete. This repair does not
attribute or resolve their one-second deadlines. The evaluator normally
isolates actors in processes; the lock additionally serializes parent calls
through this runtime module and is reentrant for nested actors. It does not
coordinate unrelated direct seller calls from other threads, and module reload
during an active call is not a supported concurrency contract.

T15/RULE and FINCH can consume this runtime directly without another wrapper.
SPRUCE's separate score-loop optimization is compatible and remains in its own
source path. Reuse the exact failed-call inputs for further profiling; do not
reinterpret original held records as successes after this source change.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
