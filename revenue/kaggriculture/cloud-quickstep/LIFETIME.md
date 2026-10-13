# Scoped market-cache lifetime

This optional runtime component removes self-retaining bound-method cache cycles from the short-lived `selected_sell_core.MarketPath` workspace. It does not change valuation, cache limits, candidate plans, selection keys, market actions, game inputs, garbage-collection settings, or the canonical package. Integration remains with the current package writer.

## Scope and ownership contract

`scoped_method_cache.py` stores an unbound Python method and a weak reference to its owner. A miss temporarily pins the owner while executing the unchanged method. `functools.lru_cache` still supplies the same key handling, maximum size, hits, misses, eviction, exception behavior and explicit clear operation.

This is **not a general drop-in replacement for a bound method**. The workspace must remain strongly owned throughout all calls, including cache hits; arguments and cached results must not reference it; the cached callable must not be retained after dropping the workspace. A miss after release raises `ReferenceError`. A previously cached hit does not consult the weak reference. The intended optimizer has a local `model` throughout scoring, and its numeric cache arguments/results do not hold that workspace. Do not use this helper to change arbitrary persistent-method ownership semantics.

## Exact integration

The supplied `selected_sell_core.lifetime.patch` changes one import and two constructor assignments in the already-selected cached core. In the frozen source closure its builder input is:

```
cloud-execution-lab/reference/titan-current/latest/selected_sell_core.py
```

The unchanged source is 7015 bytes, SHA256 `63198d3b642847a02fee8f3553b9983341b4931b4975013209ad10777b5d1199`. Map the helper into the existing package using:

```python
mapping['scoped_method_cache.py'] = '../cloud-quickstep/scoped_method_cache.py'
```

Keep the existing quote cache and the complete `_single`, `_joint`, `score` and `optimize_lot` implementations unchanged. No global monkeypatch, explicit collection, changed GC threshold, second seller, or private replay input is needed. The provided patch describes source integration, not a modified release archive.

## Validation and evidence boundaries

```sh
python -B revenue/kaggriculture/cloud-quickstep/test_scoped_method_cache.py
python -B revenue/kaggriculture/cloud-quickstep/test_fastpath.py \
  --package /path/to/composed-package
```

Nine new tests check exact cache behavior, independent workspaces, exception propagation, bounded eviction, recursive methods, overrides, owner pinning during a miss, immediate CPython reclamation and unchanged GC settings. The existing 14 optimizer/snapshot checks and seven route/module recovery checks also pass on the composed overlay: **30 checks passed**. Immediate reference-counted reclamation tests explicitly skip non-CPython implementations; no cross-interpreter timing claim is made.

A deterministic GC-disabled lifetime probe on the original core leaves all 20 discarded model objects alive until an explicit collection; all are then released. This is a lifetime test, not a production configuration or throughput measurement.

A separate GC/weak-reference instrumented persistent-worker prefix created 503 models in both arms. The existing core peaked at 41 live models and left 11 awaiting collection; the scoped core peaked at one and left zero. The instrumented baseline's 58.26 ms local call included a measured 53.79 ms generation-two collection; the scoped run had no generation-two collection in that prefix. Instrumentation changes allocation and timing. This explains only that local instrumented spike, **not the original unanswered timeout** that supplied the observations.

Four fresh, uninstrumented runs used the untouched f6 persistent Actor, original lazy native loader, the same complete retained prefix and fixed one-second RPC deadline, in baseline/scoped/scoped/baseline order. All 661 previously recorded actions matched in every run; the newly observed response to the originally unanswered input also matched across arms. Hot-call maxima were 56.70/67.27 ms for the existing core and 22.21/16.08 ms for the scoped core. Summed-call means were 2.6162 and 2.5546 seconds, respectively: an observed 2.35% reduction, with one pairing slower. This small repeated single-prefix sample does not establish a general throughput or tail guarantee.

A separate exact-native-loader check matched the completed route/seller/seed-event state hashes and every recorded action, with zero caller mutations or local fallbacks. These are retained-input checks, **zero new games**, not independent strength samples. The old timeout remains unanswered and unexplained; local responses do not repair or reclassify it. No cold-start, hosted deadline, rank, profit or promotion claim follows. Do not add this percentage to the earlier compact-snapshot/optimizer-redirect or other contributors' overlapping measurements.

The participating owner's private Library handoff retains the complete original failure prefix and wire, source closure, both source overlays, all per-call responses, GC events, test stdout, timing limitations and reproduction scripts. Raw game observations are not included in this public contribution.

## Attribution

Apache-2.0. This only changes ownership of memoized methods around the existing market calculations; all existing runtime, seller, receipt-math and performance contributions retain their attribution. The canonical writer continues to own release integration.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
