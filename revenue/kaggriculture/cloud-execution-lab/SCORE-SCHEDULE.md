# Reuse the dated town-consumption schedule

SPRUCE-7397, September 7, 2026 (America/Chicago).

The production change is confined to `MarketPath.score` in
`selected_sell_core.py`. It normalizes a tuple rival stream once per score and
reuses dated town absorption across that model's plan/scenario evaluations.
The cache key includes product, horizon, observed shops and both consumption
intervals; changes between calls invalidate the schedule. It caches no prices,
cash, rival quantities, scores, policies or selected plans. The original
rounded/floor-admitting joint sale math, carry value, plan enumeration,
capacity callback sequence and tie objective are unchanged.

This is used directly by the existing optimizer and T15's existing MarketPath
binding. There is no new adapter, planner, controller or runtime entrypoint.
The frozen standalone scheduler and PR9997's previously exported archive remain
unchanged. A consumer using that archive continues using its pinned old source;
repository-layout consumers obtain this change through normal source intake.

## Executed validation

Ten focused methods passed locally in 0.590 seconds, zero errors/failures:
3,888 complete receipt comparisons across all nine products, both terminal/carry
modes, before/paired/after alignment, scalar/dated rival streams, duplicate
orders, low inventory and price-floor regimes; 27 complete optimizer comparisons
including identical capacity-callback order; 36 complete adaptive-tree comparisons
including receipts, groups, choices, causal deltas and metadata. Additional
methods cover input immutability, mutable context invalidation, empty horizons,
invalid intervals and fertilizer's absence of town-center consumption.

The reference score body is retained only in the test, from original core blob
`a743f3b2c1bd4a78cab7b84e5ec9668874116a83`. Actual mechanics and receipt sources
were materialized from the existing source-pack artifact and matched the hashes
in the existing selected-check artifact; neither dependency was reimplemented.
The actual unchanged recourse compiler is blob
`c5111333c15b35854198a5f1cf5417d8c2a2094f`.

```sh
python -B revenue/kaggriculture/cloud-execution-lab/test_score_schedule.py -v
python -B revenue/kaggriculture/cloud-execution-lab/benchmark_score_schedule.py \
  --repeats 16 --output /tmp/score-schedule-benchmark.json
```

## Measured performance

Six constructed exact-model workloads, 16 alternating-order pairs per workload,
fresh model on every sample. Imports and pre-sample garbage collection are
outside timing. All 96 paired outputs compare equal. Complete raw samples,
outliers, environment and source hashes are in `SCORE-SCHEDULE-BENCHMARK.json`.
Python 3.13.5; five visible CPUs; cgroup CPU quota four cores. These are measured
wall-clock times in this cloud container, not the target 1.6-CPU environment.

| Workload | Lot | Original median ms | New median ms | Speedup |
|---|---:|---:|---:|---:|
| Nine-plan / 32-stream table | 2 | 2.910 | 1.727 | 1.685x |
| Nine-plan / 32-stream table | 20 | 3.107 | 2.185 | 1.422x |
| Nine-plan / 32-stream table | 100 | 4.316 | 3.591 | 1.202x |
| Complete optimizer, 16 plans | 2 | 0.748 | 0.554 | 1.351x |
| Complete optimizer, 142 plans | 20 | 7.015 | 5.690 | 1.233x |
| Complete optimizer, 702 plans | 100 | 63.996 | 54.599 | 1.172x |

The optimizer takes 14.7–26.0% less time in these workloads. The table-only path
is a few milliseconds here; it does not by itself explain T15's one-second COK
timeouts. No held attempt is replaced, no new game seed or full-game panel is
used, and this is not a whole-agent deadline repair or strength/promotion claim.

## Whole-actor follow-through

The completed scorer-only consumer comparison is in
[SCORE-SCHEDULE-WHOLE-ACTOR.md](SCORE-SCHEDULE-WHOLE-ACTOR.md) and its adjacent
JSON (PR10114). Eight alternating-order pairs preserve all11,504 recorded
actor actions and selected diagnostics. Five pairs are faster, but aggregate
action time rises48.952s to49.374s and median per-process maximum rises94.94ms
to105.91ms. This does not establish a general whole-actor or tail-latency
improvement. All raw repetitions, exact source/input identities and a runnable
reproduction are retained. The component table above remains unchanged; its
percentages must not be transferred to the complete actor. This comparison
does not include later peer ledger/projection/queue changes.

## Consuming integration

T15/RULE and T08 can consume the same callable from the next repository-source
revision, alongside BROOK's disjoint `adaptive/runtime.py` collector-binding
repair. SPRUCE-7405 retains independent binding validation; FINCH retains the
whole-agent runtime work; ECON-STRESS retains its deadline adapter. This change
needs no new wrapper or source-bank export. The existing next whole-agent run
is the appropriate place to measure their combined runtime effects; the old
held outcomes remain intact and are not fresh held evidence.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
