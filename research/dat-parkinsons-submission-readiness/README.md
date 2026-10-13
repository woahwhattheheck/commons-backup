# DaT Parkinson’s Challenge — data-free submission readiness

Operation: `sol-canary-dat-parkinsons-readiness-20260908-01`

This is a **public, data-free** contract and packaging kit for the DrivenData DaT Parkinson’s Challenge. It contains no competition scans, labels, metadata, derived features, model weights, credentials, submissions, or scores. Competition data must remain local to an eligible participant environment and must not be uploaded to ChatGPT/Codex or other services that retain it.

## Pinned live contract (verified 2026-09-08)

- Competition end: `2026-09-16T23:59:00Z`.
- Awards: €12,500 / €7,500 / €5,000.
- Metric: log loss, so output calibrated probabilities rather than hard labels.
- Submission: ZIP with `main.py` at archive root.
- Runtime: Python 3.12, offline, no root; A100 80 GiB, 24 vCPU, 220 GB RAM; 3 h full / 6 min smoke.
- Input: read-only `/code_execution/data/niftis/<uid>.nii.gz` and `/code_execution/data/submission_format.csv`.
- Output: `/code_execution/submission.csv` with exactly `uid,is_pathologic`; probability must be finite and within `[0,1]`.
- Test cases must be processed independently; no test-set pseudo-labeling, cross-case feature fitting, or retraining.
- Winner solution license: MIT. Prize-eligible external data/models must support broad use including commercial use; all external data used must be disclosed to organizers.
- Official runtime: `drivendataorg/competition-sfmn-parkinsons-runtime` commit `976fdcea1e6e586ca8af13bdab703de4a6c260a4`.
- Runtime dependency blob: `runtime/pyproject.toml` = `dd795535a5edaa73b514d07c7f8eaa5717a094ed`.
- Organizer template blob: `examples/template/main.py` = `f495ac6f0cbf99db9b650eb9ba0d90fb64a35cfc`.

## What is implemented

- `dat_readiness/contract.py`: strict manifest/output parsing, finite-probability checks, and a structurally independent per-file runner that gives the predictor only one scan path at a time.
- `dat_readiness/package.py`: deterministic ZIP creation, root-`main.py` validation, symlink rejection, and a guard that refuses obvious competition-data artifacts (`*.nii`, `*.nii.gz`, `submission_format.csv`, generated `submission.csv`).
- `dat_readiness/assets.py`: machine-readable external-asset manifest validation requiring explicit commercial-use and submission-redistribution confirmations. It is a provenance gate, not legal advice or a license parser.
- `submission_src/main.py`: model-agnostic entrypoint template wired to the official paths. Replace only `model_backend.predict_probability` with an eligible local model implementation.
- `submission_src/model_backend.py`: deliberate fail-closed placeholder; it does not download or fabricate a model.
- `pack_submission.py`: deterministic pack/check CLI.
- `tests/test_readiness.py`: synthetic contract regressions only. No real medical images are used.
- `runtime_lock.json` and `METHODS.md`: exact public-source pins and a local-only workflow.

## Local checks

```sh
python3 -m unittest discover -s research/dat-parkinsons-submission-readiness/tests -v
python3 -m py_compile research/dat-parkinsons-submission-readiness/dat_readiness/*.py \
  research/dat-parkinsons-submission-readiness/submission_src/*.py \
  research/dat-parkinsons-submission-readiness/pack_submission.py
```

The template intentionally cannot produce medical predictions until an eligible, locally developed model backend is supplied. No diagnostic-performance claim is made here.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

