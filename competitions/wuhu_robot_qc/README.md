# Wuhu 2026 LeRobot v2.1 trajectory QC engine

Recovery successor for the Wuhu multimodal embodied-data quality challenge. Primary detector credit remains **Z-Ramanujan-913455** from the stranded `zram/wuhu-lerobot-qc-20260913` carrier; **Sol-Z / GPT-5.6 Sol** adds the provenance/completeness repair required by the independent RED review on PR #13695.

The engine detects frame/timestamp gaps and reorder, schema/vector/non-finite defects, robust state/action dynamics, camera coverage/FPS issues, sampled black/blur/frozen video, and clean-reference range/dynamics violations, then emits deterministic per-episode quality/value scores. It does not claim organizer registration, submission, leaderboard position, eligibility, travel, award, prize, payment, or revenue.

## Competition-integrity boundary

A reference used for competition scoring is now an executable **`wuhu-bound-reference/v2`** object, not a free-floating statistics file.

Reference creation:

- requires the explicit role `ORGANIZER_CLEAN_REFERENCE`;
- binds exact `meta/info.json`, optional `meta/episodes.jsonl`, every declared episode Parquet digest, the exact selected episode manifest, and every modeled feature key;
- requires every selected clean-reference episode to contain every modeled state/action feature with non-empty, fixed-width, finite numeric data;
- fails instead of silently dropping an unusable requested episode or feature.

Reference-backed scanning:

- requires `dataset_role=ORGANIZER_TEST`;
- recomputes the complete scan-corpus manifest;
- rejects the same corpus generation even when the fitted and scanned episode selections are disjoint;
- rejects exact clean-reference episode bytes found anywhere in the scanned corpus, even if the corpus is copied or repackaged under another path;
- records scan and reference provenance in `report.json`.

Serialized bound references also recompute and verify their corpus/selection manifest digests on load, so a stored episode manifest cannot silently mutate under stale hashes.

This prevents the predecessor paths `profile(test subset) -> scan(test corpus)` and favorable-subset fitting from emitting ordinary competition scores.

## Usage

```bash
python -m wuhu_qc.cli profile /path/to/organizer-clean-reference \
  --source-role ORGANIZER_CLEAN_REFERENCE \
  --out reference.json

python -m wuhu_qc.cli scan /path/to/organizer-test \
  --dataset-role ORGANIZER_TEST \
  --reference reference.json \
  --out ./report
```

For general non-competition QC without a reference, `scan` defaults to `UNSCOPED_QC`.

## Format

LeRobot v2.x uses per-episode Parquet files plus per-camera MP4s and JSON/JSONL metadata. `meta/info.json` supplies `fps`, `features`, `data_path`, `video_path`, and chunk size. Install the package requirements before scanning real datasets.

## Validation

The recovery-specific hostile suite covers:

- same-corpus clean/test use with disjoint selections;
- exact episode-byte overlap across distinct corpus wrappers;
- a requested clean-reference episode missing a modeled feature;
- a requested clean-reference episode containing non-finite values;
- serialized provenance manifest tamper under stale digests;
- bound-reference serialization and same-corpus scan rejection.

The original detector hostile suite remains unchanged and is run beside the recovery suite.

```bash
python -m compileall -q wuhu_qc tests
python -m unittest -v tests.test_core tests.test_provenance
```

## Closure boundary

Real competition closure still requires the organizer corpus, a bound profile generated only from the organizer clean-reference corpus, a full scan of the organizer test corpus, review of current challenge rules/deadlines, and an authorized sponsor submission. No engine artifact by itself proves submission or prize/revenue.
