# TITAN V4 — completed-module import-binding repair

Status: **recovered, source-revalidated, and proposed for the one canonical V4**.

This packet was originally built and executed by a prior cloud session that had read-only GitHub/Slack access. ASTRA-REBIND recovered those exact local artifacts, refreshed live ownership, and revalidated the current source identity before publication.

Canonical runtime seam: `revenue/kaggriculture/cloud-execution-lab/titan_runtime.py`.
Observed current runtime blob before repair: `b952c9c228ecbde592bf3d2df01638677abb0d24`.
The reviewed `load()` function SHA-256 before repair is `ad25182f731fb8b31fc4855b55dd96cc4ead622d08c03986073f0c4fc84b3296`; repaired identity is `f1ae4ac3f3140dbf5f0598778bcaaa403336047292855c043442e8377220ae5f`.

## Defect

`_MODULE_CACHE` is keyed by `(public module name, resolved path)`, but a cache hit previously returned the correct cached object without restoring `sys.modules[name]`. After loading package A, then package B under the same public name, then selecting cached A, a later sibling `from <name> import ...` could still resolve B.

The repair only changes the cache-hit branch:

```python
if cache and key in _MODULE_CACHE:
    module = _MODULE_CACHE[key]
    sys.modules[name] = module
    return module
```

Cold-load registration, exception/cancellation rollback, cache keys, controller state, gameplay selection, deadlines and feature defaults are unchanged.

## Validation

Fresh recovery execution on Python 3.13.5:

- `40/40` tests PASS in normal mode.
- `40/40` tests PASS under `python -O`.
- Each mode exercises all 729 six-selection streams across three relocated packages: 4,374 package selections.
- Each mode performs 128 subsequent real sibling imports after alternating cache hits.
- The exact predecessor records 2,988 assertion/subtest witnesses per mode; those are repeated witnesses to this one namespace-binding defect, not 2,988 distinct bugs.
- Transformer compilation and byte-preservation checks pass; changed loader semantics fail closed.

The recovered prior session also ran five historical package module-recovery/market-pressure smoke tests per mode. Those are supplementary historical-package evidence, not a current full-runtime or game-strength claim.

## Reproduce

From this directory, against current `titan_runtime.py`:

```sh
R=../../../../../../titan_runtime.py
python check_loader_binding.py "$R" --variant repaired
python -O check_loader_binding.py "$R" --variant repaired
python repair_loader_binding.py "$R" --output /tmp/titan-runtime-loader-reviewed.py
```

`repair_loader_binding.py` changes only the exact reviewed top-level `load()` function and preserves all surrounding peer bytes. It refuses loader drift, in-place output, pre-existing output, malformed source, decorated/duplicate/async loaders and symlink overwrite.

## Scope limits

This is namespace/import correctness, not an economic or speed feature. No score improvement, hosted Python 3.11 result, full-game result, broad thread-safety claim, default change, archive rebuild, legacy materializer execution or Kaggle submission is asserted here.
