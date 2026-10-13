# Selected-market consumer checks

`check_market_contracts.py` exercises the generic selected-action SELL interface against the pinned official market executor. It constructs synthetic states, not seeded games, and uses the existing offline engine loader without fetching or installing anything.

## Run

From a Commons checkout containing `cloud-execution-lab`, `cloud-eval` and its existing offline loader:

```sh
python3 revenue/kaggriculture/cloud-selected-market-checks/check_market_contracts.py \
  --engine-cache /path/to/existing/engine \
  --json-output /tmp/selected-market-results.json
```

The cache must contain `kaggriculture.py`, `kaggriculture.json`, and `utils.py` from `Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`. The existing loader checks their Git blobs before execution. Reuse accepted engine artifact `10005621438`; this suite does not dispatch transport jobs or games. `--lab` and `--evaluator` select existing source paths for an isolated source pack. The command returns nonzero on a failed assertion and writes the exact source hashes plus all market receipts when `--json-output` is provided.

## Terminal stock contract

Standing stock minima must remain binding after the last executable market, just as dated cash minima do. The final-decision return in `ProjectionLedger.feasible` previously checked cash alone. The correction checks stock minima before returning, without applying post-final deposits, counting salvage, changing optimizer scoring, or constructing a production controller.

The discriminating fixture reserves WHEAT1 and supplies a valid fallback that sells only CARROT1. With the original seller, decision717 returns that fallback, but decision718 sells the reserved wheat too. The corrected terminal path returns the valid fallback in both seats. Official market execution retains WHEAT1 and produces cash1035 rather than selling it for cash1060. This is compliance with an explicit caller reservation, not a profit or policy-strength claim. A caller seeking unrestricted final liquidation should not reserve that stock.

## Executed coverage

Fourteen test methods pass on the corrected source, including 28 actual official `_process_market` executions. The exact original seller produces seven failing subtest/assertion results across three terminal-reservation methods; the other eleven methods pass. The suite covers alternate episode length, final-deposit exclusion, before/after cash minima, paired product-buy cost bounds, seed storage, animal capacity, SELL-funded hires, repeated hire and land costs, duplicate sales, reserved slots, and fallback/input nonmutation.

`VALIDATION.json` records the exact tested sources and baseline/candidate counts. These are focused synthetic integration checks: zero full-game panels, no seeds consumed, no hosted rating claim, and no whole-repository CI claim. The frozen standalone scheduler and pure optimizer are unchanged. Ordered non-market projection checks belong to the separate `cloud-selected-projection` component; this patch changes only the terminal stock/cash return condition.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../../titanmcp.html). Cite Latch Pad KEEP.
