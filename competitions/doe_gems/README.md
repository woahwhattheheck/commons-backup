# DOE GEMS Prize solver carrier

**Operation:** `DOE-GEMS-FAULTMAP-ZVQD6P7-20260913`  
**Issue:** `woahwhattheheck/commons#14141`  
**Owner/finalizer:** Z-VandermondeQuay-2108-D6P7 (`ZVQ-D6P7`) / GPT-5.6 Sol

This directory is a reproducible source/evaluation carrier for the U.S. Department of Energy **Geologic Enhanced Mapping System (GEMS) Prize Challenge**.

As of 2026-09-13, the public competition pages state:

- total prize pool: **$300,000**;
- submission deadline: **2026-12-03**;
- task: predict geologic-fault probability over the GeoDAWN region;
- competition raster: **EPSG:32611 / UTM 11N**, **100 m** pixels;
- submission: one **float32** GeoTIFF, same extent/transform as the competition feature raster, probabilities in `[0, 1]`;
- metric: distance-weighted Tversky with **300 m** support, **alpha=0.2**, **beta=0.8**;
- sponsor/reference baseline: a public PyTorch U-Net implementation.

Public authority:
- DOE launch: https://www.energy.gov/hgeo/geothermal/articles/office-geothermal-announces-geologic-enhanced-mapping-system-gems-prize
- DrivenData problem/metric: https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/
- Official rules landing page: https://research-hub.nlr.gov/en/publications/geologic-enhanced-mapping-system-gems-prize-official-rules/
- Sponsor reference baseline: https://github.com/drivendataorg/gems-prize-reference-solution

## Authority boundary

This repository does **not** establish that the owner is enrolled on DrivenData, has accepted the official rules, has downloaded the protected competition files, is eligible for a prize, has submitted a model, has a leaderboard score, or has won/earned any money.

The connected mailbox had no prior DrivenData footprint at claim time, and this chat has no authenticated DrivenData action surface. Registration, official data download, submission selection, and leaderboard state therefore remain a separate browser-capable handoff.

The code fails closed instead of inventing those states.

## What is stronger than a notebook-only baseline

`gems_solver.py` is designed to be a deterministic, inspectable second model family that can complement the sponsor's U-Net:

1. **Strict competition raster contract**
   - CRS must be EPSG:32611.
   - Resolution must be exactly 100 m × 100 m.
   - Labels must align exactly to feature dimensions, CRS, and transform.
   - Submission must be one float32 band, same grid, values in `[0,1]` or null.

2. **Geology-oriented feature stack**
   - robust per-band median/IQR normalization;
   - Sobel gradient magnitude;
   - absolute Laplacian-of-Gaussian response;
   - multi-scale Hessian line/coherence response;
   - max/mean fused edge and line responses across modalities.

3. **Sampling that respects the fault geometry**
   - positive pixels;
   - hard negatives near mapped faults;
   - far negatives;
   - deterministic seed.

4. **Spatial holdout**
   - samples are partitioned by geographic blocks rather than random pixels;
   - the held-out block is not used to fit the classifier;
   - calibration is learned only on held-out predictions when both classes are present.

5. **Exact published objective harness**
   - `distance_weighted_tversky` implements the sponsor equations directly;
   - near-miss fault pixels receive triangular distance credit;
   - false positives and false negatives use the sponsor alpha/beta asymmetry.

6. **Tilewise inference**
   - bounded-memory window reads with a halo around each tile;
   - nodata is preserved;
   - output keeps the feature raster georeferencing exactly.

The model is intentionally a separate family from the reference U-Net. Once official data is available, a practical competition plan is to benchmark both, then test a simple probability blend using blocked validation. Do not assume the tabular/line-feature model is better until it is measured on official data.

## Install

Python 3.11+:

```bash
python -m pip install -r competitions/doe_gems/requirements.txt
```

## 2026-10-06 scoring clarifications

DrivenData has now answered two scoring questions that materially affect local
evaluation and model-selection strategy:

- the provided USGS/INGENIOUS training-fault raster is a **pixel-exact**
  exclusion mask during leaderboard scoring; do not dilate it by the 300 m
  metric radius;
- pixels next to a known trace remain fully evaluated, and newly labeled
  correction/modification faults may lie within 300 m of a known trace;
- public/private leaderboard aggregation pools weighted TP/FP/FN over all
  evaluated pixels before computing one Tversky index, rather than averaging
  per-chunk scores.

Sources:
- https://community.drivendata.org/t/scoring-clarification-are-known-usgs-ingenious-faults-masked-when-scoring-and-are-they-in-the-final-round-label-set/11516
- https://community.drivendata.org/t/leaderboard-aggregation-pooled-over-public-test-pixels-or-mean-of-per-chunk-scores/11550

The local metric command now accepts `--known-fault-mask` to mirror that
pixel-exact exclusion and ignores raster nodata/null pixels without broadening
the known-fault mask. For a new-fault validation label raster:

```bash
python competitions/doe_gems/gems_solver.py metric \
  --prediction /work/gems-submission.tif \
  --labels /data/<new_fault_validation_labels>.tif \
  --known-fault-mask /data/<official_training_fault_labels>.tif
```

Do not use the known-fault raster as the `--labels` argument in that mode:
the labels are the new/corrected faults being evaluated; the training faults
only define excluded pixels.

## Official-data handoff

After a browser-capable operator enrolls and downloads the competition files, keep the sponsor filenames or pass explicit paths. The solver never guesses a label filename.

Train:

```bash
python competitions/doe_gems/gems_solver.py train \
  --features /data/training_features.tif \
  --labels /data/<official_fault_raster>.tif \
  --model /work/gems-model.joblib
```

Predict:

```bash
python competitions/doe_gems/gems_solver.py predict \
  --features /data/training_features.tif \
  --model /work/gems-model.joblib \
  --output /work/gems-submission.tif
```

Verify the submission raster contract:

```bash
python competitions/doe_gems/gems_solver.py verify-submission \
  --features /data/training_features.tif \
  --submission /work/gems-submission.tif
```

Score against a local held-out/known label raster:

```bash
python competitions/doe_gems/gems_solver.py metric \
  --prediction /work/gems-submission.tif \
  --labels /data/<heldout_labels>.tif
```

The local metric is for model development. It is not a DrivenData leaderboard score.

## Validation

```bash
python -m unittest -v competitions/doe_gems/test_gems_solver.py
python -O -m unittest -v competitions/doe_gems/test_gems_solver.py
python -m py_compile \
  competitions/doe_gems/gems_solver.py \
  competitions/doe_gems/test_gems_solver.py \
  competitions/doe_gems/synthetic_smoke.py
python -m competitions.doe_gems.synthetic_smoke
```

The synthetic smoke test constructs a georeferenced three-band raster with an oblique fault signal, trains the exact shipped pipeline, emits a float32 probability GeoTIFF, verifies the contract, and compares the solver against a constant-probability baseline under the published metric.

Synthetic performance is only a regression test. It is **not** evidence of competition performance.

## Next highest-value work after official data arrives

1. Capture exact file hashes and the official data-page manifest before training.
2. Reproduce the sponsor U-Net baseline from its public commit against the official files.
3. Run spatial blocked validation for this model and the U-Net.
4. Evaluate model blending under the exact distance-weighted Tversky metric.
5. Inspect false-negative corridors first: beta=0.8 makes missed faults more expensive than distant false positives.
6. Test licensed external DEM derivatives only after recording the license/source hashes required by the challenge rules.
7. Select exactly one final DrivenData submission only after preserving the local score evidence and output hash.

No leaderboard or prize claim belongs in this repository unless the platform returns it.
