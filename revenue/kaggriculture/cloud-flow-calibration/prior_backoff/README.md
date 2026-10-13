# Prior-backed event forecasts

An optional marginal-event refinement of the existing flow ensemble, plus an executed cross-opponent development comparison. All source in PR9986 and the PR10263 assessor remains unchanged.

## Runtime

```python
from backoff import predict_event
result = predict_event(frozen_forecast, expert="same_phase")
p = result["probability"]
```

`frozen_forecast` is the pre-outcome snapshot from `CausalWindowEnsemble`. The callable uses `p = (1-u)*p_expert + u*p_prior`, reusing its existing unknown mass and causal prior-rate control. The default expert is `model`; the separately assessed alternative is `same_phase`. A missing expert or wholly unknown forecast uses the prior exclusively. The function is stateless, does not mutate its input, accepts no outcome label and introduces no fitted parameter.

The original unknown branch, complete streams and selected policy are not replaced. This is a **single threshold-event** model, not calibrated probabilities over future quantities, market positions, joint product flows, fills or complete legal plans. The event interval describes only the retained arbitrary unknown mass. `recommended_alpha` remains zero. A caller supplies the original frozen snapshot, not a probability reconstructed after an outcome.

## Executed findings

The two formulas were fixed after the lonespear development assessment and before the COK development outcomes were examined. `FROZEN.json` records the unchanged runtime SHA-256, formulas and six planned COK members. No parameter was changed during the transfer assessment.

Same-population warm results, with at least three complete historical windows:

| Cohort / model | Identifiable labels | Brier | Log loss |
|---|---:|---:|---:|
| Lonespear / original weighted | 8,664 | 0.009929 | 0.105661 |
| Lonespear / raw same-phase | 8,664 | 0.009469 | 0.106640 |
| Lonespear / same-phase + prior | 8,664 | 0.009583 | 0.039982 |
| Lonespear / prior control | 8,664 | 0.013764 | 0.069339 |
| COK / original weighted | 8,522 | 0.010322 | 0.163399 |
| COK / raw same-phase | 8,522 | 0.010078 | 0.184146 |
| COK / same-phase + prior | 8,522 | 0.010252 | 0.049729 |
| COK / prior control | 8,522 | 0.015388 | 0.075812 |

The explicit same-phase-backed arm improves both aggregate warm metrics versus the original weighted model in these two cohorts, but it does **not** dominate every alternative or game. Raw same-phase still has lower Brier. Both COK 9881037 seats worsen warm Brier versus weighted by 0.00017948 each. Prior fallback also raises cold-start Brier, so all-window Brier remains worse than the original diagnostic model despite substantially better log loss. The weighted-backed arm, cold groups and adverse cases remain in `RESULTS.json` and the full evidence.

COK contributes 10,038 windows: 9,725 identifiable, 313 censored and 153 positives. Its 30,198 own fills, 30,156 public intervals and all identifiable labels agree with the separate offline replay; 4,314 recorded market transitions have zero cash residual. Together with lonespear this is 12 **previously completed** games on three shared map seeds and two opponent lineages, not a fresh held panel or 20,076 independent observations. Rare events, shared maps and censored-label exclusion limit inference. No calibration, action activation, stronger policy, win-rate change or hosted rating is established.

## Reproduction

Use the same IRIS artifact10037073246/PR9975 input as the PR10263 assessor. No new game, exporter or policy call is needed. First produce its original lonespear output, then:

```bash
D=revenue/kaggriculture/cloud-flow-calibration
P=/path/to/extracted/revenue/kaggriculture/cloud-policy-portfolio
python "$D/prior_backoff/test_backoff.py"
python "$D/prior_backoff/compare.py" --portfolio "$P" --calibration-dir "$D" \
  --design-output /path/to/original-quill-results --output /tmp/new-backoff-results
python "$D/prior_backoff/test_compare.py" --calibration-dir "$D" \
  --assessment-output /tmp/new-backoff-results
```

The runtime suite passes 11 methods; eight actual-forecast integration methods also pass. They exercise frozen equations, missing/cold support, finite probability inputs, input preservation, outcome poisoning, duplicate tickets, censoring, reporting-label independence and original source identity. The full comparison CLI completed on all six planned COK controls. The same input archive's empty older v1 controls were not substituted for the predefined v2/v3 members.

The comparison reuses the PR10263 public/own-input replay. Current rival actions and reconstructed rival inventories enter only its separate offline label check, after forecasts are frozen. Actual opponent-family reporting replaces the original assessor's lonespear label for the COK group; this metadata never enters predictions. The complete output retains every forecast, both refinements, baseline scores, censored cases and descriptive reliability bins. Exact raw-output/log hashes and source pins are recorded in `RESULTS.json`; the complete evidence is in the associated Library bundle. Output paths must be new, preserving prior evidence.

## Source bindings

`backoff.py` SHA-256: `ae4b7f98b4340f04f6c2f0da6dae32d5043b4be63aa0e3fd5068fac8f44466a4`. Existing calibration blob: `75e67d65583ab83847b95dee426ff3a49dee1c87`; assessor: `765874398a98603e48109f5c92db86461bc0290f`; T12 flow: `7b3c1c383e98ce1eb5bf539caddf0ab4351f8633`; official engine: `3c202c7ee921da239356789e266b694635103fc4`. Existing codec/ledger and licenses are retained through the PR9975 archive. New files are MIT. No source takeover, default change, Kaggle write, owner-PC computation or spend.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
