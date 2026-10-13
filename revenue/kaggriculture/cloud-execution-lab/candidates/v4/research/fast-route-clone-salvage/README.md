# Current-native fast route clone salvage

Status: **source/evidence only; current default path is cold; no activation or runtime mutation.**

This package harvests one semantic theorem from the retired V3/V3.1 fast-clone lineage without copying its router postimage, `apply_v4.py`, feature plumbing, or branch ancestry. The current authenticated native package still has one route-continuation copy in `integrated_selected.py`: `action = deepcopy(route[step])`. For the exact current authored route-action schema, copying the top `farmer`/`hands`/`market` lists and each hand/market row is behavior-equivalent to `deepcopy`; any unknown or future schema fails closed to real `deepcopy`.

## Exact current source

The checks bind existing Actions artifact `10175943272`: outer ZIP SHA-256 `3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`, package `SOURCE.json` SHA-256 `e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2`, and `integrated_selected.py` Git blob `defa9b84c77fff28ae107bce291b6235bec5d26c`. The offline materializer accepts only that source blob, inserts one helper pair, replaces exactly one copy callsite, compiles the candidate, and refuses source drift. It never edits the runtime in place.

The current route bank contains four routes × 720 callbacks = **2,880 authored route actions**. All 2,880 match the guarded shape. The focused test compares every action to real `deepcopy`, proves top-level and row-level alias separation, mutates cloned children to verify the route template stays unchanged, and exercises future/foreign schema fallback to real `deepcopy`.

## Executed evidence

`test_fast_route_clone.py` passes **5/5 under normal Python and 5/5 under `python -O`**. The helper-only local benchmark clones 5,760 rows per sample; recorded medians are about 121.3→44.5 ms (2.73×) normal and 112.5→40.2 ms (2.80×) optimized. These timings are deliberately scoped as a local clone microbenchmark, not a whole-agent or deadline claim. Raw sample timings are retained in `RECEIPT.json`.

## Critical reachability boundary

`TITAN-CONFIG.json` currently selects `consumer="frozen"`. `titan_runtime.py` reaches `IntegratedSelectedAgent` only under `consumer == "ordered"`. Therefore this exact copy callsite is **not reachable on the current default path**. No production optimization, consumer change, feature key, default change, archive, workflow dispatch, or Kaggle action is justified by this result.

Later native action-copy owners should consume the semantic predicate/clone contract rather than recreate the stale V3.1 router. In particular, active `frozen_selected` or other copy hot paths require their own source-bound composition and action/state/deadline evidence. If `ordered` becomes active later, rerun this exact-source suite plus actual native returned-action/deadline controls before any runtime consumption.

## Reproduce

With the exact extracted `final-pressure-runtime` from artifact `10175943272`:

```sh
python -B test_fast_route_clone.py --runtime /path/to/final-pressure-runtime --receipt normal.json
python -O -B test_fast_route_clone.py --runtime /path/to/final-pressure-runtime --receipt optimized.json
python -B fast_route_clone.py /path/to/final-pressure-runtime/integrated_selected.py /tmp/integrated_selected.fast-clone.py
```

This package is an additive current-line salvage receipt, not a sibling V4 implementation.
