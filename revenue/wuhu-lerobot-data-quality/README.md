# Wuhu LeRobot V2.1 Data Quality Auditor

A read-only, deterministic baseline for the **2026 Yangtze River Delta (Wuhu) embodied-intelligence multimodal data-quality challenge** build order. It audits a local LeRobot **v2.1** dataset, localizes faults down to episode/frame/modality, and produces transparent data-quality and training-value scores.

The tool is intentionally an offline artifact. It does **not** register for, submit to, or claim qualification/prize/payment from the organizer.

## V2.1 contract used

The reader follows the LeRobot v2.1 layout documented by the upstream v2.1→v3.0 converter:

- `meta/info.json`
- `meta/episodes.jsonl`
- `data/chunk-*/episode_XXXXXX.parquet`
- `videos/chunk-*/CAMERA/episode_XXXXXX.mp4`

`meta/info.json` must advertise `codebase_version: "v2.1"`. The default challenge profile expects **three camera/image features** and **20-dimensional state/action vectors**; both are configurable CLI fences rather than hidden assumptions.

## What it checks

- **Structure and indexing:** required roots/files, version, duplicate/gapped episode indices, declared episode length versus loaded rows, camera-count mismatch and missing per-episode files.
- **Frame/timing:** missing or reordered frame indices, timestamp duplicates/reversals, frame-interval/FPS jitter and large time gaps.
- **Cross-modal synchronization:** camera start offset, duration drift and temporal overlap against the state/action timeline; decoded video frame count and container FPS against episode metadata.
- **Visual quality:** full-frame decode by default, corrupt frames/videos, black-frame luminance, and low-variation/low-edge occlusion heuristics. `--visual-sample-stride N` can deliberately trade coverage for speed and is recorded by the invocation, not silently inferred.
- **State/action integrity:** exact expected dimensionality, non-finite values and configurable absolute range fence.
- **Training value:** transparent dynamic-signal score based on the fraction of consecutive valid state/action transitions that actually change.

Heavy readers are loaded only for real dataset inspection: **PyArrow** reads parquet, while **PyAV + NumPy** decode video frames. If those capabilities are missing, the report receives explicit error faults (`parquet_unavailable` / `decoder_unavailable`) instead of silently presenting partial analysis as complete.

## Scoring

Every localized fault belongs to one of five categories: structure, timing, synchronization, visual, vectors. Each category starts at 100 and subtracts a fixed severity penalty:

- error: 12 points
- warning: 4 points
- info: 1 point

Category scores floor at zero. Overall quality is the fixed equal-weight mean of the five category scores. Training value is:

```text
0.75 * quality + 0.25 * dynamic_signal
```

The JSON report embeds these exact weights and penalties. It also records SHA-256 hashes for every metadata/data/video file the run actually inspected, so repeated reports can be bound to the same immutable input bytes.

## Install

Python 3.10+:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

## Audit

Keep output **outside** the dataset root. The CLI refuses an output directory below the input tree so the raw competition data stays immutable.

```bash
python -B lerobot_quality.py audit /data/wuhu-v21 \
  --out-dir /tmp/wuhu-quality-report \
  --expected-vector-dim 20 \
  --expected-cameras 3
```

Exit codes:

- `0`: audit completed with no error-severity faults;
- `1`: audit completed and localized one or more error-severity data faults;
- `2`: CLI/configuration/input failure prevented a complete audit.

Outputs are deterministic for the same input bytes and options:

- `report.json` — machine-readable scores, provenance and localized faults;
- `report.md` — human review summary and fault table;
- `report.html` — portable dependency-free HTML wrapper of the same report.

Every fault row carries `episode_index`, `frame_index` when available, `modality`, stable `code`, severity, reason and metric.

## Synthetic acceptance suite

The stdlib-only test suite does not need PyArrow/PyAV/NumPy. It injects each required fault class directly into the normalized scoring layer and proves replay stability:

```bash
python -B -m unittest -v test_lerobot_quality.py
python -O -B -m unittest -v test_lerobot_quality.py
python -m py_compile lerobot_quality.py test_lerobot_quality.py
```

Current fixtures cover:

- episode index gap/duplicate and wrong V2.1 schema version;
- frame loss, FPS jitter, timestamp reversal/duplicate and frame reordering;
- three-camera offset, drift and overlap faults;
- corrupt, black and occluded visual frames;
- malformed/non-finite/out-of-range 20D vectors;
- explicit missing decoder/parquet capability faults;
- byte-for-byte dataset immutability through a full mocked audit;
- stable JSON/report scoring on repeated identical evidence.

## Heuristic boundaries

Black/occlusion detection is intentionally explainable, not a learned vision classifier. Default thresholds are exposed as CLI flags and should be calibrated against organizer examples before a final submission. Likewise `--vector-abs-limit` is a generic gross-outlier safety fence; domain-specific joint/velocity/action ranges can tighten it without changing the audit format.

A competition-grade run should preserve the generated JSON plus the input provenance hashes, record the exact environment/dependency versions, and separately receipt organizer registration/submission. Do not relabel this code/test milestone as a submitted or prize-eligible entry without those external receipts.
