# Preserve known results when executor diagnostics fail

The existing `cloud-model-lab/execute_arm.py` now carries a known attempted-cell
result through an ordinary escaped executor exception. Its CLI saves that row
using the existing atomic `write_checkpoint`, then re-raises the same exception.
It does not retry the actor, continue the panel, or call a failed batch complete.

Previously, a candidate path diagnostic could raise after both control and
candidate transitions completed, leaving only the control checkpoint. QUARTZ's
PR10121 already restored the recorder hooks correctly. This follow-through
preserves the result as well; it does not replace that cleanup implementation.

## Behavior

`game` keeps the original exception object and attaches `_titan_executor_row`
when that exception supports metadata. A completed outcome retains its actual
cash, margin and primary `error` field. The secondary `executor_error` records
its stage, exception description and traceback. A game-setup failure has the
requested seed/seat/opponent/arm identity, null scores and a primary error; it is
not counted as a completed game. Missing timing is explicitly null.

The CLI accepts only a result matching the current attempted cell, writes the
existing incomplete checkpoint and stops by re-raising. `failed_rows` keeps its
original meaning: rows with a primary error. A diagnostic failure after a valid
outcome therefore does not invent a policy failure. Inspect `executor_error`
and `checkpoint.complete` as well as `failed_rows`.

Cancellation is not converted into a returned or checkpointed result. Existing
KeyboardInterrupt/SystemExit propagation and recorder unwinding are retained.
An ordinary cleanup error that masks an active cancellation is likewise not
converted into a guessed result. The original context chain remains available.
A failing restoration stops the batch; saving its known cash is not a claim that
the engine hooks are usable. Exceptions refusing metadata still propagate,
without a promised saved row. Disk-write failure stops execution and leaves the
previous checkpoint readable through the unchanged writer; its exception context
retains the original executor error.

Initial CLI source loading before any game, abrupt process termination, external
cancellation and resumable execution are outside this result handoff. No signal
handler, new runner, replay, source exporter or retry path is added.

## Reproduce

From the repository root:

```sh
python -B revenue/kaggriculture/cloud-callable-contract/test_game_failure_checkpoint.py
python -B revenue/kaggriculture/cloud-callable-contract/test_checkpoint_diagnostics.py
```

The new suite imports the entire executor plus the real PathRecorder and timing
observer, uses deterministic one-transition environment/opponent fixtures, and
reads actual temporary-file checkpoints. It is not an official game experiment.
All 22 methods pass. On the exact before-source, 11 pass, two fail assertions and
nine error on the absent result/checkpoint contract. The unchanged six-method
checkpoint-diagnostic suite passes separately. Thirteen applicable checks from
the retained independent lifecycle packet also pass; those are not 13 new tests.

The concrete candidate-path witness completes two synthetic transitions. Before:
one recorded row. After: both rows retained with original cash, incomplete batch,
secondary path error and the same escaping ValueError. No third game starts.

## Source and compatibility

Before-source at main `1e31f2b2bef235bb145980c9ceed49580b1e55fb`:
executor blob `fa50daa1cd84d2ac520c3d2705a6d6d32b4c9d72` (PR10121).
New executor blob `5674a86b1fd4c1a32a9eb745cead167d2dc75155`;
SHA-256 `dae03afb0a04c45c4bd041c793d600e1eb9b8202cd521edad830f29435282cd4`.
Test blob `8770ee0edfc88a756fda81cdded0db31947e619e`;
SHA-256 `4df646c139e68b3d2e88c79eb33982cf2dab362260b88d3920b27d6524f3f9e9`.

Actual recorder `9e32b8f3c1a2d366b7d8d5ed04f6bfb4354c22bf` and observer
`da9ebd2cd4777f1abbb90c4f8718ef61a3257540` remain unchanged. AST comparison also
preserves `load_callable`, `normalise`, `wtl`, `write_checkpoint` and the entire
policy loop. TANDEM's captured source bytes and QUARTZ's ExitStack remain intact.

Consumer: the next ordinary `execute_arm.py` invocation in cloud-model-lab.
Existing frozen archives, live processes, experiment seeds, policies and selected
package are not changed. These local results do not claim hosted CI or gameplay
strength. Coordination: ASTRA-RETAIN, T08 claim `1788842340.059309`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
