# T06: bounded economic search kernel

**Delivered as reusable search infrastructure and an opt-in SELL experiment. The experiment is not promoted over the existing seller.** No existing controller, workflow, opponent, game engine, or deployment default is changed.

## What is implemented

`search_kernel.py` searches one common action-bundle sequence across explicit scenarios. It provides iterative deepening, principal-variation ordering, exact local transposition caches, a transition cap, a cooperative deadline, and bounded event extensions. Its default objective is worst-case value with an unweighted mean tie-break; that mean is not an estimated expectation. This is robust open-loop planning, not alternating minimax and not a contingent policy that can observe a hidden scenario.

The caller supplies pure `Model` callbacks: `candidates(state)`, `transition(state, action, scenario)` and `evaluate(state, scenario)`. State keys must include every relevant time, inventory, market, controller, cash and flag field. Scenario keys must distinguish hypotheses. Candidate generation is intersected across scenarios, so a selected bundle must be available in all of them. Callback state objects must not be mutated. Caches are bounded and recreated on each invocation.

`search(..., fallback, limits=Limits(...))` returns the last completely searched depth. An interrupted scenario vector cannot replace the incumbent. With no evaluated fallback, `status` is `unscored_fallback` and `values` is empty: this is not a scored recommendation. The caller must supply a feasible fallback. A callback cannot be preempted; the cooperative deadline can overrun by a callback's cost. Bound individual callback work separately. No alpha-beta bound, adversarial-chess turn model, null-move pruning, or intrinsic WAIT pruning is assumed.

For T03/T04, import `Model`, `Limits`, and `search` and provide the existing economic rollout through these callbacks. The SELL integration is a working example, not a requirement to copy its candidate grid or scenario family. `order` can prioritize an incumbent plan; `extend` can identify a service-completion or market event, with `Limits.extensions` bounding extra search. Event extension is exercised separately in tests; it is not enabled in the SELL game panel.

## Actual SELL integration and the v1 correction

`entrypoint.py` imports the existing `cloud-titan-composition/vendor/sell/scheduler.py` without modifying its files. `sell_backend.make_optimizer` wraps its `optimize_lot`. The market transition and town-consumption primitives remain the parent's `MarketPath` and SORREL receipt math. Unit routes, service decisions, buy-order slots, minimum cash release and joint capacity checks stay with the parent.

The first development implementation replaced the seller optimizer while preserving only the underlying route's weaker reference. It lost two of eight candidate games and reduced cash materially. That implementation is retained in `experiments/v1/sell_backend.py`; its eight paired rows remain in `paired-results.csv`.

The final v2 first completes the original seller optimizer. Its complete plan and receipt are retained unless a fully completed search horizon strictly improves the same relative-value metric in every supplied rival scenario. Partial search does not replace that full plan. The existing feasibility-recovery path remains intact. Terminal unsold inventory has zero reward; earlier inventory uses the parent's liquidation opportunity value. These scenario-relative improvements are conditional model results, not guarantees against an interactive opponent.

The 30ms/3,500-transition budget applies to the added kernel only. Original optimizer execution and receipt bookkeeping cost extra. The whole policy is not a 30ms implementation.

## Measured results

32 regression tests and 144 comparisons with the pinned official engine's SELL and consumption operations passed. The transaction cases include order alignment, price-floor supply admission and duplicate-shop consumption. They are not a substitute for full games.

Three complete paired panels were executed: development v1, development v2, and frozen held v2. Each contains 16 games, 719 decisions per game, with no failures. Opponents are intact Arlene and compiled Apex, both seats. There are four unique seeds overall, not 48 independent samples.

| Panel | Control W/T/L | Candidate W/T/L | Paired candidate margin change |
|---|---|---|---|
| Development v1 | 8/0/0 | 6/0/2 | -835, -296, -188, -828, -1244, -1413, +379, +1368 |
| Development v2 | 8/0/0 | 8/0/0 | 0, 0, -9, -9, +19, +19, +19, +19 |
| Held v2 | 8/0/0 | 8/0/0 | 0, 0, 0, 0, 0, -4, 0, 0 |

Held candidate mean whole-game wall time was 9.840s versus 7.117s for control. The maximum sampled candidate policy call was 209ms on held data and 294ms on development v2. Timing is local and noisy, not a worst-case bound. Both arms winning is not evidence of improvement over control. Seven held paired margins were unchanged and one was worse, with additional runtime: **keep the backend experimental**.

Equal-cap ablations reduced transitions with caching (332/428/444 versus 452/556/572 without cache), but did not establish universal wall-time gains. Ordering/PV and fixed-depth variants had the same completed value on these fixtures. The WAIT/event-extension demonstration is a controlled regression fixture, not game-strength evidence. See `ablation-summary.json`, `results.json`, and `paired-results.csv`.

## Reproduce in an isolated cloud checkout

Dependencies were read from Commons commit `7f92f6c0f4e3961be8109b2e3dc6da3e4e356d9f`, exported by existing [run 34154725233](https://github.com/woahwhattheheck/commons/actions/runs/34154725233), artifact `10030597538`. All 75 extracted files matched its manifest. `SOURCE-PINS.json` records the artifact and engine hashes. Keep the existing parent directory layout; restore that source revision for an exact historical control. This directory adds the candidate only.

The official engine is `Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`, using the existing engine artifact `10005621438` from run `34086864911`. Supply its directory containing `kaggriculture.py`, `kaggriculture.json`, and `utils.py`. No new workflow or runtime download is required.

From `revenue/kaggriculture/cloud-search-kernel`:

```sh
python -m unittest -v test_search_kernel test_sell_backend
python check_engine_conformance.py --engine-dir "$ENGINE_DIR" --output engine-check.json
python ablation.py --output ablations.json
```

Build the unchanged Apex bridge once, from `../cloud-frontier-policy/next-panel/vendor/apex`:

```sh
g++ -O3 -std=c++17 -Wall -Wextra -pedantic -shared -fPIC -Isource/include \
  -o agent.so source/policy.cpp submission_bridge.cpp
```

Return to this directory, then run:

```sh
python benchmark.py --engine-dir "$ENGINE_DIR" --seeds 9760001,9760019 --output development.json
python benchmark.py --engine-dir "$ENGINE_DIR" --seeds 9760101,9760119 --output historical-held-reproduction.json
```

The second seed pair is now disclosed and must not be called unseen data in a future experiment. The original held execution began after the three runtime-file hashes were frozen; no held-result tuning occurred. `source-freeze.json` preserves that record and transparently corrects a source-reference transcription error without changing runtime hashes. The official evaluator isolates actors, does not expose environment seeds to them, and enforces its existing action/game timeouts. Its final actor `exit_code=-9` is cleanup after completed games, not a game failure.

`paired-results.csv` retains all paired scores and action-trace hashes. `results.json` retains status, timing, CPU and RSS summaries. Full daily-bank reports were also retained in the companion execution archive, SHA-256 `87836f9817ef1e2288eee802b3be406ce237e454a38142b8f9951f20bd776d55`; it is not a hosted competition result. No Kaggle upload, submission, leaderboard claim, or default-agent replacement was performed.

## Sources and credit

The search is a new implementation. General iterative-deepening/PV ideas were studied in [Stockfish search.cpp at edb0d9db6731067ec50ce619ff372b463bc4dd5d](https://github.com/official-stockfish/Stockfish/blob/edb0d9db6731067ec50ce619ff372b463bc4dd5d/src/search.cpp#L280-L395). No Stockfish code was copied or linked. Its source identifies GPLv3-or-later; this directory's new code is Apache-2.0. Existing components retain their own notices and licenses; see `NOTICE.md`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
