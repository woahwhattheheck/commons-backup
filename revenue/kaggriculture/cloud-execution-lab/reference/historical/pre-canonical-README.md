# T08: finite-horizon SELL scheduler over intact Arlene

The selected v3 callable recorded **12W/0T/0L** on the development panel and **8W/0T/0L** on the held-out panel, against unchanged Arlene and Apex in both seats. The paired unchanged-parent controls recorded 6W/6T/0L and 5W/2T/1L. These are cloud-container tournament results. No Kaggle submission, public-notebook write, or rating change is claimed. Exact cash, receipts, timing, and controls are in [RESULTS.md](RESULTS.md).

This component changes market execution over the strong public Arlene controller. Its source remains byte-for-byte intact at SHA-256 `1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4`. The selected scheduler SHA-256 is `32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9`; [SOURCE-FREEZE.json](SOURCE-FREEZE.json) was recorded before held-out use, and its listed runtime sources stayed unchanged afterward.

## Callable integration

For one actor in one persistent process:

```python
from scheduler import agent

action = agent(obs, configuration)
```

For an embedding application, retain one separate instance per actor and match:

```python
from scheduler import SellScheduler

policy = SellScheduler()
# Repeat once for each observation in this actor's match:
action = policy.act(obs, configuration)
```

The module function is `scheduler.agent(obs, configuration=None)`; it resets its instance at observation step 0. The class interface is `SellScheduler(mode="candidate").act(obs, config=None)`. Both return the full Kaggriculture action dictionary. The class runs its own intact Arlene instance internally, obtains the parent action, and then schedules SELL execution. This checkpoint exposes an end-to-end callable; it does not expose a market-transform function accepting an independently computed baseline action. T08 composition should use the callable once per observation and keep its controller and scheduling state together.

Keep `scheduler.py`, `mechanics.py`, `reference/next-panel/vendor/arlene.py`, and `reference/decision/decision.py` in their existing relative layout, together with the accompanying notices and licenses. The optimizer uses Python's standard library and these retained source modules. It does not require Cvxportfolio, CVXPY, an LM, or a financial trading platform. `candidate.py` provides the same callable for the existing evaluator.

## Execution behavior

1. Call unchanged Arlene on the actual current observation, and project its farmer and hand actions through the retained deterministic engine unit functions. Optimize available post-unit shed products; leave WHEAT, FERTILIZER, and animal stock under the parent controller.
2. Consider integer first-sale amounts and a small family of later tranches over at most eight future steps. Candidate dates include the turns after known town-consumption ticks. Bound the horizon at the current day, the next parent decision checkpoint, or the actual final decision.
3. Price conditional paths with exact configured dollar rounding, per-unit floor admission, and shared precommit paired quotes. Reuse the repaired `sale_receipts` interface from the pinned decision module. Both seats' corresponding units quote from the same precommit inventory; a $1 sale pays and consumes own stock without adding market inventory.
4. Evaluate no-rival-sales and named rival-supply scenarios separately. Public standing yields and recently observed harvest changes determine stress quantities; paired, later-order, next-turn, and pre-delayed-batch placements explore different timings. Select by the worst improvement in own-minus-rival modeled value relative to the inherited sale plan, then aggregate scenario improvement. This is a conditional local objective, not a calibrated win-probability model.
5. Reserve current-route operating cash, including successive land purchases, and check conditional current-route arrivals against shared shed capacity. Distinguish unit-stage DROP overflow from later automatic EOD deposits. Preserve original non-SELL order values and indices; retain empty positions for withheld SELLs, clamp multiple SELL orders to remaining stock, and append extra sales after inherited orders within the market-order limit.
6. Execute the first decision and replan from the next observation. Unsold stock has a conservative receipt-based continuation value at an artificial short horizon. Zero salvage applies at the actual match end; decision 718 uses the parent's terminal settlement over the exact post-unit shed.

Farmer and hand actions and non-SELL order indices were checked against an independent unchanged Arlene instance on the candidate's observation sequence: all 14,380 actions across the selected 20 games matched. This is preservation of the parent response to each actual observation; the candidate's changed cash and market state can still change later parent decisions.

## Bounds and evidence

The selected candidate's largest measured action, with process startup included in the cold first-action comparison, was **0.203147 seconds**. Its longest full episode was **8.538961 seconds**. The integer search spans a bounded tranche family, rather than every possible multi-product trading policy.

The market transitions are exact conditional on the scenario inputs. Rival supply is a stress assumption, and own arrivals follow the current route only; neither model reads private rival stock, hidden RNG, future replay actions, or unknown future shops. The measured panel contains three development seeds and two held-out seeds. Further integration should preserve these limits and use fresh evaluation seeds.

The plan-several-trades, execute-the-first, and replan mechanism follows [Boyd et al., section 5, Multi-Period Trading via Convex Optimization](https://web.stanford.edu/~boyd/papers/pdf/cvx_portfolio.pdf) and [Cvxportfolio MultiPeriodOptimization](https://www.cvxportfolio.com/en/stable/optimization_policies.html). This is a discrete implementation for Kaggriculture's integer, nonconvex rules. No GPL implementation code was copied.

Official interpreter commit: `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`. Existing evaluator and public-parent attribution are retained. See [ENGINE-SEMANTICS.md](ENGINE-SEMANTICS.md), `reference/engine/LICENSE`, `reference/next-panel/NEXT-DISTRIBUTION-NOTICE.txt`, `reference/next-panel/UPSTREAM.json`, and the accompanying licenses. All downloads, compilation, and simulations ran in this session's cloud container.

## Reproduce and inspect

The source-only archive `exports/titan-sell-v3-source.tar.gz` contains the callable and exact runtime imports. The complete `exports/titan-sell-lab-evidence.tar.gz` also contains every competitive-game trace, raw reports, immutable v1/v2/v3 snapshots, pinned evaluator, complete Apex source, and focused cases. `exports/FILES.json` records every retained file hash. Extract the complete archive into a cloud directory to restore the documented `runtime/` paths.

GitHub carries the complete archive as two exact byte parts to fit the connected transport. Download both parts, join them in order, and verify the combined SHA-256 against `exports/ARTIFACTS.json` before extraction:

```sh
cat exports/titan-sell-lab-evidence.tar.gz.part01 exports/titan-sell-lab-evidence.tar.gz.part02 > exports/titan-sell-lab-evidence.tar.gz
sha256sum exports/titan-sell-lab-evidence.tar.gz
tar -xzf exports/titan-sell-lab-evidence.tar.gz
```

Reproduction requires Linux, Python, a C++17-capable `g++`, and `libseccomp.so.2`. All were present in the measured cloud container.

```sh
python3 -m unittest test_engine_semantics test_scheduler -v
python3 prepare_runtime.py --runtime runtime/reproduce --candidate candidate.py
python3 benchmark.py --runtime runtime/reproduce --variants candidate,baseline --seeds 9600901,9600919 --freeze-manifest SOURCE-FREEZE.json --output runtime/reproduced.json
```

Those seeds are consumed reproduction seeds, not a new hold-out. For the measured naive comparator, point preparation at `runtime/variants/v1/naive.py`; the current `naive.py` is not the frozen v1 snapshot. Reproduction remains cloud-only. `python3 scenario_crosscheck.py` compares three existing development transitions with SORREL's separately pinned adapter; it runs no games and does not modify the candidate.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
