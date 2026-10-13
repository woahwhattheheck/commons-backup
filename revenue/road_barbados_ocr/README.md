# R.O.A.D. Barbados OCR baseline

`baseline.py` is a deterministic, offline submission generator for the
[R.O.A.D. Barbados Historic Handwriting Challenge](https://zindi.world/competitions/road-barbados-historic-handwriting-challenge).
It uses the open-source Tesseract engine and Pillow, selects the strongest of
three line-layout interpretations by length-weighted OCR confidence, preserves
the organizer's submission schema and emits a per-image JSON receipt.

## Current operator handoff

The [October 4 source and pipeline handoff](SOURCE_HANDOFF_2026-10-04.md) links this image baseline to the already-shipped [v2 consensus core](../road_barbados_ocr_v2/README.md) and its separate input requirements. It also records the current organizer clarification sources and the unresolved inconsistencies in the public rules. The real challenge-data/model work retains its existing owner in [#16021](https://github.com/woahwhattheheck/commons/issues/16021).

## Truthful state

- The official page was read on 2026-09-07. It lists an October 4, 2026 close,
  weighted WER/CER scoring, five submissions per day, 200 overall, and open
  participation. Open-source tools and the supplied challenge dataset are
  allowed; publicly available pretrained models are allowed; AutoML and paid
  tools/trials requiring a card are prohibited.
- The public image archive was downloaded only to ephemeral competition work
  storage. It is 442,081,009 bytes and contains 5,472 JPG images. No challenge
  image or label is committed here.
- `Train.csv`, `Test.csv`, `SampleSubmission.csv`, and the starter archive are
  gated behind a joined, authenticated Zindi account. This build does not
  claim a Zindi entry, submission, score, rank, award, or payment.
- This is a reproducible baseline, not a claim that generic Tesseract will beat
  a handwriting-specialized model. Its purpose is to close the ingestion,
  image-normalization, deterministic inference, schema, and receipt path so
  later work can measure model improvements instead of rebuilding plumbing.

The checked-in public-image benchmark used 24 images from the organizer's
public archive, but commits no images, identifiers, OCR text, labels, or other
challenge data. With Tesseract 5.3.4, Pillow 12.3.0, and the default three PSM
candidates, the run completed in 21.438 seconds with 24/24 non-empty outputs.
The mean selected Tesseract confidence was 26.918341. That low confidence is a
useful baseline diagnostic, not accuracy, WER/CER, or leaderboard evidence.
See `PUBLIC_IMAGE_BENCHMARK.json`.

## Run

Keep all organizer data outside Git. Extract the public `images.zip`, then run:

```bash
python3 revenue/road_barbados_ocr/baseline.py \
  --test-csv /private/road/Test.csv \
  --sample-submission /private/road/SampleSubmission.csv \
  --images-dir /private/road/images \
  --output /private/road/submission.csv \
  --report /private/road/baseline-report.json
```

Requirements: Python 3.11+, Pillow and the `tesseract` executable with English
language data. The script fails on duplicate/mismatched IDs, unresolved or
unsafe image paths, ambiguous output schemas, OCR process errors, and empty
predictions. `--allow-empty` is explicit for diagnostics only. `--limit N`
creates a benchmark/debug subset and must not be treated as a full submission.

The default page-segmentation modes are `6,7,13`. Override with `--psms 7` for
a faster single-line pass. The output keeps the sample CSV's exact column names
and row order.

## Tests

```bash
python3 -m unittest discover -s revenue/road_barbados_ocr -p 'test_*.py' -v
python3 -m py_compile revenue/road_barbados_ocr/baseline.py
```

The suite includes a real Tesseract invocation on a generated line image. It
also checks schema preservation, ID-set equality, traversal rejection, image
resolution and confidence parsing without using any challenge data.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
