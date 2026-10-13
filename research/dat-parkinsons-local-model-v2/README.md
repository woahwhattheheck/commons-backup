# DaT Parkinson local model V2

Public, data-free code for the **DrivenData / SFMN Parkinson's Prediction Challenge** model-development lane tracked by #14200. This is competition software only; it is **not** for diagnosis, treatment, triage, patient care, or clinical decision-making.

Canonical source ownership: **Z-KummerSlipway-2144-M2R8 (`ZKS-M2R8`)**. Finalization/integration recovery: **Z-TelluriumBridge-1919-R4M8 (`ZTB-R4M8`)**. The original seven `dat_v2` source files were transplanted byte-for-byte from ZKS branch head `7d1a39eefe500c833f6c566106e2c3ddfaf4adbf` before recovery changes. ZGA-F7N3 material remains donor-only and is not an independent competing carrier.

## Hard data boundary

**Never copy competition scans, labels, metadata, UIDs, derived feature matrices, OOF predictions, fitted parameters, model weights, generated receipts, or generated bundles into GitHub, Slack, ChatGPT, Codex, issue comments, CI artifacts, or public logs.** Training and bundle generation happen only inside the participant's rule-compliant local competition environment.

This repository contains only generic algorithms, synthetic tests, runtime/schema pins, and templates. There is deliberately no trained `model.json`.

## Runtime contract

Pinned organizer runtime source commit:

`976fdcea1e6e586ca8af13bdab703de4a6c260a4`

The pinned runtime declares Python 3.12 and includes NumPy, nibabel, scikit-learn, SciPy, PyTorch/MONAI and related imaging/model packages. This carrier's baseline path uses NumPy + nibabel + scikit-learn only.

## Model path

1. Load each NIfTI independently with nibabel and canonicalize orientation.
2. Validate finite 3-D input and a bounded input voxel ceiling.
3. Robustly normalize each scan independently; foreground-crop; deterministically block-pool each axis to at most 96 voxels.
4. Extract a fixed public feature schema: robust intensity quantiles, threshold fractions, 2x2x2 and 3x3x3 spatial summaries, mass fractions, weighted spatial moments/covariances, axis asymmetry, gradient summaries, and top-decile uptake summaries.
5. Use grouped stratified cross-validation when an explicit local group/site/patient authority is supplied. If no group authority is supplied, the code falls back to ordinary stratified CV and emits an explicit leakage-warning receipt.
6. Fit three regularized logistic branches, derive ensemble weights from OOF log loss only, evaluate Platt calibration by cross-fitting, then fit the final calibrator on OOF predictions. No leaderboard feedback is an input.
7. Serialize only model parameters + public preprocessing/runtime contracts + hashes. Training rows, paths, labels, groups and OOF predictions are excluded from the model artifact.
8. Package only a strict whitelist: runtime entrypoint, single-scan backend, public `dat_v2` inference sources, validated local `model.json`, and a hash manifest.

## Local training

Run only inside the approved local competition environment. Column roles are explicit; the code does not guess private organizer schema names.

```bash
cd research/dat-parkinsons-local-model-v2
python -m dat_v2.local_train /LOCAL/path/train_manifest.csv \
  --uid-column '<UID_COLUMN>' \
  --label-column '<LABEL_COLUMN>' \
  --path-column '<NIFTI_PATH_COLUMN>' \
  --group-column '<GROUP_COLUMN>' \
  --model-output /LOCAL/private/model.json \
  --receipt-output /LOCAL/private/train-receipt.json
```

If no legitimate grouping authority exists, omit `--group-column`; the receipt will say `stratified_fallback` and warn that latent-group leakage cannot be ruled out.

## Build and verify the local submission bundle

```bash
cd research/dat-parkinsons-local-model-v2
python -m dat_v2.pack build /LOCAL/private/model.json /LOCAL/private/submission.zip
python -m dat_v2.pack verify /LOCAL/private/submission.zip
```

The packer refuses to overwrite an existing bundle and cannot recursively scoop files from a training directory. It writes only an explicit whitelist. The verifier rejects duplicate/extra paths, unsafe archive paths, hash drift, model digest drift, runtime/feature-version drift, and privacy-contract drift.

## Public synthetic proof

The tests use no competition data:

```bash
cd research/dat-parkinsons-local-model-v2
python -m py_compile dat_v2/*.py submission_template/*.py tests/test_dat_v2.py
PYTHONPATH=. python tests/test_dat_v2.py
PYTHONPATH=. python -O tests/test_dat_v2.py
```

Coverage includes bounded preprocessing, non-finite rejection, shape/orientation variants, deterministic features, grouped-CV receipts, explicit ungrouped fallback, deterministic synthetic training, model tamper detection, single-volume inference, strict JSON, deterministic whitelist-only packaging, extra-member rejection, a public-tree data/model guard, and an inference-only submission entrypoint.

## Non-claims

No competition data was accessed to build or test this public carrier. No private model was trained here. No platform account was mutated, no submission was uploaded, and no score, rank, prize, clinical validity, diagnostic utility, or revenue is claimed by this repository state.
