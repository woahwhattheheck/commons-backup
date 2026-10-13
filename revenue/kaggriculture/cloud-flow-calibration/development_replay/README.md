# Recorded-development flow assessment

QUILL's additive consumer for the existing causal flow ensemble. This directory adds a public-input replay interface, a runnable assessment and its regression tests. It changes no history model, expert weights, seller, controller, selected policy or original evidence.

## Measured result

Six previously completed frozen-SELL controls against lonespear v18 **greedy**, three development seeds in both positions, produce 10,038 forecast windows. There are 9,832 identifiable labels, 206 censored labels and 167 positive events. The aggregate model Brier error is 0.013327 versus 0.018969 for its causal prior-rate control, but log loss is worse: 0.219573 versus 0.090477.

On the same 8,664 identifiable windows with at least three complete prior windows, model Brier is 0.009929, prior-rate 0.013764, and the simpler same-phase empirical expert **0.009469**. Thus the ensemble does not beat that simpler expert on this metric. Warm log loss is 0.105661 versus the prior's 0.069339. The fixed unknown-branch midpoint also worsens Brier error. These are retained findings, not tuned-away failures.

All six games' warm model Brier errors beat their own prior control; they represent only **three seed clusters and one opponent lineage**, not six independent validation samples. Positive labels are rare, and excluding ambiguous labels can bias the scored population. No held-out calibration, confidence interval, action activation, win-rate gain or leaderboard effect is established. `recommended_alpha` remains zero. WHEAT/FERTILIZER buying versus selling is outside this model, never encoded as a zero prediction. In cold windows the entire scenario mass is unknown; the raw zero model score is only a diagnostic, not an actionable probability.

## Actual causal boundary

`PublicReplay(engine, flow, calibration, game_id).feed(observation, own_action)` accepts only the current player-visible/own observation and the selected own action. It never accepts a current rival queue, future row, hidden seed or terminal outcome. It derives own non-operating fills from the exact own unit stage, ordered shed stock and own SELL queue. These products cannot be bought in the pinned engine; their fills, including floor-price sales, do not depend on the rival queue. Operating products remain excluded.

The next public observation resolves the previous market-flow interval through unmodified T12 `infer_flow`. Forecasts use only intervals strictly before their target. The driver freezes the original ensemble's predictions first, then runs the existing recorded-action ledger separately to check the labels. Reconstructed rival state and recorded rival actions remain in this offline check. Game IDs identify records and do not enter feature selection or random draws.

Protocol fixed before scoring: seven non-operating products; threshold five units; nonoverlapping three-step windows; target total sold during the first step's entire market, not a within-market position; history period 24, five historical windows, minimum three; existing eta=2, gamma=1, unknown mass=0.25. Each game/product starts a new learner. No hyperparameter fitting or policy selection occurs.

## Validation and reproduction

The new suite passes **16 methods** using the actual retained dependencies. It covers stock/floor/deposit order, duplicate sells, order limits, observation immutability, public clock precedence, missing/reversed observations, reset, pre-outcome freezing, same-population scoring and poisoned current-rival/future metadata. On the full recorded input, 30,198 own-fill checks match; 30,156 public intervals contain the offline truth; all 9,832 identifiable threshold labels agree. The existing ledger reconciles 4,314 recorded market stages with zero cash residual. These are analyses of existing actions, not new policy invocations or games.

Use the existing IRIS artifact **10037073246**. Its ZIP SHA256 is `4c7bc03c383ba73d0687156f864b7d529eacd63bfa8a755b66d90805a3b31335`; extract its `t14-9975-retained.tar` without changing members. The portfolio root is `revenue/kaggriculture/cloud-policy-portfolio` within it. No new export job is needed.

```bash
D=revenue/kaggriculture/cloud-flow-calibration
P=/path/to/extracted/revenue/kaggriculture/cloud-policy-portfolio
python "$D/development_replay/test_assess.py" --portfolio "$P" --calibration-dir "$D"
python "$D/development_replay/assess.py" --portfolio "$P" --calibration-dir "$D" --output /tmp/new-quill-results
```

The output directory must not already exist. The six selected members and semantic hashes are in `RESULTS.json`; the decoder checks compressed parts and reconstructed hashes. It scores only those development members, not other arms or validation data stored in the same archive. The CLI retains all per-window forecasts/errors, intervals, own fills, offline receipts, per-product/game scores and descriptive reliability bins. The full output and executed log digests are recorded in `RESULTS.json`; the raw evidence is in the associated Library delivery.

`RESULTS.json` is a compact projection of the complete output, retaining exact floating-point values. Score rows name their own count, so an expert available only on warm windows is not compared with a control over a different population. All/ warm/ cold and per-product/game groupings overlap and must not be summed as independent samples.

## Source provenance and limits

Existing calibration: PR9986, Git blob `75e67d65583ab83847b95dee426ff3a49dee1c87`, MIT. T12 flow: commit `4d7fd6d4d4e1f71941f7fe76b8e10274f1bfc1a6`, blob `7b3c1c383e98ce1eb5bf539caddf0ab4351f8633`, MIT. Official engine: Kaggle/kaggle-environments commit `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`, blob `3c202c7ee921da239356789e266b694635103fc4`, Apache-2.0. T14 codec, evaluator, ledger and development archive are reused from PR9975/source `5be6099f5ab2b3a20855bdee1e1e42f336eab678`; their exact input blobs are retained in the protocol.

This is an offline bounded-dataset assessor, not a streaming production agent or a market-order-alignment predictor. It holds decoded traces/results in memory. No new games, seeds, uploads, purchases or owner-PC execution. The next model choice needs independent game/family validation and actual action evidence; this assessment does not replace IRIS behavior, JOINT-HISTORY joint scenarios, T12 flow, T15 selection or TITAN rating calibration.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
