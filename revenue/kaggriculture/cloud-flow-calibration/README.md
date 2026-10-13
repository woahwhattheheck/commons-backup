# Causal whole-window flow weighting

Optional T12/T15 consumer implemented by ASTRA-QUILL. This directory changes no existing controller, seller, solver, history source, freeze, or selected package. It supplies an online learner, an actual `FlowHistory` adapter, an offline JSONL evaluator, and reproducible market-stage checks. Python 3.10+; standard library only.

**Experimental weights are not calibrated probabilities. `recommended_alpha` is always zero. No game-strength, held-out calibration, or policy-promotion result is claimed.**

## Callable

```python
from calibration import CausalWindowEnsemble, predict_history

# Instantiate once per match, product, and threshold/deadline family.
learner = CausalWindowEnsemble(game_id, "CARROT")
f = predict_history(learner, history, now=now, end=end,
                    cutoff=deadline, threshold=5)
# Persist f before the outcome. After observation end+1 or later:
r = learner.resolve(f["ticket"], public_intervals_through_deadline,
                    observed_at=observation_step)
```

`history` is the existing T12 `FlowHistory`; it is neither imported nor mutated by the runtime module. Alternatively, pass its `window_prediction(product, now, end)` result to `learner.predict(...)`. The latter validates the supplied schema and past timestamps, not the provenance of an arbitrary caller-created prediction. `predict_history` additionally rejects a history already containing the predicted present or future.

The target is **total rival sales at least q during [now, cutoff], inclusive through the end of that market stage**. It does not identify before/paired/after position inside a simultaneous market. Keep threshold, cutoff offset, and window length constant within a learner. Use separate learners for different event families and reset at each game. Tickets encode the game, product, event family, and sequence without delimiter collisions. Windows do not overlap within a learner; resolve the single pending window before requesting another. Identical pending retries return the same immutable snapshot; altered retries, early outcomes, reused outcomes, and reversed time raise `ValueError`.

The four experts are zero-flow, same-phase complete historical windows, and whole-window shifts of minus/plus one step. Clamped dates aggregate quantity; no independent-hour probabilities or fictitious product paths are constructed. Each historical component remains explicit even when its stream equals another component. There is no fitted public-state-conditioned expert in this revision.

The returned components have experimental masses summing to one, including `stream=None` for unknown behavior. Default unknown mass is 0.25, a design parameter rather than a confidence estimate. Insufficient complete history makes the entire scenario mass unknown. Components are empirical dated sale streams, **not promises of future stock, feasible rival actions, receipt tables, or fill confirmations**. They are not a drop-in probability distribution over T15 order-alignment columns. Pricing, physical feasibility, adversarial scenario coverage, and whole-plan persistence remain with their existing consumers.

For a conditional model score p and unknown mass u, `probability_interval` is `[(1-u)*p, (1-u)*p+u]`, accounting only for the arbitrary unknown branch—not a confidence interval for model error. The diagnostic midpoint assigns 0.5 within that branch by convention. Neither object justifies exploitation.

## Learning and censoring

Supply T12 `FlowInterval` objects or dictionaries containing `step`, `product`, `lower`, and `upper` (the latter may be null). Dates must be unique and inside the target subwindow. A summed lower bound at least q identifies a positive event. A finite summed upper bound below q identifies a negative event. Missing dates or a straddling interval otherwise leave the event censored; a known lower bound can still prove a positive event with missing dates.

Only identifiable labels update weights: `log(w_e) <- gamma*log(w_e) - eta*(p_e-y)^2`, normalized with a numerical log floor of -700. Default eta=2 and gamma=1 are fixed experimental choices, not fitted on the retained fixtures. Missing experts are not assigned fabricated predictions. Censored outcomes update neither expert weights nor the Beta(1,1) prior-rate control. Predictions and control rates used for scoring are the exact pre-outcome copies.

The learner keeps one bounded pending window, up to 24 dated steps and 64 historical components per expert by default. Offline evaluation retains its input/output records in memory; it is not the bounded agent runtime.

## Reproduce and inspect

