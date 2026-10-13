# RSNA Knee adaptive-compute carrier

Data-free downstream model/inference controller for the 2026 RSNA Knee Abnormality Detection competition. It composes the existing readiness work rather than replacing it. No competition DICOMs, reports, labels, hidden test identifiers, model weights, submission files, scores, ranks, awards, or clinical-use claims are committed here.

## Why this lane

The competition is unusual: each study can contain multiple MRI series, the scoring target is macro ROC-AUC across 12 abnormalities, code notebooks are internet-disabled with a 9-hour CPU/GPU ceiling, and the efficiency track counts full notebook wall time. A static "read everything" pipeline can therefore waste the exact resource the efficiency prize measures.

This carrier implements **adaptive compute**:

1. choose a small label-covering first-stage series set from plane/fluid/fat metadata;
2. run any allowed public-pretrained image predictor through a narrow callback boundary;
3. aggregate series logits with label-specific routing priors;
4. mark labels near the calibrated decision boundary as uncertain;
5. load at most a bounded number of extra series only for uncertain studies;
6. freeze calibration from explicit out-of-fold training predictions only;
7. fail closed when projected full-notebook runtime or safety-adjusted peak VRAM exceeds the configured budget;
8. emit an exact-order 12-target submission matrix only after all invariants hold.

The routing priors are compute hints only. They are not diagnoses, medical advice, or label-generation authority.

## Files

- `controller.py` — series router, uncertainty controller, logit aggregation, OOF calibration, runtime/VRAM gates, resource receipts, notebook callback runner, exact submission compiler, and report-leakage guard.
- `data_contract.py` — exact organizer-shaped series manifest ingestion, explicit slice-count binding, deterministic group-safe fold assignment, and abstention receipts.
- `test_controller.py` / `test_data_contract.py` — deterministic routing, leakage, calibration, resource-budget, manifest/fold, predictor-boundary, receipt, and submission hostiles.
- `METHODS.md` — frozen experiment arms and promote/kill gates for an authorized competition-data seat.

## Predictor boundary

```python
def predictor(study_id, series_ids, stage):
    # Return ({series_id: {label: probability}}, measured_wall_seconds)
    ...
```

A real notebook can wrap an allowed public DINOv2/CNN/other public-pretrained checkpoint behind that interface. The controller itself is stdlib-only and data-free.

## Current organizer facts to re-check before submission

At publication time the official competition pages state: 12 binary targets, macro-averaged ROC-AUC, internet-off code submissions, a 9-hour CPU/GPU notebook ceiling, an efficiency track whose runtime is full notebook wall time, entry/team deadline 2026-10-15 23:59 UTC, and final submission deadline 2026-10-22 23:59 UTC. Rules can change; the competition page remains authoritative.

Sources:
- https://www.kaggle.com/competitions/rsna-knee-abnormality-detection/overview
- https://www.kaggle.com/competitions/rsna-knee-abnormality-detection/data
- https://www.kaggle.com/competitions/rsna-knee-abnormality-detection/rules

## Test

```bash
python -m unittest -v
python -O -m unittest -v
python -m py_compile controller.py data_contract.py test_controller.py test_data_contract.py
```

Passing these synthetic/data-free tests is not evidence of leaderboard performance.
