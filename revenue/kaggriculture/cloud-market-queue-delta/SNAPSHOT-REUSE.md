# Reuse detached queue snapshots

The existing `compare_queues` executor now reuses each completed slot's detached
snapshot as the next slot's input snapshot. Its final snapshot is the last
completed snapshot, or the initial one when both queues are empty. No input,
report schema, pricing function, market call, deadline checkpoint, scenario
selection or action-selection behavior changes.

Previously each slot deep-copied both parties immediately before and after the
market call, although the preceding after-state was already an independent copy.
The change halves `_view` calls: for one comparison with two arms, two parties and
`n` slots, calls fall from `8 * (n + 1)` to `4 * (n + 1)`. The original paired
market function still runs once per slot per arm. Returned views remain detached
from the live final farm/private state, caller inputs and other scenarios.

## Measured result

Paired warm complete-call measurements, 21 samples per implementation per
workload, two excluded warmups, alternating execution order:

| Scenarios | Initial hands | Slots | Original median | Updated median | Reduction |
|---|---:|---:|---:|---:|---:|
| 1 | 0 | 10 | 2.169 ms | 1.606 ms | 26.0% |
| 8 | 6 | 10 | 24.960 ms | 16.394 ms | 34.3% |
| 32 | 12 | 10 | 134.870 ms | 85.002 ms | 37.0% |

All 63 timed paired reports match exactly after excluding only
`elapsed_seconds`. Imports, engine loading, JSON serialization and full-agent
execution are not included. These are constructed post-unit workloads, not
reached game states or proof that a whole policy meets its action deadline.
The cloud container reported `cpu.max=400000 100000` and a 4 GiB memory limit.
Full samples, p95/max values, environment and source hashes are retained in
[`snapshot-performance.json`](snapshot-performance.json).

A separate instrumented original-source profile attributed 0.502 of 0.672 seconds
to 3,520 `_view` calls across five eight-scenario comparisons (74.7% cumulative).
Profiler overhead is included there; the latency table uses unprofiled calls.

## Changed-path validation

Twelve new methods pass with 273 completed comparisons and 626 independent full
unmodified official-market reference calls. Every completed report also matches
the original executor, excluding only elapsed time. Coverage includes snapshot
counts, detached views, zero/unequal/truncated queues, both positions, multiple
scenario banks, ordered hires/land/stock, floor/custom prices, partial deadlines,
engine failures and unknown inputs. The original source fails the new snapshot
work-count assertion, while preserving its existing economic behavior.

The original `test_queue_delta.py` and `validation.json` are unchanged. Their
24-method result remains bound to the original source; it is not relabeled as
this execution. The new evidence is separate. No full games, game seeds, policy
changes, workflow changes or new engine distribution accompany this patch.

## Reproduce

Use an existing Commons checkout and the existing pinned engine cache. The cache
contains `kaggriculture.py`, `kaggriculture.json` and framework `utils.py` from
`Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.
The source is Apache-2.0; its license remains in the existing engine cache and
`cloud-execution-lab/reference/engine/LICENSE`. Existing artifact `10005621438`
was reused; no download or export is performed by these commands.

```sh
D=revenue/kaggriculture/cloud-market-queue-delta
git show f7629e07b0bfb87a7e7dbf95c0005e89af7da821:"$D/queue_delta.py" \
  > /tmp/queue-original.py
python "$D/test_snapshot_reuse.py" --engine-cache /path/to/existing/engine \
  --baseline-source /tmp/queue-original.py --report /tmp/queue-snapshot-tests.json
python "$D/benchmark_snapshots.py" --engine-cache /path/to/existing/engine \
  --baseline-source /tmp/queue-original.py --repeats 21 \
  --output /tmp/queue-snapshot-benchmark.json
```

The baseline file hash is checked before comparison. Tests can run without
`--baseline-source` for official-market/state-isolation validation alone; that
mode does not claim old/new report comparisons. The benchmark requires the exact
original source. It asserts report parity after every timed pair and retains
all timing samples rather than asserting a machine-dependent speed threshold.

Consumers continue to call `compare_queues` normally. This optimizes its existing
conditional current-market reports; it does not add a funding certificate,
future-price model, new policy, default selection or another prerequisite for
an assembled-agent experiment.

[`snapshot-cli-validation.json`](snapshot-cli-validation.json) records the
benchmark CLI resolving a relative baseline path before matching its
profiler source filename. A separate three-pair-per-workload CLI smoke returned
exit 0 and nine matching reports after this portability correction. The retained
21-pair timing record names its original benchmark hash at commit
`c5f37cc881d3fccf2e8a3d0e16d62febbf3ba9b7`; its measurements are unchanged.
The evaluator and tests are byte-identical across this CLI-only follow-through.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
