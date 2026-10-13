# TITAN V4 — represented-market executability

Status: **CURRENT V4 SOURCE CARRIER / PHYSICAL TRANSITION MERGED / INTEGRAL-MONEY CUSTODY FOLLOW-UP HELD FOR EXACT GATE**

Canonical workspace: `revenue/kaggriculture/cloud-execution-lab/candidates/v4` on `main`.

This directory is the **single** V4 authority for `SellScheduler.receipt_profile()` represented-market physical executability. It must not be split into a sibling controller, alternate V4 root, or stale whole-file scheduler fork.

## Canonical composition chain

The source-only chain is intentionally narrow:

1. raw current scheduler `scheduler.py` Git blob
   `a483b24dd72b580d7d8811636b54d2d44f391575`;
2. canonical scheduler-prefix materializer Git blob
   `f36e9120ea07c861a7eca5821a5306c6dbfa4613`;
3. merged represented physical-transition materializer Git blob
   `647fcccb4f07adbb308e93f99aa0bc8c4a9ffd1f`;
4. integral-money custody compositor in this directory.

The pinned official engine is
`reference/engine/kaggriculture.py@3c202c7ee921da239356789e266b694635103fc4`.

The chain composes transformations from exact captured bytes. It does **not** overwrite the production scheduler, change runtime/default/config state, or move COMPOSITION/INTEGRATION pointers by itself.

## Merged physical-transition theorem

The predecessor current-root defect replayed authored market intent as if every represented purchase or HIRE physically executed. That could manufacture shed goods or an actor that the official interpreter would reject.

`materialize_represented_physical_transition.py` closes that seam after the canonical raw-prefix materializer:

- `BUY_PRODUCT` is admitted only for official WHEAT/FERTILIZER rows with source-provable cash, quote, and real shed capacity;
- fixed-price `BUY_ANIMAL` is applied sequentially until cash/capacity proves a stop;
- HIRE uses native Fibonacci `_hire_cost` and mutates cash, `hires_today`, hand cardinality, and private inventory atomically only on success;
- unproved SELL credit never becomes later funding authority;
- prior unmodeled BUY_SEED/BUY_LAND spending destroys exact funding proof rather than funding later represented effects;
- later lockstep product quotes fail closed once rival/shared-market state is no longer source-bound;
- malformed/coerced quantities and receipt-critical config values fail closed;
- inactive raw suffix rows and indexes remain owned by the scheduler-prefix carrier and are never compacted here.

The physical carrier consumed the V3 donor semantics from #12056 / #12110 / #12055 without copying any stale V3 whole-file scheduler postimage.

## Integral-money custody successor

The merged physical helper intentionally accepts `int` and `float` money because the official engine stores canonical farm money as a float. The pinned engine, however, constructs it from an integer:

```python
starting_money = int(...)
farm["money"] = float(starting_money)
```

The represented market/HIRE costs used by this seam are integer-valued. Canonical float balances therefore remain integer-valued (`0.0`, `1.0`, `25.0`, `300.0`, ...).

The old guard accepted any finite nonnegative float. A malformed prestate such as `money=1.5` could therefore prove a cost-1 represented HIRE and leave `0.5`, even though that fractional state is outside the pinned engine domain.

`materialize_integral_money_custody.py` is the **same-package successor compositor**. It authenticates the exact merged physical materializer before execution, requires the two expected permissive money-guard preimages, then replaces only those guards so:

- exact integer money stays valid;
- finite nonnegative integer-valued floats stay valid;
- fractional floats fail closed before any represented BUY_PRODUCT / BUY_ANIMAL / HIRE transition.

It does not alter SELL-credit lower bounds, price semantics, capacity semantics, HIRE cost semantics, raw-prefix ownership, queue order, or suffix/index custody.

## Exact gate

The dedicated existing workflow `.github/workflows/titan-v4-represented-physical-transition.yml` is the hosted authority for this package. The current successor gate must execute:

- `test_represented_physical_transition.py`;
- `test_receipt_config_guard.py`;
- `test_repository_materialization.py`;
- `test_integral_money_custody.py`.

Required result is **30/30 normal + 30/30 under `python -O`, zero skips**, followed by `py_compile` for both materializers and all four test modules.

The nine integral-money contracts bind the upstream materializer, bind the official engine source, kill fractional HIRE/GOOSE/WHEAT predecessors (`1.5`, `300.5`, `25.5`), preserve canonical integer-valued float positives (`1.0`, `300.0`, `25.0`), and compile an exact repository composition.

Queued or pending Actions runs are not green evidence. A repo-mounted receipt must bind the exact head and relevant blobs before and after execution.

## Adoption boundary

This directory remains source/test evidence until the then-current one-tree gameplay admission owner consumes the composed candidate. In particular, this package does **not** by itself:

- flip a feature/default;
- edit runtime scheduler bytes;
- edit configuration;
- move COMPOSITION or INTEGRATION authority;
- create an archive/provider/submission artifact;
- authorize Kaggle/provider action;
- claim a complete two-player hidden-state model beyond the source-proved represented seam.

Future repairs to this theorem must extend this same package and composition chain instead of opening another represented-market carrier.
