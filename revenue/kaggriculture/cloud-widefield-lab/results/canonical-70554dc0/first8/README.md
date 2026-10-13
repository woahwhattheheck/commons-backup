# Canonical packaged TITAN: first eight development seeds

Archive SHA256 `70554dc01f8e84336ede169cf109f3d61152e169dce8ad5265b9625216fe52cb`, merge `4f743f8ec29bddc36220b2169a2609fe159776e2`, SOURCE.json `5f6aab68a5c286e574adc80c998733c83680ac41ef92350b19867ffe9be52ef2`. All 47 listed runtime files verified. Official engine and opponent pins are unchanged from source-freeze.json.

80 new games on development 9921001–9921008, five public entries, both seats. Canonical default 78W/0T/2L, mean own 97885.45 and rival 67353.80. Versus reused frozen SELL: +192 own, zero rival delta, no verdict flips. Retained committed-envelope is a separate old arm, also 78W/0T/2L. No controls rerun.

Default consumer=frozen, seed=true, funding=true, terminal_route=false, committed=true (only used by ordered dispatch), budget_seconds=1, reserve_seconds=.01. Package entrypoint main.py calls TitanAgent.act from the relocated archive, with one selected production and transform_selected. Ordered, adaptive and terminal opt-in policies are not enabled. No repository policy imports or network preparation during games.

No external errors/timeouts. Across per-game maxima, candidate external RPC median .0651979s, p95 .1699519s, maximum .2936828s. These are not per-action percentiles. Maximum child-reported agent execution was .2022793s; the initial delivery mislabeled this as RPC and is corrected here. Internal deadline-fallback counts are not exposed by the existing evaluator. Two losing rows are one mirrored Apex seed9921001: own75280/rival78467. Mirrors are dependent and lonespear greedy/SciPy share a lineage; no held or leaderboard claim.

summary.json includes all paired rows, source report hashes and mirror counts. report.json provides compact cash/timing/feature readback. ../first8-raw.tar.gz preserves all new original evaluator JSON, logs and run-state. Reused controls remain in the previously published PR10009 result bundle. Next24 uses the same immutable archive and disjoint continuation seeds9921009–9921032.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../../titanmcp.html). Cite Latch Pad KEEP.
