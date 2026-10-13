# Shared opponent invocation

`cloud-model-lab/arlene_arm.py::make_opponent` now selects the supported positional call shape with `inspect.signature(...).bind(...)` before executing an opponent. The existing one-argument Arlene special case, opponent registry, module loading, source metadata, game loops and result aggregation are unchanged.

The previous wrapper caught every `TypeError` from `fn(obs, cfg)` and called `fn(obs)` next. An optional-configuration or variadic stateful opponent could therefore execute twice; a required-two-argument opponent could have its original body error replaced by an argument error. The repair forwards the chosen call exactly once and propagates the original exception. A callable accepting neither supported shape fails at construction without executing its body. This is the same invocation method used by CALLABLE's separate candidate-loader repair in PR9998; that implementation and authorship remain intact.

## Exact source and executed validation

Python 3.13.5 in the connected cloud container. Main original Git blob: `28affd86d27c8f182c75df2270836601b6e064fe`. Repaired main blob: `8af1c3e8d5dba212f9ab239b562461d38e104b53`, SHA-256 `258c4b152ca9a1fbd25d5f3cc20b85fcb9a61fa645c873d1238b6e5a05a7d8ee`.

Test blob: `5c81b96d46b7a63437f655051025bfa669b57d43`, SHA-256 `97c6b91cea9221d5cbc8cf71665c99b4bc26329a7a0997cce6f5889cab172122`.

The original fails four of the 16 new tests: required body error preservation, optional body error without retry, variadic body error without retry, and unsupported-arity construction. The repaired main source passes all 16. Normal one/two-argument callables, optional configuration, bound methods, callable objects, partials, keyword-only defaults, fresh opponent state, unchanged Arlene special handling and source metadata are covered. The test imports the complete resolver module and loads actual on-disk fixture opponents; only unrelated game/overlay imports are test doubles. No game or seed is used.

```text
original: Ran 16 tests; FAILED (failures=4)
repaired main: Ran 16 tests in 0.013s; OK
repaired Claude resolver: Ran 16 tests in 0.013s; OK
```

Reproduce from repository root:

```sh
python -B revenue/kaggriculture/cloud-combination-analysis/test_opponent_invocation.py
# To evaluate a saved original or the owning branch's resolver:
TITAN_OPPONENT_RESOLVER=/absolute/path/to/arlene_arm.py \
  python -B revenue/kaggriculture/cloud-combination-analysis/test_opponent_invocation.py
```

The owning Claude branch additionally has a public-bank registry absent from this main source. Its original resolver is `1132023eab7af9f2ea2325437880c6b2e6d7526e`; applying only the same invocation delta produces `4885d62f7fba568a483e63ed57ca1b136b7c35ee`. The bank paths are retained, not replaced by the main file. Branch integration and the existing executor's direct consumption of PR9999 timing are separate delivery steps, not claims made by this main-source receipt.

No policy decisions, opponent source, existing result files, running processes, full panels, default selections or held data are changed. This repair does not retroactively relabel completed games, and the focused local result is not a whole-repository CI claim.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
