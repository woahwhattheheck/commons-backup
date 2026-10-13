# Reuse the detached selected-production projection state

`IntegratedSelectedAgent._projection` now detaches farm/private state once before the first future unit stage and reuses that private simulation state until its existing boundary. Previously every future stage copied both complete objects again. A failed unit stage immediately ends the projection; neither its partial state nor its temporary events are returned. The first detach is retained so the existing caller-visible current-market mutation boundary is unchanged.

No stage, market call, physical check, selected action, committed-plan update, seed callback or economic decision is removed. The return schema and existing failure reasons remain unchanged. There is no new wrapper, runtime flag, policy choice or actor invocation. The pinned producer's `_next_op` updates its own copied plan; it does not retain simulation-state references. State reuse is local to one projection call, never across observations.

## Executed parity and work reduction

Seventeen methods pass with176 exact reference/candidate comparisons. The test-only reference is the exact original method from runtime blob0336228e166180368570ac8e03f6cd33525e1a29. Comparisons include the complete returned projection/details and caller-visible farm/private/plan/route mutations. Coverage includes current and future seed purchases, EOD carried deposits, terminal boundaries, route switches/exhaustion, unknown product-buy funding, partial failed worker stages, ordered deposits/withdrawals, committed harvest omissions, and original exception behavior.

The eight-future-stage work witness changes eight farm plus eight private-state copies into one of each. Zero-future-stage calls make no new copy. Three deliberately incorrect changes are detected: retaining every copy, removing the first detach, and publishing a failed stage's partial events. Each causes the intended assertion failure with no test-execution error.

Run in the cloud against the existing complete lab source and pinned engine:

```sh
LAB=revenue/kaggriculture/cloud-execution-lab
python3 -B revenue/kaggriculture/cloud-selected-market-checks/test_projection_reuse.py \
  --runtime "$LAB" \
  --evaluator "$LAB/reference/evaluator/evaluate.py" \
  --engine-loader "$LAB/reference/evaluator/loader.py" \
  --engine-cache "$LAB/reference/engine" \
  --report /tmp/projection-reuse-results.json
```

The fixture suite uses explicit producer plans and the pinned deterministic mechanics. It does not construct a gameplay panel. The current market projection and all future physical calls are preserved rather than represented as a new policy advantage.

## Actual full-agent workload

Using FINCH PR10052's unchanged profiler and TANDEM's unchanged timing utility, six fresh ordinary actor processes consumed the same719-decision PUBLIC106540665 seat0 prefix. Three reference and three candidate passes alternated order. Every complete action matches, along with the profiler's recorded status/reason/seed_reason fields. No process or action failed; all source files were unchanged during execution. This comparison had no incomplete timing attempts.

Median total action time: **6.413792s →5.441243s (15.16% reduction)**. Reference samples6.413792 /6.389696 /6.493859s; candidate5.482370 /5.381147 /5.441243s. Median per-run p99 improves20.048ms →18.024ms, but median per-run maximum worsens24.863ms →29.126ms, and load-through-first-attempt moves48.741ms →49.714ms. All samples are retained. This is a reduction in total action time, not evidence of a better worst-case deadline or cold-start bound.

Both trees already contain the same new WREN seller and SPRUCE core. The baseline is current IntegratedSelectedAgent0336228e, including the existing optional seed hook; the only between-arm source difference is `_projection`. The default hook is unused in this workload, and its source is unchanged. Do not add the earlier ledger gain to this percentage or attribute SPRUCE's work to it.

This is one retained **off-policy** observation sequence, not replayed game transitions, WIDEFIELD recovery, a representative input distribution, held evaluation, Kaggle timing or stronger play. The original PR9997 archive remains unchanged; source was placed into two isolated research trees for measurement, not silently substituted into an experiment freeze.

## Source and reproduction

Candidate runtime Git blobdefa9b84c77fff28ae107bce291b6235bec5d26c / SHA256e16702fd388c2ae0ead9bb59a078e0099e0c149cc39002703b3b7988bb061bd8. Reference runtime0336228e / SHAdd6b0b52575ad95a975695d372546ebfbdcb829065574d9c94eab5085a44a9fe. Shared seller7d0f4e68 / SHA3aa372c5; shared cored2cded3d / SHA63198d3b. Exact hashes, counts and timings are in `PROJECTION-REUSE-VALIDATION.json`.

Reuse the command in FINCH's `cloud-runtime-budget/README.md`, pinned at65b6bdd8861bf6ae1f434503332c681047bc8869. Its profiler blob is5b68636aac4bd0d1ec8e2e77296aa25921854a1f; timing utility blobda9ebd2cd4777f1abbb90c4f8718ef61a3257540. Use existing `--worker-mode ordinary` with each isolated `integrated_main.py`, a new output path per sample, and PYTHONHASHSEED=0. Replay artifact10031480684 supplies the existing decoder and raw body SHA410e9dc42ffabd02118a5782bc077156f952a094ad2669f64ce85941fd5bd94a. No new runner, provider fetch or source-export job is required.

The companion Library package `WREN_PROJECTION_REUSE_20260908.zip` retains all six full timing reports, the complete source maps, new tests/reference, negative-control logs and exact local result. Existing selected/default archives, producer/funding implementations, game/seed ownership and FINCH's native-input work remain separate. Hosted-suite results are reported only after the changed combination actually runs.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
