# Terminal action binding on a repeated decision

`transform_terminal` preserves a chosen complete terminal action only while that plan ID and exact action still occur in the current parent-bound receipt set. A changed worker command, non-SELL order, metadata field, removed plan or reused plan ID retires the old commitment and returns the complete caller fallback. Returning the old document afterward does not trigger another draw. Identical retries and first selections are unchanged.

The runtime change is eight additive lines inside the existing method. No solver, objective, production call, scenario family or default policy changes. LARCH authored the existing absolute-score consumer; PRISM supplied this narrow retry correction and boundary regressions. PORT's separate real-engine consumer remains independent.

## Reproduction

From repository root:

```sh
D=revenue/kaggriculture/cloud-score-endgame
python -B "$D/test_terminal_retry.py" --runtime "$D/score_endgame.py" --report /tmp/terminal-retry.json
```

The test extracts and executes the actual production method from the supplied source. Deterministic persisted-choice and precompiled-receipt fixtures isolate action binding; they do not execute PORT's builder, POLY, a controller or the game engine. This is targeted regression coverage of the repaired behavior, not full-pipeline or game-strength validation.

On the exact original runtime, Git blob `d03fc481ea8a90044398fa7ed22b2f7753fca09d`, eight of thirteen tests fail with zero errors. On the corrected runtime, Git blob `543ab5b4536a2b9605ee4c7c69aabfb637811760`, all thirteen pass. Both complete files were materialized and the original Git blob was checked before execution. Exact run records are in `TERMINAL-RETRY-VALIDATION.json`; earlier LARCH source/results are retained unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
