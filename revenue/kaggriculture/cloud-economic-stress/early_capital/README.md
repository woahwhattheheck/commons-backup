# Early-capital retained-trace audit

This lane tests whether earlier or additional land actually repays its cash cost
before the episode ends. It replays retained authored action tapes through the
pinned official engine, changes only `BUY_LAND` timing, and verifies every
baseline terminal score against the retained game sidecar.

The 64 analyzed traces cover 16 seeds, both seats, and two opponent source
families. Moving the existing second land purchase about 15 turns earlier is
terminal-neutral throughout. An additional third land at step 266 is positive in
25/64 traces but loses $3,053.953125 on average, with outcomes from -$24,196 to
+$19,589. A hindsight choice among tested route-entry timings is positive in
36/64, demonstrating a real opportunity but not an implementable decision rule.

These are deliberate engine-valid fixed-action counterfactual fixtures, not
naturally generated games: later actions remain the retained baseline actions.
They establish that a static cash threshold or route identity is unsafe. Runtime
promotion requires an observable prospective certificate covering ordered-queue
affordability, needed inputs, finite worker turns, and receipts before the
remaining horizon.

`analyze_early_plant.py` also tests the most concrete existing-land opportunity:
move a later same-tile WHEAT plant/water pair into two earlier literal PASS
turns. All 64 reached predicates hold and terminal seed state is preserved, but
the terminal cash delta is positive in 23, zero in 20, and negative in 21
(mean -$1,138; range -$17,524 to +$23,957). The two-turn transform is therefore
sent to the complete-route owner as a dated-sale/capacity input and rejected as
a standalone stage.

Run `summarize.py` from the repository root to recheck all baseline identities
in the compressed raw result files and regenerate `summary.json`. No Kaggle
upload or hosted-strength claim is made.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
