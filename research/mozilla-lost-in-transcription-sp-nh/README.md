# Lost in Transcription — Spanish–Nahuatl offline baseline

This directory is a public, data-free submission-readiness scaffold for Mozilla Data Collective / DrivenData's Spanish–Nahuatl track. It deliberately contains **no competition audio, transcripts, speaker metadata, or model weights**.

## Pinned execution contract

Checked 2026-09-08 against `drivendataorg/lost-in-transcription-runtime` main commit `05b89385334512c8bff98f1bf35616df3ab0bca9`.

The official runtime contract used here is:

- Python 3.12 runtime.
- `submission.zip` must contain `main.py` at the archive root.
- Runtime input lives at `/code_execution/data`: `submission_format.csv` and `clips/`.
- `main.py` must write `/code_execution/submission/submission.csv`.
- Prediction rows are keyed by `audio_filename` with a `transcript` column.
- Execution has no general internet access, so model assets must be packaged into the submission.
- Official scoring is corpus word error rate after its published transcript normalization.

The official runtime currently includes PyTorch, Transformers, Qwen-ASR, torchaudio, librosa, soundfile, sentencepiece, pyctcdecode and KenLM among other packages. The baseline entrypoint uses only packages already in that runtime. `RUNTIME.lock` pins the exact runtime commit, tree, Python range, template blob, pyproject blob, and official `uv.lock` blob used for this scaffold.

## What is runnable now

`submission_src/main.py` is a valid offline execution skeleton. With no `submission_src/model/config.json`, it emits empty transcripts. That is intentionally a **plumbing baseline**, not a competitive ASR claim.

To turn it into an ASR candidate, vendor a compatible Hugging Face automatic-speech-recognition model under:

```
submission_src/model/
```

The entrypoint loads that directory with local-only settings and will not download weights at inference time.

Build a byte-stable ZIP:

```
python tools/build_submission.py --source submission_src --output submission.zip
```

Validate packaging:

```
python tools/validate_submission.py --zip submission.zip
```

Validate a produced CSV against the organizer's `submission_format.csv`:

```
python tools/validate_submission.py   --csv /path/to/submission.csv   --format /path/to/submission_format.csv
```

Create a deterministic, data-minimizing local train/validation manifest from an authorized CSV:

```
python tools/split_manifest.py /path/to/local_metadata.csv /path/to/split-manifest.json \
  --seed sol-nahuatl-v1 --validation-fraction 0.2
```

The manifest contains only `audio_filename`, split assignment, parameters, and the source CSV SHA-256; it never copies transcript text.

Run data-free tests:

```
python -m unittest discover -s tests -v
```

## Scoring compatibility

`tools/score_compat.py` is a stdlib reimplementation of the public score normalization plus corpus WER. It is intended for fast local checks without modifying or redistributing organizer data. For final verification, use the organizer's own `score.py` and Docker runtime at the exact runtime revision you plan to target.

The normalizer intentionally does **not** erase Nahuatl spelling distinctions, accents, apostrophes, or internal word structure beyond the organizer's published scoring cleanup. That matters because code-switched Spanish–Nahuatl WER is orthography-sensitive.

## Data and privacy boundary

Do not commit competition audio/transcripts here. Do not send challenge data to hosted model APIs. Keep speaker-identification and voice-cloning attempts out of this lane. If external training data or open-weight models are used, record their source, license, version, digest, and any disclosure/publication obligation required by the competition.

## Next measured step

On an authenticated competition/data surface:

1. Download the authorized Spanish–Nahuatl development bundle.
2. Record archive/file digests without copying protected payloads into Commons.
3. Run the organizer's minimal example once to pin runtime behavior.
4. Select an open-weight multilingual ASR checkpoint that can be legally redistributed in the submission and fits the runtime.
5. Fine-tune or decode locally/offline; record deterministic splits and seeds.
6. Compare held-out WER using organizer `score.py`.
7. Package the exact model assets plus this `main.py`, run the official Docker harness, and only then report a local measured WER.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

