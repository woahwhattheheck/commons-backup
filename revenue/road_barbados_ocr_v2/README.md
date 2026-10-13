# R.O.A.D. Barbados OCR v2 — consensus + automated pseudo-label core

This is an additive successor to the merged `revenue/road_barbados_ocr/**` Tesseract/Pillow baseline. It does **not** replace that image-ingestion carrier. It starts at the next expensive boundary: comparing multiple local OCR candidates without leaking test labels or external corpora, compiling a deterministic ensemble submission, and producing an automated pseudo-label set that can be consumed by a separately authorized local self-training loop.

## Current source and pipeline handoff

The [October 4 handoff](../road_barbados_ocr/SOURCE_HANDOFF_2026-10-04.md) connects the existing image baseline and v2 input contracts, dates the two directly read organizer clarifications, and identifies the unresolved public-rule inconsistencies. The dated rules.json and original real-data/model ownership are preserved.

## Current rules boundary

Public organizer pages were rechecked on 2026-09-13/14. The challenge advertises a $25,000 pool and closes October 4, 2026. Training/adaptation is limited to competition data; external training datasets are forbidden. Public pretrained bases are allowed only when their licenses let the challenge host use, modify, reproduce, and deploy the resulting solution, including commercially. Open-source tools are required and AutoML is forbidden. A later organizer clarification explicitly permits fully automated pseudo-labeling/self-training on test images; manual test labeling is not permitted. Top-10 solutions face rapid code review/reproducibility obligations.

`rules.json` is a source snapshot, not Zindi entry, terms acceptance, eligibility approval, or submission authority.

## What v2 does

* fail-closes model manifests unless every model is openly available, commercially usable by the host, adapted only with challenge data, and declares no hosted inference, external training data, or AutoML;
* computes a deterministic local mirror of length-weighted WER/CER using aggregate edit counts over reference words/characters;
* profiles model reliability from **out-of-fold training predictions only**;
* trains a tiny character n-gram prior from competition training transcripts only;
* chooses a transcript per test ID by reliability-weighted candidate medoid/support plus the train-only language prior;
* admits pseudo-labels only by deterministic inter-model support/agreement thresholds, never by manual test-label review;
* preserves the organizer sample CSV's header and row order exactly;
* emits SHA-256-bound profile, ensemble audit, pseudo-label artifact, build receipt, and offline receipt verifier.

It does not train or download a heavyweight OCR model, fetch the gated CSVs/images, call hosted APIs, send a Zindi submission, or claim a leaderboard score/rank/award/payment. Model weights, predictions, challenge labels, images, IDs, and generated submissions must stay outside Git.

## Input contract

`manifest.json` contains 2–16 local model declarations. Each model needs a stable ID, public base source/revision/license, a local weights SHA-256, and explicit false/no declarations for external data, hosted API use, and AutoML. The manifest authority block must remain all false.

`Train.csv`, each OOF CSV, each test-prediction CSV, and `SampleSubmission.csv` must contain exactly two columns: one case-insensitive `ID` column and one text column. OOF prediction ID sets must equal Train; all test model ID sets must match each other; final predictions must exactly match SampleSubmission IDs.

Example local invocation (paths are intentionally private):

```bash
python -m revenue.road_barbados_ocr_v2.cli build \
  --manifest /private/road/manifest.json \
  --train /private/road/Train.csv \
  --oof trocr=/private/road/oof-trocr.csv \
  --oof churro=/private/road/oof-churro.csv \
  --pred trocr=/private/road/test-trocr.csv \
  --pred churro=/private/road/test-churro.csv \
  --sample /private/road/SampleSubmission.csv \
  --out /private/road/v2-build
```

Then verify the content receipt offline:

```bash
python -m revenue.road_barbados_ocr_v2.cli verify \
  --receipt /private/road/v2-build/receipt.json \
  --sample /private/road/SampleSubmission.csv \
  --submission /private/road/v2-build/submission.csv
```

The build state is `LOCAL_BUILD_COMPLETE_NOT_SUBMITTED`. Pseudo-label output explicitly says it does not itself authorize self-training or submission; it is evidence for a local operator/runner under the competition rules.

## Reproducibility gate

```bash
python -m py_compile revenue/road_barbados_ocr_v2/*.py
python -m unittest revenue.road_barbados_ocr_v2.test_engine -v
python -O -m unittest revenue.road_barbados_ocr_v2.test_engine -v
python revenue/road_barbados_ocr_v2/package.py
```

The package builder emits a deterministic source ZIP plus an SBOM containing per-file SHA-256 digests. Its file list is explicit and excludes challenge images, labels, predictions, generated submissions and model weights. Content hashes are integrity evidence, not proof that a model license declaration or competition-data provenance claim is independently authentic; those declarations remain operator-supplied facts that must be checked before a real entry.
