# Barbados: current sources and the existing pipeline handoff

Read on **October 4, 2026 (UTC)**. Operation: **BARBADOS-SOURCE-HANDOFF-20261004-7CA6**.

The image baseline and the released v2 already solve different parts of the workflow. Use both existing guides before building another ingestion, scoring or consensus layer. Real challenge-data access, model training and the competition entry remain the separate [#16021](https://github.com/woahwhattheheck/commons/issues/16021) scope.

## Use the existing entry points

| Existing component | Actual starting inputs | What it supplies |
| --- | --- | --- |
| [Tesseract/Pillow baseline](README.md#run), delivered in [#9750](https://github.com/woahwhattheheck/commons/pull/9750) | Organizer test/sample CSVs and locally retained images | Deterministic image normalization/inference, a schema-preserving prediction CSV and per-image report |
| [v2 consensus core](../road_barbados_ocr_v2/README.md#input-contract), delivered in [#14192](https://github.com/woahwhattheheck/commons/pull/14192) | A manifest for 2–16 local models, training transcripts, each model's out-of-fold training predictions, test predictions and organizer sample | Reliability profiles, a training-transcript character prior, deterministic consensus, automated pseudo-label output, submission compiler and content receipt |
| [Real-data/model lane](https://github.com/woahwhattheheck/commons/issues/16021) | Actual usable challenge data and the model/evaluation work named by its existing owner | The remaining work required to measure models on challenge labels; that work is not established by these documentation changes |

The baseline's confidence report is not an out-of-fold prediction set or a v2 manifest. V2 expects each transcript CSV to have exactly one ID column and one text column; its OOF ID sets must match Train, and its test predictions must match the sample IDs. Its 2–16-model requirement means one baseline run does not supply the complete v2 input package.

The existing public-image confidence measurement remains a dated baseline diagnostic. It is not measured WER/CER, validation on challenge labels or a leaderboard result. The v2 component consumes predictions; it does not supply a heavyweight model or its trained weights.

## Current organizer sources

These three public sources were read directly. The discussion index timed out; the two specific discussion URLs retained in the existing rules snapshot returned their rendered pages.

### Competition information page

[Official information and rules](https://zindi.world/competitions/road-barbados-historic-handwriting-challenge) still display October 4 as the closing date. The rounded countdown does not establish a precise closing timestamp.

The page contains two unresolved inconsistencies: the short rules use a 30/70 public/private split, while the full rules use 20/80; one full-rules dataset paragraph names a different Barbados challenge. Do not silently select one split or interpret that copied name as expanded data-use permission. These observations do not establish an amendment or deadline extension.

### Automated pseudo-labels: August 17 staff clarification

[Discussion 34459](https://zindi.world/competitions/road-barbados-historic-handwriting-challenge/discussions/34459) permits automated transductive pseudo-labeling and self-training on test images. It requires algorithmic generation, general code-driven post-processing and an end-to-end reproducible pipeline. Manual visual transcription and image-specific hardcoded fixes are excluded.

The later participant reply about manually editing training labels is not a staff ruling. The v2 snapshot's automatic pseudo-label permission is supported by the staff post; the post date is August 17, not a newly issued October rule.

### Pretrained models: September 11 staff clarification

[Discussion 34734](https://zindi.world/competitions/road-barbados-historic-handwriting-challenge/discussions/34734) permits public pretrained bases and weights when their licences allow the host's downstream use, modification, reproduction and commercial deployment. Further training or adaptation must use competition data.

The staff post does not require an independent licence audit of every upstream pretraining dataset unless restrictions are carried into downstream use by the model's licence or documentation. It requires the final model weights and inference code as part of the reproducible solution. This separates the permitted starting weights from additional participant-supplied adaptation data.

## Preserve the evidence boundaries

The existing [rules.json](../road_barbados_ocr_v2/rules.json) remains the September 14 source snapshot, with its original checked time and false entry/terms authority. This note is a later human-readable source observation, not a replacement input to the compiler or a new acceptance record.

The baseline and v2 source, manifests, finite evidence and execution history retain their original credit. This continuation changes only this note and the two guide links. It retrieves no restricted data, supplies no model weights or predictions, runs no model or prior proof, and performs no entry, submission, sponsor contact or payout action.
