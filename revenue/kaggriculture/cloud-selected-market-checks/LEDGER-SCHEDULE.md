# Reuse dated consumption inside the selected SELL ledger

`ProjectionLedger.feasible` now reuses deterministic town-consumption values across the many candidate plans checked against one caller snapshot. The existing method remains the consumer: no new wrapper, controller, policy selector, dependency or runtime flag. All inventory products and their order are retained. Actual inventory, cash, purchases, transfers, pending-lot capacity and stock reservations are recomputed for every candidate exactly as before.

The cache is local to the ledger and populated only when execution reaches the original post-market consumption boundary. Rejected prefixes do not evaluate unused future dates; the final market still returns before post-final consumption or deposits. Dates are absolute. Inventory keys, observed shops, consumption intervals, planning range and the consumption function identify the cached context; changes between feasibility calls invalidate it. Nonstandard shop inputs use the original uncached path. Callers supply a stable observation/configuration during each synchronous feasibility call, as with the existing pure candidate evaluation. Engine catalogs remain the pinned mechanics, not mutable policy inputs.

## Run the new checks

The test compares the actual complete transform against the exact pre-cache `feasible` method retained from seller blob `0364fa0ab6c3f0d7cc93569efb14d3f5af66da72`. Both variants use the same current seller helpers and SPRUCE optimizer. The retained function is test-only, Apache-2.0, and hash-checked; it is not a second runtime implementation.

```sh
LAB=revenue/kaggriculture/cloud-execution-lab
python3 -B revenue/kaggriculture/cloud-selected-market-checks/test_ledger_schedule.py \
  --lab "$LAB" \
  --evaluator "$LAB/reference/evaluator/evaluate.py" \
  --engine-loader "$LAB/reference/evaluator/loader.py" \
  --engine-cache "$LAB/reference/engine" \
  --report /tmp/ledger-schedule-results.json
```

The existing offline evaluator/engine cache can also be supplied directly. Local execution reused engine artifact10005621438 and source artifact10030763484; no export job or installation was required. Without engine/evaluator flags, the source-parity tests run and the one native-market method is explicitly skipped. Add `--benchmark --samples 9 --iterations 8` for the six recorded workloads. Timings are descriptive and do not determine test success.

## Executed result

Twenty new methods pass with no skips or errors: 1,218 explicit feasibility comparisons; 99 complete transforms with identical actions, diagnostics and public-history state where tested; 4,718 identical ordered feasibility-callback records; and 24 native pinned `_process_market` executions. Inputs cover ordered spill/withdrawal, operating purchases and conservative cash bounds, empty-lot queues, final stock reservations, phase-specific commitments, changed inventory values/keys, in-place shop changes, interval changes, partial exceptions, and independent ledger instances. The deterministic repeated-call witness reduces consumption calls from900 to45 for20 checks of five dates/nine products. Three deliberately bad mutations are detected: no reuse, stale shops/intervals, and stale inventory keys/range. The last mutation raises the expected missing-product error rather than passing.

Nine alternating timing samples per implementation, eight fresh-seller transforms each, include seller initialization and ledger construction but exclude module import. On this cloud Python3.13.5 runtime, median complete-transform times in milliseconds were: empty0.1263 to0.1308; small0.4303 to0.4012; medium12.3992 to10.2610; large43.7504 to35.9137; operating-buys49.7022 to41.4820; terminal1.7827 to1.7825. Thus the three larger workloads use16.5–17.9% less time, while the empty-lot case adds approximately4.5 microseconds. Raw samples, platform, counts and source hashes are in `LEDGER-SCHEDULE-VALIDATION.json`.

These are constructed bounded-call workloads and exact source-parity tests, not a full-game distribution, whole-agent latency result, deadline guarantee or leaderboard improvement. The source uses the already-landed SPRUCE core `d2cded3d` in both timing arms; those savings are not counted twice. ATLAS ordering, WREN terminal/empty-lot checks, the original optimizer decisions, frozen standalone scheduler and exported experiment archives remain unchanged. Existing hosted compatibility suites and this new suite have distinct execution receipts; only actually executed suites should be counted.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
