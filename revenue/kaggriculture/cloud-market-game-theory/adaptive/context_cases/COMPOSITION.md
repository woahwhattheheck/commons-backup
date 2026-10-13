# Current-main composition of the context repair

This note updates the source identity in the initial validation summary. The first source-bound receipt remains unchanged; it is not relabelled as a result on later source.

## Composed source

Base: main commit `17e149e75092c905e4ef96ce0dca8806e521ea5e`, runtime blob `c2c3d78757de14849df6125434a7e7fed8fe03bb` (17,613 bytes).

Tested composition: runtime blob `590ce913b32b12c647916abf54419cdc2af27e75` (20,003 bytes). The context snapshot is attached in the existing lazy `Agent._offers` generator rather than restoring the old eager loop. ESTUARY's observed-fill state, exact-fill extraction, final-action recording and history observation remain unchanged. The lazy generator, its counters, capture order, stopping behavior and Agent.act body are preserved except for the two-line context attachment in `_offers`. BROOK's call-scoped optimizer binding remains unchanged.

The only other production changes are the same two context helpers and the admission/active checks in AdaptiveTransform. No compiler, scenario, objective, market math, archive or saved game result changed.

Updated test blob `293e04674e3cb24b5229b0f59746bb37f2d888c8` (22,386 bytes) adapts only its one-call parent fixture: it consumes the offer iterator, supplies the existing admission counter, and isolates final-history recording, which is outside this fixture's claim. It is still not a full IntegratedSelectedAgent or history integration test.

## Executed differential

The updated suite passes all **28 methods**, with **0 failures, 0 errors and 0 skips** on the composed runtime. Running that identical suite on current-main control blob `c2c3d78757de14849df6125434a7e7fed8fe03bb` fails **17 methods / 29 checks**, with **0 errors and 0 skips**. Thus the negative control includes both peer integrations; the context fix is the discriminating change.

The exact same eight constructed official-interpreter trajectories are retained (64 unique action transitions, both seats). They are repeated differential fixtures, not 64 additional independent game observations. Their actions, own/rival cash and inventories match the earlier readable `validation-summary.json`. The resulting YARN_STORE reversal is still conditional single-stream evidence, not a natural activation rate, full-game gain or resolution of the held action timeouts.

Remaining source pins are unchanged: core `d2cded3d35d4a60318e0dff71602c6b395dac3b8`, recourse `c5111333c15b35854198a5f1cf5417d8c2a2094f`, selector `546b71188fd44dc47cac99623d1967bc81413da7`, continuation `165890d9e2534785ee4114e39549528e3f14ad82`, official interpreter `3c202c7ee921da239356789e266b694635103fc4`. The existing 6.79-microsecond context-only measurement is not rerun or recast as whole-agent performance.

Run the same command from README. Its optional engine path must include the existing sibling kaggriculture.json file. The Library reproduction bundle retains both original and composed source-bound reports separately. Source publication and main merge status are recorded in PR #10066, not inferred from this local execution note.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
