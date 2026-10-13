# Per-game executor checkpoints

`cloud-model-lab/execute_arm.py` now replaces its existing `--out` JSON after each
returned control or candidate game. No new command, runner, or resume mode is
introduced. The existing `candidate`, `control`, and `rows` fields remain intact,
including source identities, timing, path records, errors, and tracebacks.

An additive `checkpoint` object contains `recorded_rows`, `expected_rows`,
`failed_rows`, and `complete`. `complete=true` means the requested batch and its
pair diagnostics finished; it does **not** mean every game succeeded or any policy
improved. During a run, `complete=false` remains explicit even when the final game
has returned but final output replacement has not completed.

The control is saved before the candidate begins. The candidate is saved before
pair-level path diagnostics. A later interruption or diagnostic exception therefore
leaves already-returned rows available, rather than retaining them only in memory.
Source-fixed existing jobs are not restarted, and old output is not reinterpreted.

## Write behavior

Each snapshot is serialized into a temporary file in the destination directory,
flushed and file-fsynced, then installed with `os.replace`. A serialization, flush,
or replacement failure propagates and leaves the previous destination unchanged;
handled failures remove their temporary file. Abrupt process termination may leave
a temporary file, but readers continue to use the previous complete destination
JSON. This is process-interruption recovery, not a guarantee against host/storage
loss, nor recovery of a game that had not returned or reached its checkpoint.

As before, the caller selects the output path. An existing destination is replaced
when the first new result is saved. If the process fails before any row is returned,
no new snapshot is written and any older output remains an older run. Use distinct
output paths for separate jobs and preserve partial snapshots before a manual rerun.
The implementation does not infer which cells may safely be resumed.

Full JSON snapshots deliberately preserve the existing consumer format. Snapshot
I/O is outside the individual game/action timers. The existing policy invocation,
opponent resolution, normalization, game loop and timing observer are unchanged.

## Executed validation

Base: main publication commit `2d70fa40673bf091f01d182643df7adb6ec01287`, executor
Git blob `224d3995f56dadc6762ebc2f35de6ea06ddee782` (9,072 bytes). The local source
was checked against that exact Git blob before applying the change.

Python 3.13.5 in an isolated cloud container:

```sh
python -B revenue/kaggriculture/cloud-callable-contract/test_execute_arm_checkpoint.py -v
```

**14 methods passed, zero skips** (0.588 seconds in the recorded run). Restoring
the exact original executor produced **5 failures and 8 errors** in those same
14 methods, with one original-format check still passing. The baseline is not
modified or weakened to pass the new tests.

The suite compiles the actual executor's `main`, `wtl`, and checkpoint function
from its source, supplies explicitly synthetic game rows, and exercises real
filesystem writes. It checks control-before-candidate persistence, later-batch
interruptions, preserved failure rows, output order/source identities, failed pair
diagnostics, partial serialization, fsync/replace failures, nested/relative paths,
readable replacement snapshots, and final-write failure. A separate real child
process receives SIGTERM during the synthetic candidate call; the returned control
row remains readable and marked incomplete. These are CLI/filesystem integration
checks, **not official-engine games or policy-strength evidence**.

The full changed source and test file compile. AST comparison with the exact base
confirms `load_callable`, `normalise`, `game`, and `wtl` are unchanged. CALLABLE and
TANDEM's existing implementation and author evidence are preserved, not rerun or
claimed as new results. No new game seeds, transport jobs, workflow changes,
submission, runtime default change, or whole-repository CI result is claimed.

Source SHA-256: `d65a9ba738f2674fe4be343126d40c4debf03a8e5a44019d67135cbbcaacb11e`.
Test SHA-256: `5b0840a9b4f22fc5ba91a064cb721ed19e1ebe996278d90a8e2e4bd0c6c986f4`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
