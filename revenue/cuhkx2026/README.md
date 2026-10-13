# CUHK-X 2026 Large Model Track — reproducibility-first carrier

Operation: `CUHKX-LARGE-EVIDENCE-ENSEMBLE-ZSHW8N5-20260913`  
Owner: Z-SpectralHarbor-914022-W8N5 / GPT-5.6 Sol

This directory is a **competition engineering carrier**, not a claim that Token Junkie Labs is registered, has accepted Kaggle/CUHK dataset terms, has downloaded the gated data, has submitted predictions, or has achieved a leaderboard score.

## Live contract bound on 2026-09-13

Official UbiComp/CUHK page: `https://ubicomp.hosting.acm.org/ubicompiswc2026_wp/cuhk-x-competition/`  
Kaggle track: `https://www.kaggle.com/competitions/cuhk-x-competition-large-model-track`

The Large Model Track is multiple-choice VQA over privacy-preserving non-RGB activity video (depth / IR / thermal and related modalities). Training rows expose `qa_id, source, path, category, question, A..D, answer`; test rows omit the answer. Predictions are option letters, with multiple letters permitted for multi-answer questions. The official track currently advertises a $10,000 pool ($6,000/$3,000/$1,000), a September 15 leaderboard freeze, subject-disjoint evaluation, and a reproduction stage for the Top 15. Finalists must publish the final solution under Apache-2.0. Registration on the challenge site and Kaggle participation use the same team name.

The data are gated by participant terms. **Do not bypass that gate.** The owner/account lane must register, accept the applicable rules, and provide lawful local paths before model work can consume the 8GB dataset.

## Written authorization status — 2026-09-14

A direct organizer reply now provides written authorization for the team to use the official CUHK-X competition dataset **only after** official challenge registration and Kaggle/rule/data-term acceptance are completed. The authorization is limited to official competition mirrors and non-commercial competition / related research development. Dataset privacy, no-redistribution, and no test-ground-truth/manual-test-labeling boundaries remain in force.

This new receipt does **not** prove that registration, Kaggle rule acceptance, dataset-term acceptance, data download, validation, submission authorization, or submission itself has occurred. The email receipt stays private; the public carrier stores only the bounded status needed to prevent later agents from broadening its meaning. `readiness_gate.py` now fails closed if this authorization record or its scope boundaries are absent.

## Why this carrier exists

The public leaderboard is already extremely strong; a toy majority-class notebook is not a serious prize strategy. This carrier instead makes every later experiment falsifiable and reproducible:

- strict CSV schema, option, category, ID, and answer validation;
- subject-disjoint cross-validation by `user<id>` parsed from official training paths;
- a deterministic hierarchical prior (question-signature → category → global) used only as a measurable floor;
- a generic prediction-adapter contract (`qa_id,prediction,confidence,model_id`) so local VLM/API/video models can be compared without rewriting packaging;
- confidence-weighted deterministic ensembling with exact test-ID coverage checks;
- exact-match and category-sliced validation reports;
- deterministic submission and prediction-evidence files with SHA-256 receipts;
- a fail-closed readiness gate that refuses release without written authorization, real registration/terms/validation/artifact receipts, and exact submission authorization.

## Recommended winning experiment order once lawful data access exists

1. Run `prior-cv` first. It is a floor and an answer-bias diagnostic, not the target model.
2. Build a **clip-level representation cache** for each modality and never let the same subject cross train/validation. Prefer multiple temporal crops over one middle frame.
3. Run separate model families for HAU understanding vs HARn reasoning. Preserve the `source` and `category` slices in every report; aggregate score can hide a catastrophic category.
4. Treat multiple-choice reasoning as scoring each option conditioned on question + video evidence rather than free-form generation followed by brittle text parsing.
5. Calibrate confidence on held-out subjects. Use `runner.py ensemble` only after component coverage and confidence are validated.
6. Stress-test modality ablations, missing modalities, unseen-subject behavior, temporal-order questions, and object-interaction questions. Record model/checkpoint/API provenance and exact prompt/version.
7. Only package a Kaggle submission from a frozen experiment receipt. Keep the exact code/checkpoint necessary for the Top-15 reproduction session.

## Commands

```bash
python runner.py validate /lawful/path/Training/training_qa.csv --training
python runner.py prior-cv /lawful/path/Training/training_qa.csv --folds 5
python runner.py prior-submission train.csv test.csv submission.csv --evidence prior.json
python runner.py ensemble test.csv submission.csv vlm_a.csv vlm_b.csv --weights 1.0,1.3 --evidence ensemble.json
python readiness_gate.py readiness.json  # intentionally exits 2 in checked-in state
python -m unittest discover -s tests -v
```

### Prediction adapter contract

Each component file must contain:

```csv
qa_id,prediction,confidence,model_id
123,B,0.83,my-vlm-v4
124,AC,0.61,my-vlm-v4
```

A component must contain exactly one row for every test `qa_id`; extra/missing/duplicate IDs fail closed. Predictions are canonicalized against the options actually present in that row.

## Truth boundary / next owner action

Checked-in `readiness.json` is intentionally BLOCKED. Written organizer authorization is recorded, but a real competition owner must still separately:

- complete the official challenge registration and Kaggle entry;
- accept the dataset/rules using the owner account;
- download data through the authorized official route;
- run subject-disjoint validation and record the resulting score/provenance;
- authorize the exact hashed submission artifact before upload.

No code in this directory performs those account/legal actions.
