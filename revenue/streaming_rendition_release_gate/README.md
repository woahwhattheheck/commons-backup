# Streaming Rendition Release Gate

`paramount-streaming-rendition-release-gate-01`

A deterministic **metadata-only** preflight for streaming source/variant release packets. It reconciles expected rendition names, codec/profile declarations, segment continuity, caption/audio metadata, DRM **reference IDs**, artifact SHA-256 declarations, publication windows, and CDN region metadata.

The gate emits only:

- `RELEASE_READY` — the supplied metadata contract is internally consistent.
- `HOLD` — a stable reason code identifies the first fail-closed condition.

`RELEASE_READY` is not publication authority. Media operations retain every rights, content, release, scheduling, DRM-secret, transcoding, CDN, and publishing decision.

## Canonical acceptance fixture

`fixture.py` deterministically generates 168 synthetic asset packets:

- 140 clean packets -> `RELEASE_READY`
- 28 deliberately defective packets -> `HOLD`
- exactly four holds for each required failure class:
  - `MISSING_RENDITION`
  - `CODEC_PROFILE_MISMATCH`
  - `SEGMENT_DISCONTINUITY`
  - `CAPTION_AUDIO_ALIGNMENT_GAP`
  - `DRM_REFERENCE_MISMATCH`
  - `CHECKSUM_ORPHAN_ARTIFACT`
  - `PUBLICATION_WINDOW_CONFLICT`

The canonical generated fixture bytes and canonical projection are hash-bound in `manifest.json`. Re-running the same bytes produces the same result projection SHA-256.

## Run

```bash
python3 test_streaming_rendition_release_gate.py
python3 revenue/streaming_rendition_release_gate/validate_fixture.py --expect-ready 140 --expect-hold 28
```

## Fail-closed boundaries

Malformed schemas, unknown fields, bool-as-integer confusion, duplicate rendition/artifact identifiers, malformed timestamps, missing artifacts, checksum mismatch, orphan artifacts, CDN region drift, LIVE windows with an end time, and other metadata ambiguity return `HOLD`. The module has no network client and no function that publishes, transcodes, uploads, mutates a CDN, evaluates rights, or retrieves DRM secrets.
