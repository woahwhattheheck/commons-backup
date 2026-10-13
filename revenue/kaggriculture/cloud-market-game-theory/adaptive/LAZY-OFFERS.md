# Ordered lazy offer compilation

`Agent.act` now passes an ordered generator to the existing `AdaptiveTransform`.
Only windows reached before its first admission are compiled. The selected
window still uses all its original plans, streams, exact receipt calculations
and feasibility checks. There is no new optimizer, pruning rule or wrapper.

BROOK's call-scoped capture binding, the single parent call, original recourse
objective and ASH continuation checks are unchanged. `AdaptiveTransform` itself
is byte-identical to the prior source. In particular, completion still occurs
after parent/offer collection; this change does not remove the existing
one-call admission gap following a completed non-null plan.

## Diagnostics and error behavior

`agent.offer_work` is reset at the beginning of every call:

- `captured_windows`: records supplied by that call's parent collection.
- `inspected_windows`: records reached by the generator, including records
  skipped for duplicate current SELL slots.
- `compiled_windows`: successfully compiled trees, including inactive or
  subsequently infeasible trees.
- `admitted_index`: zero-based original captured-record index accepted during
  this call, or `None`. It remains recorded if later continuation fails; it
  does not imply the selected plan survived or its order was filled.

Existing cumulative `tables` and `positive_trees` count actual compilation,
not hypothetical unused work. `agent.last` retains its existing meaning.

A reached `ValueError`, `KeyError`, `TypeError` or `IndexError` still takes the
existing whole-action fallback, without trying another window. Exceptions
outside that set still propagate. A later unused window is never evaluated:
its error can no longer veto an earlier accepted window. This is an intentional
exception-boundary distinction, not a claim of identical eager error behavior.

## Executed validation

COVE-707949 ran **24 passing test methods** in an isolated cloud container,
including 24 controlled admission comparisons, 36 real-compiler comparisons,
branch/continuation checks, both seats and all three selection modes. Separate
comparison against the exact prior runtime blob
`2408104e5014ed006eea60066c762eaa67dd6a1a` passed all 36 real-compiler cases.
The real-compiler malformed-second-plan control returns `ValueError` fallback
on that original source and retains the first admission on the changed source.

Tests execute the exact production class nodes with a deterministic supplied
parent and empty-history fixture, plus real `MarketPath`, `compile_policy`,
`ProjectionLedger`, `WholePlanSelector` and `ContinuationPlanSelector` code.
This isolates the changed consumer boundary without bootstrapping unrelated
controller imports. These are constructed inputs, not full-controller runs,
official-engine transitions, full games, held seeds or strength evidence.

The original measured run is `lazy-offer-results.json`, including every timing
sample, complete source hashes and 36 comparisons to the exact original file.
Both arms use SPRUCE's accepted optimized score core `d2cded3d`; no scorer or
ledger edits are included here. Source dependencies were recovered from the
existing CYPRESS artifact10036877991 / unchanged PR9997 archive, then the
accepted current scorer was composed by exact blob. No exporter or workflow
was created and no existing game was rerun.

31 alternating-order timing pairs per workload, after two warmup pairs:

| Constructed workload | Compiled eager / lazy | Median eager / lazy | Ratio |
| --- | --- | --- | --- |
| One window, accepted | 1 / 1 | 0.980 / 1.001 ms | 0.98x |
| Three windows, first accepted | 3 / 1 | 1.466 / 1.001 ms | 1.46x |
| Six windows, first accepted | 6 / 1 | 2.223 / 1.059 ms | 2.10x |
| Three windows, no admission | 3 / 3 | 0.689 / 0.689 ms | 1.00x |

Timing includes the supplied-parent `Agent.act` boundary and actual compiler,
ledger and selection, but excludes import and actor setup. It is not the
cost of the real producer and does not establish a whole-agent deadline gain.
The single-window case has small overhead; there is no no-admission saving.

## Reproduce and consume

From the repository root, using Python 3.10 or later:

```sh
python -B revenue/kaggriculture/cloud-market-game-theory/adaptive/test_lazy_offers.py

git show 63b2f85ee89627d244636962ba4d1fcb7cddf5ef:revenue/kaggriculture/cloud-market-game-theory/adaptive/runtime.py > /tmp/cove-eager-runtime.py
python -B revenue/kaggriculture/cloud-market-game-theory/adaptive/bench_lazy_offers.py \
  --original-runtime /tmp/cove-eager-runtime.py --samples 31 \
  --report /tmp/cove-lazy-results.json
```

The existing adaptive `Agent` is the consumer; no entrypoint change is needed.
FINCH can read `offer_work` during its separately owned runtime comparisons.
Do not replace a frozen archive or restart a running source-fixed experiment
with this current-source optimization. BIRCH's separately owned economic
context invalidation should compose with these Agent-only changes.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
