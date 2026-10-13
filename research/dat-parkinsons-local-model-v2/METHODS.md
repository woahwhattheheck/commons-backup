# Methods and leakage contract

## Scope

This document describes the public, data-free baseline implemented under issue #14200. It does not describe any private training set, participant-local fitted artifact, leaderboard result, or clinical claim.

## Preprocessing

A scan is loaded as one 3-D float32 NIfTI volume and canonicalized through nibabel. The feature path rejects non-3-D, non-finite, undersized, and over-ceiling inputs. Intensities are winsorized implicitly by the 1st/99th percentile transform and mapped to `[0, 1]` per scan. No cohort-level normalization is used.

The normalized volume is cropped to its obvious foreground and deterministically mean-pooled axis-by-axis to a maximum working axis of 96. This bounds the downstream feature working set. Spatial moments use 1-D and 2-D marginals instead of full coordinate meshgrids, preventing the multi-gigabyte transient allocation possible in the unfinished source branch.

`FEATURE_VERSION=dat-v2-features/v2` records the bounded preprocessing and corrected grid mass-fraction semantics. A v1 artifact is therefore not silently accepted by v2 inference.

## Fixed feature schema

The schema is deterministic and public. It includes robust intensity quantiles, mean/std, threshold exceedance fractions, 2x2x2 and 3x3x3 grid means and normalized mass fractions, weighted center/variance/covariance terms, mirrored half-volume asymmetry, gradient magnitude summaries, and top-decile uptake summaries. Feature names are unique and validated exactly before training/inference.

## Cross-validation

When an explicit local grouping authority is available, `StratifiedGroupKFold` is used. The code verifies that each validation row appears exactly once, train/validation row indices do not overlap, training folds retain both classes, and group identities do not cross train/validation within a fold.

If no group authority is supplied, `StratifiedKFold` is used and the receipt explicitly records `stratified_fallback` plus a warning that latent-group leakage cannot be ruled out. The code does not invent patient/site groups from UIDs or filenames.

## Ensemble and calibration

Three logistic branches are fit with fixed public hyperparameters. Each branch's OOF predictions are generated only by models that did not fit that validation row. Branch ensemble weights are deterministic functions of OOF log loss only; leaderboard feedback is not an input.

For evaluation, Platt calibration is cross-fit: each fold's validation probabilities are calibrated by a calibrator fitted on the other OOF rows. The reported calibrated OOF log loss therefore does not fit the calibrator on the row it evaluates. A final calibrator is fitted to all training OOF predictions for inference after model selection.

The final branch models are refit on all local training rows only after OOF selection. The serialized artifact contains standardization parameters, logistic coefficients/intercepts, ensemble weights, the final calibrator, fixed public schema/runtime identifiers, and a canonical SHA-256 digest. It excludes training rows, labels, UIDs, paths, groups/sites, and OOF predictions.

## Submission execution

The bundled `main.py` reads the organizer `submission_format.csv`, validates exactly `uid,is_pathologic`, resolves one NIfTI per UID, and calls `predict_probability(scan)` independently. The backend loads a validated local model once, loads only the current scan, extracts the fixed features, and emits one finite probability in `[0,1]`. There is no fit/retrain/adaptation API in the submission templates.

## Packaging

`dat_v2.pack` uses a fixed whitelist rather than recursively archiving a working directory. The archive contains only:

- `main.py`
- `model_backend.py`
- `model.json`
- the public inference-side `dat_v2` modules
- `bundle_manifest.json`

Every non-manifest member is SHA-256 listed. The verifier rejects duplicate or unexpected paths, traversal-like paths, hash drift, strict-JSON violations, model digest drift, runtime/feature-version drift, and a changed privacy contract.

## Reproducibility and limitations

Public CI exercises only synthetic arrays/features and generic code. It cannot establish competition quality, medical validity, or organizer acceptance. Participant-local training and official smoke/full-runtime execution remain necessary before any real submission. Generated models, receipts, scans, labels, metadata, derived features, bundles, scores and ranks remain private unless the competition rules and owner explicitly authorize otherwise.
