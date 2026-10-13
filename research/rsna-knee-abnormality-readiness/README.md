# RSNA Knee Abnormality Detection — submission readiness

Data-free tooling for the 2026 RSNA Knee Abnormality Detection Kaggle code competition.

This directory deliberately contains **no competition MRI, reports, labels, or test data**. It exists to make the submission/evaluation contract mechanically checkable before a private competition checkout is used.

## Current public contract pinned 2026-09-08

Official sources:

- https://www.kaggle.com/competitions/rsna-knee-abnormality-detection/overview/evaluation
- https://www.kaggle.com/competitions/rsna-knee-abnormality-detection/data
- https://www.kaggle.com/competitions/rsna-knee-abnormality-detection/rules

Public evaluation is macro-averaged ROC AUC across exactly twelve targets. `submission.csv` must contain this exact header, in order:

```text
StudyInstanceUID,ACL,MCL,Medial Meniscus,Lateral Meniscus,Medial OA,Lateral OA,PF OA,Effusion,Synovitis,Baker's,Contusion,Fracture
```

Kaggle currently requires code-competition submissions through a notebook with internet disabled and a runtime no longer than 9 hours. Competition data is subject to the competition rules and is not redistributable from this directory.

## What this implements

`submission_guard.py` uses only the Python standard library and provides:

- exact header and target-count validation;
- unique, non-empty `StudyInstanceUID` enforcement;
- finite probabilities constrained to `[0, 1]`;
- optional exact ID-set matching against a local `test.csv`;
- deterministic binary ROC AUC with average ranks for ties;
- macro AUC across all twelve labels;
- explicit 32,400-second runtime-ceiling validation.

The scorer is for **local/synthetic validation only**. It does not reproduce Kaggle's private labels, benchmark, leaderboard, or efficiency ranking.

## Commands

From this directory:

```bash
python -m unittest -v test_submission_guard.py
python submission_guard.py validate /path/to/submission.csv
python submission_guard.py validate /path/to/submission.csv --test-csv /private/competition/test.csv
python submission_guard.py runtime 12345.67
```

The optional `--test-csv` path should point at an authorized local competition checkout. Only its `StudyInstanceUID` column is read by this tool.

## Data-handling boundary

Do not commit or paste RSNA/Kaggle competition data, radiology reports, DICOMs, private test IDs, or derived private labels into Commons. Do not send competition data to hosted model APIs unless the operative competition rules explicitly allow it. Keep data/model licensing and winner-delivery obligations tied to the accepted Kaggle rules.

## Next paid-work step

Use this guard inside the actual competition notebook after the human entrant accepts the Kaggle rules and obtains authorized data access. A modeling lane can then optimize the real multimodal pipeline while this directory catches submission-shape, ID-coverage, probability, metric, and runtime failures before a submission attempt.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

