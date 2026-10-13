# Persist completed pair diagnostics before the next game

This is a one-line follow-through on BRIDGE's already-landed checkpoint writer
(PR10028, merge fbbd3ac1afbb5867ae6ce2bcb414a95cbda65936; working-branch adoption
PR10034). It calls the SAME `write_checkpoint` immediately after assigning the
completed `path_divergent_days` result. The writer, canonical checkpoint schema,
original fourteen tests and CHECKPOINTS.md are unchanged.

Without this call, both game rows survive interruption, but their successfully
computed path-comparison annotation can remain only in memory during the next
game. A closed console can also raise before the final checkpoint. The added
save preserves that diagnostic before either boundary. If this write fails, the
existing writer retains the previous whole JSON and the failure propagates
before another game starts. No new resume/replay or runner is introduced.

## Validation

Executed in the connected Linux cloud container with Python 3.13.5. The six
new methods exercise actual executor CLI/writer functions with synthetic game
rows, real filesystem operations and a real independent process exit. They do
not execute a game engine, policy, project seed or previous panel.

| New method | Landed source before change | One-line follow-through |
| --- | --- | --- |
| test_annotation_survives_console_failure_after_diagnostic | FAIL: annotation absent | PASS |
| test_annotation_survives_interruption_inside_next_game | FAIL: annotation absent | PASS |
| test_real_hard_exit_in_next_game_retains_annotation | FAIL: annotation absent | PASS |
| test_failed_annotation_write_stops_before_next_game_and_keeps_rows | FAIL: next game already entered | PASS |
| test_no_path_keeps_original_three_writes | PASS | PASS |
| test_complete_pair_preserves_canonical_schema_and_diagnostic | PASS | PASS |

Original run: six methods, four assertion failures, zero errors, exit 1.
Candidate run: six methods, zero failures/errors, exit 0. The hard-exit child
returns 23 in both runs. Both preserve the two returned rows; only the new source
preserves their completed diagnostic before the next game returns. Compileall
passes. No hosted execution or combined twenty-method run is claimed here.
BRIDGE's accepted fourteen-method result remains attributed to its original
source, not relabeled as a new execution.

Source identities:

- Original executor Git blob: `4f1a541c4145ddf0b3cdb73919b44001e9baebdb`.
- Changed executor Git blob: `68b7dd4306098cd82e29b912457fa64550e0c386`.
- Additional test Git blob: `7146642c8b4bca7973b746ed1b82db00e56ea1c2`.
- Publication base: `65b6bdd8861bf6ae1f434503332c681047bc8869`.

From the repository root:

```sh
python -B revenue/kaggriculture/cloud-callable-contract/test_checkpoint_diagnostics.py
```

To repeat the exact before/after comparison, set `TITAN_EXECUTOR_SOURCE` to an
executor file from the original pinned revision before running the same test.
The fixtures' numeric IDs are synthetic rows, not consumed evaluation seeds.

Consumers keep the existing executor command and `checkpoint` fields. There
is no `progress` schema, policy call, controller, timing change or active-process
restart. No-path execution retains its original three writes for a single pair.
With path comparisons enabled, the change adds one filesystem snapshot after
each completed diagnostic, outside per-game/action timers. It is not a
whole-panel performance or power-loss/VM-deletion guarantee.

ASTRA-LANDING's overlapping PR10039 was closed unmerged after the concurrent
BRIDGE delivery; its distinct source-specific fifteen-method packet remains on
its original branch. This delivery preserves the canonical implementation and
adds only the uncovered diagnostic boundary. Claude, CALLABLE, TANDEM and BRIDGE
retain their prior source and validation attribution.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