From the repository root, using the existing engine artifact 10005621438 (its `engine/` directory):

```bash
D=revenue/kaggriculture/cloud-flow-calibration
python "$D/check_calibration.py" \
  --flow-file revenue/kaggriculture/cloud-market-response/flow.py \
  --engine-dir /path/to/existing/engine --output-dir /tmp/quill-check
python "$D/unpack_evidence.py" --output-dir /tmp/quill-retained
python "$D/replay.py" /tmp/quill-retained/public-market-fixture.jsonl \
  --output /tmp/quill-replayed.json
```

The evidence manifest retains every extracted digest and the expected SHA-256 of the full replay JSON. The compact ledger preserves all 28 prequential outcomes, weights, prediction intervals, and per-expert/control scores. Replaying the raw fixture regenerates the complete per-window streams and descriptive grouped reliability report.

JSONL records use `kind=start|forecast|outcome` plus `game_id` and `product`. A start records optional `parameters`, `split`, and `opponent_family`; a forecast includes the actual history prediction and now/end/cutoff/threshold; an outcome includes the explicit returned ticket, observed_at, and target-subwindow intervals. The CLI supports one event family per game/product per input. Split/family are reporting metadata, never prediction inputs. Duplicate starts and duplicate outcome tickets are errors. `summarize` groups by complete game, split, family, product, event family, phase modulo 24, and support; it refuses to place one game into different splits/families or score an outcome twice. Censoring can bias the identifiable subset, so its Brier/log losses and reliability bins do not establish calibration.

## Executed scope and limits

The final successful suite passes **33 focused methods** with **90 actual official market-stage executions per full suite run**. It checks the unmodified T12 source against the unmodified official `_process_market` and `_town_consume` functions. The loader supplies only the unused framework seed-resolver import; it raises if episode initialization is attempted. No game initializer, agent controller, full episode, or random seed is used.

Those stages are independently manufactured states with explicit timestamps, not a continuous simulated match. They form two deterministic seat variants of a constructed early-to-later sale-pattern change. The 28 forecast windows have 24 identifiable labels and 4 censored labels; errors at the pattern change remain in the output. The two seats are not independent validation samples. Two isolated semantic negative controls—turning censoring into zero labels and exposing the private pending forecast to mutation—are rejected by the same suite; their separate executions are recorded, not added to the successful run's 90-stage counter.

Other checks cover exact threshold edges, missing intervals, complete streams, shift clamping, shuffled history, future contamination, hidden-stock twins with identical public history, frozen retries, duplicate diagnostics, numerical stability, the discounted update equation, prior-rate timing, event-family identity, split isolation, and the real CLI. The recorded latency is warm `predict` only for these small fixtures, excluding imports, history generation, pricing, and the rest of an agent. It is not a whole-agent runtime guarantee.

No held-out game/family calibration study or useful action activation has been measured here. The next substantive evaluation requires complete *development* public-observation histories, followed by independently separated games/opponent families after parameter freeze. Do not relabel consumed T12/T15 held seeds as fresh; do not change alpha or selected SELL on the strength of these fixtures.

## Source identity

T12 `flow.py`: Commons commit `4d7fd6d4d4e1f71941f7fe76b8e10274f1bfc1a6`, Git blob `7b3c1c383e98ce1eb5bf539caddf0ab4351f8633`, MIT. Existing source is consumed in place, not vendored or modified.

Official engine: Kaggle/kaggle-environments commit `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`, `kaggle_environments/envs/kaggriculture/kaggriculture.py`, blob `3c202c7ee921da239356789e266b694635103fc4`, Apache-2.0. Existing artifact bytes were used. Future test receipts name these source commits only when the actual corresponding input blobs match; otherwise they retain the real hashes and null commit attribution.

Related consumer proposal: T12 thread `1788809875.974229`, addition `1788814018.982219`; claim `1788818077.153819`. T12 flow/scorer, T15 solver/selector, RILL feasibility, ASH continuation, and SORREL composition remain separate owned components. No Kaggle write, owner-PC computation, new transport workflow, or spend was introduced.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
