# QuantiPhy 2026 open-weight public-baseline carrier

Data-free tooling for the **QuantiPhy Challenge @ NeurIPS 2026**. This carrier does not register, submit, call a hosted model, access hidden labels, or claim a score. It turns locally produced organizer-shaped prediction CSVs into reproducible public-validation evidence and a deterministic competition-shaped ensemble CSV.

## Why this lane

The current competition website (observed 2026-09-13) says:

- final deadline: **2026-10-23 23:59 AoE**;
- public validation: 159 question/video pairs with released ground truth;
- test ground truth: withheld;
- Open-Weight inference: publicly available weights/tools only;
- metric: Mean Relative Accuracy (MRA), macro-averaged over S2/D2/S3/D3;
- awards per track: $1,000 / $500 / $250.

The `Paulineli/QuantiPhy` README still displayed a November 5 deadline when this carrier was built. Use the earlier/current competition-site date, not the stale repository date.

The organizer evaluator at `Paulineli/QuantiPhy:evaluator.py` transforms predictions with `abs(parsed_value)`, evaluates ten relative-error thresholds `{0.10,...,0.90,0.95}`, computes per-category MRA, then averages S2/D2/S3/D3 equally. `toolkit.py` mirrors that contract using only the Python standard library.

## Competitive starting point

`MirroS-Lab/Code-as-World` commit `1353bf07d24e5463caff92ce23ffd34d03984831` (Apache-2.0) documents local QuantiPhy inference for the public **Code-as-World-VL-4B** and **Code-as-World-VL-9B** checkpoints. Its README writes evaluator-compatible prediction CSVs and raw generations. That makes it a much stronger open-weight starting point than inventing a toy predictor here.

On an authorized CUDA host with Hugging Face access:

```bash
git clone https://github.com/MirroS-Lab/Code-as-World.git
cd Code-as-World
git checkout 1353bf07d24e5463caff92ce23ffd34d03984831
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/inference.txt
hf download MirroS-Lab/Code-as-World-VL-4B --local-dir weights/4b
hf download MirroS-Lab/Code-as-World-VL-9B --local-dir weights/9b
hf download PaulineLi/QuantiPhy-validation --repo-type dataset --local-dir /data/QuantiPhy-validation

git clone https://github.com/Paulineli/QuantiPhy.git /data/QuantiPhy
python -m code_as_world.evaluation 4b \
  --input-csv /data/QuantiPhy-validation/quantiphy_validation.csv \
  --video-dir /data/QuantiPhy-validation/validation_videos
python -m code_as_world.evaluation 9b \
  --input-csv /data/QuantiPhy-validation/quantiphy_validation.csv \
  --video-dir /data/QuantiPhy-validation/validation_videos
```

Do not report a benchmark score unless those commands (or another declared public-weight inference path) actually ran and raw predictions are retained.

## Exact public-validation workflow

From Commons root, validate and independently score each local model output:

```bash
python revenue/quantiphy_openweight/cli.py validate outputs/4b.csv --categories
python revenue/quantiphy_openweight/cli.py score \
  --ground-truth /data/QuantiPhy-validation/quantiphy_validation.csv \
  --prediction outputs/4b.csv
```

Select a model/ensemble using **category-stratified five-fold held-out public validation**. For each candidate (`model:i`, median, geometric mean, arithmetic mean), per-category multiplicative calibration is fitted only on the other four folds and evaluated on the held-out fold. The winner is then refit on all public validation rows and frozen as a recipe:

```bash
python revenue/quantiphy_openweight/cli.py select \
  --ground-truth /data/QuantiPhy-validation/quantiphy_validation.csv \
  --prediction code_world_4b=outputs/4b.csv \
  --prediction code_world_9b=outputs/9b.csv \
  --folds 5 \
  --recipe-out outputs/recipe.json
```

This does **not** prove hidden-test performance. It only reduces the easiest validation-label resubstitution failure: candidate choice is based on held-out folds rather than the full validation labels used to fit scale factors.

## Freeze and apply to test predictions

Run the same declared models on the public **test inputs** locally, without hidden ground truth. Preserve raw generations and model/environment receipts. Then apply the frozen validation recipe:

```bash
python revenue/quantiphy_openweight/cli.py ensemble \
  --recipe outputs/recipe.json \
  --prediction code_world_4b=test_outputs/4b.csv \
  --prediction code_world_9b=test_outputs/9b.csv \
  --output test_outputs/quantiphy_openweight.csv
```

The CLI writes `quantiphy_openweight.csv.manifest.json` with SHA-256 hashes of recipe, inputs, and output. It strips `ground_truth_posterior`/`mra` fields from the output and refuses zero/non-finite predictions by default because the organizer evaluator counts zero as invalid.

A platform upload remains a separate, explicit action. Before any submission, re-read the current competition rules, deadline, team/track state, daily submission limit, and exact reference template.

## Tests

```bash
python -m unittest -v test_quantiphy_openweight.py
python -m py_compile \
  revenue/quantiphy_openweight/toolkit.py \
  revenue/quantiphy_openweight/cli.py \
  test_quantiphy_openweight.py
```

Tests lock organizer-threshold semantics, absolute-value behavior, category macro-averaging, deterministic ensembling/packaging, held-out recipe selection, model-order binding, and ground-truth stripping.

## Boundaries

- Public code, public validation metadata/ground truth, and synthetic tests only in Commons.
- No hidden test labels or competition secrets.
- No hosted proprietary inference in the Open-Weight competition pipeline.
- No registration, terms acceptance, score, rank, award, or payment inferred from this source carrier.
- No spend or GPU run is claimed here.
