# RSNA Knee Abnormality Detection 2026 — data-free readiness toolkit

This directory is a **data-free engineering baseline** for the 2026 RSNA Knee Abnormality Detection AI Challenge. It does not contain competition MRI images, reports, labels, derived features, model weights, credentials, or a Kaggle submission.

## Public contract pinned on 2026-09-08

Official sources:

- Kaggle evaluation/submission contract: https://www.kaggle.com/competitions/rsna-knee-abnormality-detection/overview/evaluation
- Kaggle dataset description: https://www.kaggle.com/competitions/rsna-knee-abnormality-detection/data
- RSNA challenge page: https://www.rsna.org/artificial-intelligence/ai-image-challenge/knee-mri-ai-challenge
- RSNA launch announcement: https://www.rsna.org/news/2026/august/ai-challenge-knee-mri

The public submission schema is:

`StudyInstanceUID, ACL, MCL, Medial Meniscus, Lateral Meniscus, Medial OA, Lateral OA, PF OA, Effusion, Synovitis, Baker's, Contusion, Fracture`

Kaggle evaluates the mean ROC AUC across those twelve targets. The required file name is `submission.csv`; competition notebook execution is offline and limited to nine hours for CPU or GPU notebooks. The public data page states that radiology-report text is available for training but **not** at test time.

## What is implemented

- exact 13-column submission contract validation;
- finite `[0,1]` confidence-score checks and duplicate-study rejection;
- pure-Python binary ROC AUC and twelve-target macro AUC;
- deterministic group-aware train/validation assignment helper;
- deterministic ZIP packaging for reproducible handoff artifacts;
- a command-line adapter with a synthetic-only smoke test;
- focused unit tests that require no competition data or third-party packages.

Run:

```bash
cd research/rsna-knee-abnormality-detection
python -m unittest -v
python notebook_adapter.py smoke
python -m py_compile rsna_knee_toolkit.py notebook_adapter.py
```

To validate a locally generated competition submission in an authenticated, rules-compliant environment:

```bash
python notebook_adapter.py validate /path/to/submission.csv
```

## Boundary

This is research/competition tooling, not a diagnostic or clinical-use system. No score, rank, entry, submission, award, or payment is claimed. Competition data should only be handled under the operative Kaggle/RSNA terms and stays outside Commons.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

