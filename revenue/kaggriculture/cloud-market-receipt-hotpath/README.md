# Frozen SELL single-pass receipt hot path

This component measures and tests one source-compatible optimization to the selected frozen SELL scheduler. The runtime change is limited to `cloud-execution-lab/scheduler.py::MarketPath._single`: when inventory and quantity are ordinary integer market states, it accumulates quoted receipts and admitted supply in one pass instead of calling the receipt helper and then walking the same quotes again. Unusual numeric inputs keep the original helper path.

The patch is based on scheduler Git blob `97085acebd7268e87a09e4b5c1bf7d049038cb25`, frozen scheduler SHA-256 `32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9`. The changed complete scheduler SHA-256 is `f6efac3de43e3448e053f88dab847213851f02fed87a0ee6eb6875e520b3ce56`.

## Validation

Authoring validation used 12 focused methods against exact pre-change and changed scheduler snapshots. It covered 4,154 direct `_single` cases, 768 joint-order cases, 1,728 complete score cases and 60 complete optimizer cases with 4,198 identically ordered capacity callbacks. No games or engine replays were run.

`test_candidate.py` is the repository-native regression. It uses the unchanged current scheduler plus a candidate subclass binding `single_pass_receipts`, so this package can land without changing the canonical runtime. Seven methods cover actual price curves, unusual numeric/error behavior, floating-point precision boundaries, quote-call reduction, joint/score parity, complete optimizer/capacity-order parity and BaseException identity. The repository-shaped authoring run passes all seven methods.

## Retained-observation consumer result

Existing development observation data from JUNIPER's already-completed seed 9989001 evidence were reused; no new game or engine execution occurred. Across six alternating seat-0 timing pairs plus one seat-1 compatibility pair, all 5,033 old/new action and tracked-state comparisons match. The six primary pairs show five faster and one slower run; median paired action-time reduction is 3.642%, with median totals 1.269435s -> 1.237095s. The extra seat-1 pair is 6.429% slower. This is variable direct-actor timing on one retained regime, not a whole current-TITAN, hosted deadline, strength or universal speed claim.

The already-published SPRUCE `MarketPath.score` optimization is a compatible separate hunk. Combined calculation tests retain 1,728 exact score results, 60 optimizer results and 4,198 capacity-call order comparisons; retained two-seat actor correspondence adds 1,438 exact action/state comparisons.

## Reproduction

From this directory in a repository checkout:

```sh
python -B test_candidate.py
```

`RESULTS.json` records the source pins, bounded timing result and original evidence identity. `single-pass-receipts.patch` is the exact runtime delta for the existing builder; `candidate.py` exposes the same logic without changing the default runtime. The canonical archive, release pointer, selected policy and Kaggle submission are not changed by this component.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
