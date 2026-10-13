# TITAN V2.5 E16 — terminal value screen

Operation: `titan-v25-orders-20260909-E16`  
Outcome: **negative / no-op on the frozen dispatch archive**. No policy source patch is admitted.

## Source pin and boundary

E16 was claimed against Commons main `2e171663257c43b2be3db7a34e8c6761bb4b5d6b` / tree `d40ac4ce54d3850d819fef422d9dc097387c7b28`, canonical archive `6ac897241cb54baa205e4132fab1f83e7a21e4ae957e19e16c6c48a7ecbd8bc1` (408,621 B / 104 runtime files), source-manifest SHA256 `8f65a8b4c9c6c73a8080995731a954bdc963b72e29614961572f525eb10b8c17`.

The canonical archive advanced after dispatch to `f8f1750266b3cfaea0ebfe663f287aa9c5a2682f6fc47bc932957e1d48e63f1c` on observed main `d56c11b0199d3fcf7820922023a3aa8d98370888`. **Nothing below is silently attributed to that later archive.**

Official-engine ref: `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`. The experiment enabled only the already-shipped `terminal_history` selector and explicit finite history hypotheses; all other 6ac feature flags were unchanged. The instrumentation wrappers returned `main.agent` unchanged.

## Full-game comparison

The first screen used 32 distinct seed/opponent pairs × both seats = **64 games per variant, 128 complete games total**. Enabled and control used the same cells. There were **0 failures**, **0 score mismatches**, **0 trace-hash mismatches**, and **0 nonzero paired candidate-cash deltas**. Mean/min/max E16-minus-control candidate cash delta were all exactly 0.

| Opponent | Games | Enabled W/T/L | Mean candidate cash | Worst margin |
|---|---:|---:|---:|---:|
| exact 6ac baseline | 22 | 0/22/0 | 87478.7 | 0 |
| Arlene | 22 | 22/0/0 | 96063.4 | 890 |
| official starter | 20 | 20/0/0 | 170845.8 | 125105 |

Those W/T/L counts describe 6ac against the screen opponents; they are **not** an E16 improvement. E16 and control were action-trace identical in every paired cell.

## Terminal receipts

Across 64 enabled games, the terminal history family was ready and the native terminal-input packet complete in **43/64** cells. Every applicable selector result was `baseline_optimal`; **0/64 final queues changed** and **0/64 fell back**. The other 21 states were unready/inapplicable.

Final emitted market queues were all pure SELL queues: length 3 in 24 cells, length 4 in 12, length 5 in 28. Maximum was **5 of 10 slots**; there were no duplicate product SELLs and no zero-quantity SELLs.

A six-game instrumentation-only subset bound the exact post-unit shed to the final queue. It found **0 stranded projected saleable units**, used 3–5 of 10 market slots, had zero fallbacks, and the slowest measured step-718 E16 action completed in **18.94 ms** (1.0 s action budget).

## Why the result is negative

`FrozenSelected.transform` already treats step 718 specially: it computes the exact post-unit shed and calls the existing `_terminal_settlement`. That settlement expands inherited product SELL rows to exact shed quantities, removes duplicate product SELLs, and appends each missing positive shed product by value until the 10-row market cap. The normal nonterminal joint optimizer is bypassed at the terminal step.

The optional history selector is not dead code: the shipped five-test terminal-history suite includes a constructed step-718 two-product state where it changes sale order and native receipts are verified. All five terminal-history tests passed here, plus the focused guard proving terminal settlement bypasses the nonterminal joint optimizer. But in the real 64-game E16 screen, every applicable selector packet judged the frozen settlement already optimal.

## Admission decision

Do **not** enable `terminal_history` from this result and do not add another terminal policy. There is no demonstrated omitted legal queue, no terminal cash gain, no W/T/L gain, no clipping, and no deadline failure on the pinned 6ac archive. Preserve the selector and tests as research-only.

Revisit E16 only on a new source-pinned archive when an observed final state contains genuine mixed non-SELL commitments or ≥10 executable economic rows that create real terminal slot contention, or a source-closed receipt shows reachable post-unit shed value omitted by the frozen settlement.

No Kaggle submission and no leaderboard claim were made. Full compact cell receipts and hashes are in `E16-RESULTS.json`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
