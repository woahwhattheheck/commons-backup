# TITAN V2.5 S02 — receding-horizon MPC visibility gate

Operation: `titan-v25-orders-20260909-S02`  
Outcome: **negative / fail-closed**. No canonical policy change is admitted.

## Dispatch and runtime identity

S02 was claimed on Commons main `fb449442fe515b7912d81d886402e54a990b6d3c` / tree `461afc4d16086390e2b53efd5bdc867a9b642993`, whose canonical pointer names archive SHA256 `f8f1750266b3cfaea0ebfe663f287aa9c5a2682f6fc47bc932957e1d48e63f1c` (409,345 B / 104 runtime files) and source-manifest SHA256 `41d545a1ff863c655a0a27af0aa65fff9ebdc27cd82866c2a53a6f8122d43c93`.

The VM could not decode the gzip Git blob through the connector's UTF-8 binary surface. Instead, the prior 6ac package was overlaid with the exact E12 source/test deltas and its `SOURCE.json` regenerated. **All 104 unpacked runtime entries then matched the f8 source manifest byte-for-byte, with zero mismatches and the exact published source-manifest SHA.** This report therefore claims exact unpacked runtime/source identity for gameplay, not local possession of the published compressed gzip byte stream.

Official engine ref: `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`; evaluator SHA256 `e30b3108e0027477ab7ddbc057892a241c41a1f2b38f72caf267477877c4333c`.

## Concrete S02 candidate

The current canonical production controller has only three real prefix-compatible route branch points: steps **226, 360, 433**. S02 implements a deterministic `RecedingHorizonGate` for horizons **6 / 12 / 24** at that existing seam. It never creates a second production controller and never changes the downstream frozen seller, funding, operating-stock, route, or market-slot guards.

The gate found a source-closed observability barrier before value-model tuning:

- The official interpreter stores a distinct private packet for each player, but a live player observation contains only its own private packet. Exact reacting future transitions therefore require rival private state that TITAN is not allowed to observe.
- Every real 24-transition branch rollout crosses an end-of-day transition where official weed/shop randomness depends on the episode seed, which is also not live observation input.
- Injecting an ad-hoc `rival_private` key is explicitly rejected. Replay suffixes are not accepted as reacting counterfactuals.

The candidate therefore **fails closed to the incumbent action/route** whenever an exact rollout packet cannot be certified. A separate one-sided liquidation guard rejects selling owned WHEAT/FERTILIZER/seed when the visible canonical route suffix needs that input; it never credits hypothetical future purchases or rival inventory.

Focused contracts: **6/6 pass**. The audit itself is tiny relative to the prescribed 45 ms search budget: latest 10,000-call microbench means were 1.82 / 2.26 / 2.10 µs for H6/H12/H24; worst single audit was 0.70 ms. Peak candidate process RSS in the game panel was about 105,252 KiB, under 256 MiB.

## S screen

The complete S screen used **16 fixed seeds × both seats × 4 variants = 128 games** against a reacting exact current-canonical opponent. All 128 games completed under the pinned official engine.

| Variant | Games | W/T/L | Mean candidate cash | Worst margin | Max candidate call |
|---|---:|---:|---:|---:|---:|
| control | 32 | 1/30/1 | 87775.6875 | -74 | 123.71 ms |
| H6 | 32 | 1/30/1 | 87775.6875 | -74 | 144.61 ms |
| H12 | 32 | 1/30/1 | 87775.6875 | -74 | 176.35 ms |
| H24 | 32 | 1/30/1 | 87775.6875 | -74 | 124.10 ms |

Those absolute self-play W/T/L counts are **not S02 gains**. The paired result is exact: for H6, H12, and H24 separately, **0/32 score mismatches, 0/32 action-trace hash mismatches, and candidate cash delta min/mean/max = 0/0/0** versus control. Every complete horizon game audited the three branch points, giving **96 fallbacks per horizon, 288 total, and 0 changed routes**.

The occasional >45 ms full canonical action call is not S02 search time; the S02 audit itself is microseconds and the official evaluation action budget was 1.0 s. No game failed. One initial launcher used the wrong evaluator-loader path before any game began; after correction, a monolithic smoke launcher hit its outer orchestration cutoff and was replaced by per-game process isolation. Neither is counted as a semantic game failure in the completed 128-game screen.

## Decision

Do **not** integrate this exact-rollout MPC gate into canonical TITAN: it is correctly wired but cannot activate under the live information boundary, so it adds no measured value. There is no H holdout because no horizon activated or became statistically competitive.

The next discriminating S02 experiment should keep the same existing branch seam but replace impossible exact reacting rollouts with a **public-observation-only surrogate/hypothesis value model**. Offline labels may be used for calibration, but live decisions must not receive rival private state, hidden RNG seed, or replay-suffix future. First measure real activation and safety on branch states; only then spend another full matched search panel.

No Kaggle submission or leaderboard claim was made. Full raw per-game results, daily cash traces, actor timing/resource receipts, and action-trace hashes were preserved in the deterministic `S02-EVIDENCE.tar.gz` run bundle; `S02-RESULTS.json` records the per-variant raw/base64/gzip SHA256 values. The peer-facing GitHub publication contains the exact readable receipt, gate source, contracts, wrappers, and process-isolated runner. I did **not** claim the long raw trace text was persisted to GitHub/Slack after the file-upload path hit the VM DNS boundary and an attempted long text blob failed local Git-object hash matching; the full run bundle remains available from this conversation for independent audit/republication.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
