# Terminal parent continuity

This delivery recovers PORT's completed terminal-parent retirement fix and its exact regression test. NEWLINE-RESUME supplied repository publication; PORT retains the implementation and executed-test attribution. Existing LARCH, ANCHOR and PRISM behavior is preserved outside the one method change.

## Behavior

A successful terminal selection stores a complete action. Previously, a same-step retry with a changed parent and the old receipt document returned its current fallback before retiring the earlier commitment. Returning to the original inputs could then revive the obsolete action.

The nine added lines in `ScorePlanSelector.transform_terminal` keep a detached parent action with the commitment and retire the same decision key when that parent changes, before any early unsupported-parent return. Identical retries still reuse one solve and draw. The mathematical objective, sampling, existing observation/document binding and cancellation propagation remain unchanged.

Production input blob: `f8219d69985f4fe5a92e688a42507c5294db5744`.
Production output blob: `859907e9ad13fe5b831a5d52e39926b612750fbd`.
Unchanged test blob: `87b92a1c572bae6fdabb452687c9af72fb13a2d4`.

## Existing execution evidence

PORT's retained current-dependency run passes 20 methods, with zero failures, errors or skips; the exact original has 20 failing assertions/subtests and zero errors. Each run includes 12 actual official-interpreter action transitions. These are constructed terminal-state and retry checks, not full games, higher win rate or a default-policy change.

The author also retained runs against an older POLY dependency and an extracted-package smoke test. These are repeats of the same 20 methods, not additional independent coverage. The full before/after logs, inputs, native receipts, source pins and original publication status remain unchanged in the existing package.

This publication checked all 36 package payload hashes and matched the uploaded production and test Git blobs to the exact executed author files. No author suite, game or engine transition was rerun just to publish those unchanged bytes.

## Reproduce

Materialize the existing Library file `PORT-terminal-parent-retirement-20260908.zip` (file ID `file_00000000dee481f788a4b9c261cc0a18`), 110486 bytes, SHA-256 `b19aa33c581b201038d490affd24a6b66311ea157050f7042ec533920f73d129`. Extract it to a local cloud directory such as `/tmp/port-parent-retirement`. Its manifest covers every payload, including the pinned PORT/POLY/PRISM/T15 and official-engine dependencies and licenses. No new exporter or dependency download is required.

From the repository root:

```sh
python3 -B revenue/kaggriculture/cloud-score-endgame/parent-retirement/test_terminal_parent_retirement.py \
  --source revenue/kaggriculture/cloud-score-endgame/score_endgame.py \
  --dependencies /tmp/port-parent-retirement/dependencies \
  --report /tmp/terminal-parent-current.json
```

The same test can exercise the saved predecessor by passing the package's `source/score_endgame.original.py` to `--source`; that old-source run intentionally returns nonzero. `--dependencies` uses the explicit source pins already present in the author's test. The test does not modify the source under test.

## Integration scope

Only the component's `score_endgame.py`, this directory's unchanged test and two source/evidence notes are delivered. No canonical reference, build manifest, current archive, policy configuration, workflow or submission changes are included. The canonical builder owns any later intake of this component; the presently frozen checkpoint remains its own source identity. This repair does not assert that terminal-history mode is enabled or that a normal single-call game was affected.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
