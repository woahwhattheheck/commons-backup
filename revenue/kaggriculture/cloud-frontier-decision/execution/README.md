# Price-impact-capped SELL execution over intact Arlene

Research implementation of two isolated variants: `cap` limits own supply within a price band; `demand` adds a dated release after a known town-consumption phase. `baseline` calls the same intact Arlene parent. Production/unit actions and inherited non-SELL orders are unchanged for a given observation. The parent remains observation-driven, so market effects can still influence its later route choice; paired game diagnostics distinguish observed behavior from code preservation. This is not the separate finite-horizon optimizer in cloud-execution-lab.

## Source adaptation

Read fully: Hummingbot [simple_vwap.py](https://github.com/hummingbot/hummingbot/blob/2bfaccc48dd49e71a5b6d9b3011808e127dd00cd/scripts/simple_vwap.py), [budget_checker.py](https://github.com/hummingbot/hummingbot/blob/2bfaccc48dd49e71a5b6d9b3011808e127dd00cd/hummingbot/connector/budget_checker.py), and LICENSE at that exact pin. Source mechanisms are depth within a price band, fractional size bounded by the remaining parent lot, updating remaining quantity from actual fills, and reserving each order's collateral before evaluating the next. The game implementation is new design. It does not import a financial order book, fee, bid/ask spread, or time-in-seconds cooldown. Attribution and Apache license accompany this directory.

`capped_quantity(product, inventory, stock, remaining, quote, theta=.05, alpha=.5, depth_limit=100)` enumerates exact engine marginal sell quotes, admits market inventory only for prices above one, and constructs D(theta) within 5% of the current quote. It returns `min(unreserved stock, remaining lot, floor(alpha * D))`. Depth is physically bounded by configured shed capacity, including at the price floor. A single per-product turn budget survives split orders, and stock is reserved immediately. Same-turn splitting does not recover price.

`marginal_receipt` returns conditional own cash, cash-paying sale count, admitted market-supply count, and ending inventory. It preserves the landed floor-aware receipt mechanics. These are conditional single-stream calculations: the actual engine quotes both seats from the same pre-commit inventory per unit. Opponent selling can invalidate predicted depth/proceeds.

`SellExecution.observe_fills` reconciles exact post-unit shed to the next visible own shed only across consecutive pure-SELL, non-day-close turns. This measures sale count independently of opponent prices. It does not infer actual cash or admitted supply from count. Receipt cash/supply fields are null. Impossible or missing deltas remain unknown. Repeated parent offers overlap existing lots rather than create duplicate claims on held stock.

The demand variant uses current public shop copies (duplicates consume independently) and configuration intervals. Market precedes town consumption, so an event at t permits recovery at t+1. A release is fixed when chosen, never slid forward each turn. The agent reobserves the actual market; future shop draws and opponent future actions are unavailable. Maximum deferral is four turns, independent of wall time.

## Dependencies and override behavior

Arlene remains the unchanged 1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4 source. Its chosen own route supplies a one-turn purchase/hiring dependency lookahead, not an opponent schedule. Mixed market queues are retained exactly. Deferrals flush before the next planned market expense, day-close deposits, and the last executable market step. WHEAT and FERTILIZER input sales are not capped. A conservative shed-capacity override counts projected shed, carried inventory, and all currently held field yield; it can intentionally suppress execution changes even when not all yield is immediately deliverable. No performance optimality is claimed for that bound.

LARK's unchanged ordered transfer helper projects PICKUP/DROP/PLACE, farmer then hands, including DROP overflow. It does not simulate production. Current harvests cannot reach the shed in that same unit's action; possible subsequent/day-close deposits are handled conservatively. Baseline action slots, including zero-sized capped SELL slots, are retained. Backlog fills use available slots after inherited orders. Explicit floor, dependency, capacity, and final-window tests are in test_execution.py.

## Running in the cloud

Use existing next-panel/prepare.py once to prepare Arlene/Apex adapters in a runtime directory, then:

```sh
python -B revenue/kaggriculture/cloud-frontier-decision/execution/prepare.py --runtime /tmp/execution-runtime
python -B -m unittest discover -s revenue/kaggriculture/cloud-frontier-decision/execution -p test_execution.py -v
python -B revenue/kaggriculture/cloud-frontier-decision/execution/benchmark.py --engine-dir /path/to/pinned/engine --runtime /tmp/execution-runtime --candidate /tmp/execution-runtime/cap-execution.py --seeds 9600701,9600719 --output /tmp/cap-results.json
```

Run baseline-execution.py and demand-execution.py separately for paired ablations. The evaluator is the existing official-engine cloud harness at engine pin 28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c. No alternate simulator, Kaggle upload, owner-PC execution, model install or new paid compute is involved. Runtime wrappers depend on the checkout and are runnable research agents, not a standalone submission archive. See RESULTS.md for actual completed results and selection status.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
