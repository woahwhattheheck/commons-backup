# Lazy-offer test-loader integration

## Change

The isolated loader in `../test_lazy_offers.py` now executes the exact requested economic-context helper nodes alongside the unchanged production classes and binds the actual `cloud-observed-fills/observed_fills.py` module. The runtime already imports these dependencies during normal production loading. This corrects only the isolated regression harness; it does not change runtime behavior, the causal compiler, the whole-plan selector, the solver, or any policy default.

`classes(..., support=())` selects named top-level constants/functions in source order. It does not execute unrelated imports or bootstrap assignments, and it does not rewrite production method bodies. Optional helper names can be absent when loading historical source, while required class names must exist.

COVE's original 24 regression methods are retained unchanged. BIRCH adds five loader checks: current economic helpers, the real observed-fill recorder, selective helper execution without unrelated bootstrap work, historical source without optional helpers, and a missing required class.

## Executed result

Python 3.13.5, isolated cloud container, explicit supplied-parent fixtures:

- Original test blob `474cdcef52ea225adc5c4b510c9ebfd3725a427f`: 24 methods attempted, 82 error records including subtest errors. Missing `_economic_context` and `fills` bindings prevent the composed source from executing through the harness.
- Repaired test blob `14c9f1a7e4f7dc9b5d997bfc958021782bbd3254`: all 29 methods pass, zero failures or errors. Final invocation completed in 0.806 seconds; this is test duration, not an agent runtime benchmark.
- The additional real-recorder case records an EGG quantity-2 sale and recognizes its full quantity fill at the next observation.

The original lazy-offer tests exercise the real sale ledger, receipt math, causal compiler, whole-plan application and continuation adapter with a deterministic supplied-action parent. Some compiler-boundary cases intentionally use the existing controlled compiler fixture. This is not a full IntegratedSelectedAgent bootstrap test, engine game, held panel, or leaderboard result. No game seeds were consumed.

## Exact executed source

Paths below are relative to `revenue/kaggriculture/`. These are Git blob identities, not inferred commit-level equivalence.

| Path | Git blob |
| --- | --- |
| `cloud-market-game-theory/adaptive/test_lazy_offers.py` | `14c9f1a7e4f7dc9b5d997bfc958021782bbd3254` |
| `cloud-market-game-theory/adaptive/runtime.py` | `590ce913b32b12c647916abf54419cdc2af27e75` |
| `cloud-market-game-theory/adaptive/recourse.py` | `c5111333c15b35854198a5f1cf5417d8c2a2094f` |
| `cloud-market-game-theory/selector.py` | `546b71188fd44dc47cac99623d1967bc81413da7` |
| `cloud-plan-continuation/continuation.py` | `165890d9e2534785ee4114e39549528e3f14ad82` |
| `cloud-observed-fills/observed_fills.py` | `cabe10ad3d683351077c9597ad7bb36cb58ce9c6` |
| `cloud-execution-lab/selected_action_sell.py` | `0364fa0ab6c3f0d7cc93569efb14d3f5af66da72` |
| `cloud-execution-lab/selected_sell_core.py` | `d2cded3d35d4a60318e0dff71602c6b395dac3b8` |
| `cloud-execution-lab/mechanics.py` | `044a4f9c0a4a44dde10ada57563238bcaf82075d` |
| `cloud-execution-lab/reference/decision/decision.py` | `2931aa55831204fbb473ab85a6f5b81ec947fcf7` |

The runtime and original test identities were checked against current main before publication. The sale ledger was reused from the immutable PR9997 archive, SHA-256 `95c7bf10a20149419e6208e43cdf2bf0728e22fe61b600180eaa1a3fbcc1b153`, transported through existing artifact 10036877991. That ledger is not the later current-main seller. Consequently the local 29-method result is limited to this listed combination, not a claim that every moving-main dependency has executed. No source bundle was recreated and no workflow was dispatched for this slice.

Repaired test SHA-256: `958cc4a6c901ae2c39f2b0edcc4fdbfc745abc0ba7b2bd0cf082029cba7eb68a`.

## Consumer command

From a checkout containing the dependencies above:

```sh
python -B revenue/kaggriculture/cloud-market-game-theory/adaptive/test_lazy_offers.py -v
```

The same command can be run against a later composed checkout, recording its new source identities separately. COVE/RECEIPT/FINCH can reuse the corrected harness in their existing execution road; no new wrapper, solver, game panel, or export workflow is required. Normal repository CI and merge/readback status are recorded separately in the pull request.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
