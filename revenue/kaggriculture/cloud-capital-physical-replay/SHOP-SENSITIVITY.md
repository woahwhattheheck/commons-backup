# Complete-controller future-buyer sensitivity

A controlled continuation experiment using the unchanged physical replay consumer
from PR10055. This is a reproducible economic discriminator, not a new route
selector, a full game, or the missing HAZEL step226 observation bank.

## Result

All four conditional continuations complete through the final executable
step718. Each future starts from exactly the same projected own observation and
controller state at226. Cash below is terminal **own cash**, not a win/loss or
paired-rival margin.

| Declared future shop stream | MAIN continuation | YARN continuation | YARN minus MAIN |
|---|---:|---:|---:|
| Remaining draws all BRUNCH_SPOT | 132,505 | 121,602 | -10,903 |
| YARN_STORE at public288; other draws BRUNCH_SPOT | 141,093 | 149,667 | +8,574 |

Within each offered route, the complete emitted action sequence is identical
across the two futures. Its cash and market rows are also identical through287,
before the changed shop becomes public. No discarded stock occurs in any case.
The dated buyer changes economic value without changing the selected plan's
physical actions. MAIN retains its original later milk-exit controller decision
in both futures; that behavior was not suppressed or replaced by a static tape.

The route preference reverses across these two hypotheses. A current quote is
therefore not a substitute for dated receipts in this case. This does not supply
a probability for either future, prove which route to choose at226, or establish
a result against an interactive opponent. Neither declared future is represented
as known at the226 decision. Both columns and their negative outcome are retained.

## Construction and limits

Start from the exact original T10 decision121 own observation used in
[the existing consumer validation](README.md). Project the original MAIN
controller through225 using the unchanged T04 oracle, with explicitly declared
BRUNCH draws after143 and215. This produces a **conditional projected** state
at226, not a recovered actual-game snapshot. The source controller is then
independently copied for each route/future pair.

After287,359,431,503,575, the first future adds BRUNCH_SPOT. The second changes
only the first of those additions to YARN_STORE. These are end-of-day action
dates; the first differing public observation is288. The existing initial shop,
two declared prefix additions and five future additions total eight shop
instances. No additional shop is inserted after the cap is reached.

Both conditional scenarios posit no rival supply and no new weeds. T04 uses
external inventory changes before the own market, not simultaneous rival
lockstep trades, and freezes rival public farms. Rival cash utility remains
unavailable. This experiment does not reproduce HAZEL's positive9921001 or
negative9956003/4 regimes. Their existing source/snapshot recovery stays separate.
No environment seed is initialized, held sample used, or policy default changed.

Execution count: one105-decision common prefix and four493-decision
continuations, totaling2,077 owned-state steps. The four continuations took
1.293378477 seconds in the recorded invocation; that is not a whole-agent runtime
bound. The original two-route/15-test PR10055 validation remains unchanged.

## Reproduce and inspect

Use the same real dependency paths as the original consumer. The driver verifies
the exact Arlene and T04 source identities; the existing evaluator verifies the
three official engine files. It requires the documented T10 fixture shape and
records its exact byte identity.

```sh
python shop_sensitivity.py --source-root "$TITAN_SOURCE_ROOT" \
  --oracle "$T04_ORACLE" --engine-root "$TITAN_ENGINE_DIR" \
  --observation "$T10_OBSERVATION" --output shop-sensitivity.json
```

[SHOP-SENSITIVITY.json](SHOP-SENSITIVITY.json) binds the executed driver, original
runtime/dependency pins, complete raw report and retained action/prefix checks.
`shop-sensitivity.json` contains all four full action/state/queue reports and the
conditional observation at226. The exact3,471,361-byte report is saved in
`titan-capital-buyer-sensitivity-evidence.zip` in the owner's Library, alongside
the driver, original consumer/helper, observation fixture, checks and licenses.
The original `titan-capital-physical-replay-evidence.zip` is retained separately.
Reproduction can differ in timing but should preserve the cash/action results.

No new simulator, selector, route boundary, scenario calibration, export workflow,
Kaggle upload, spending or owner-device execution is introduced by this addendum.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
