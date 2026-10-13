# Managed Clipping (Hive020)

A source-preserving batch clipping layer for managed video work. It does **not** fork the Hive008 rough-cut editor or Hive004 podcast workspace. Instead it consumes their published data shapes and owns the distinct work of choosing many moments, revising them independently, rendering them, and packaging a customer handoff.

## What it preserves

- Original source bytes are never modified. Every project stores filename, size, SHA-256, duration and video dimensions and refuses work if the source changes.
- Every clip keeps `source_filename`, `start_ms`, `end_ms`, editable caption text, hook text and normalized crop geometry.
- Edits increment `edit_revision`. Renders go into `rev-####/` directories and existing artifacts are never overwritten.
- Customer handoff exports latest playable MP4s, editable SRTs, `clips.csv`, full `project.json`, a hash manifest and a labeling README.

## Peer composition contracts

**CEDAR-TRACE008 rough-cut editor:** pass either `[[start_seconds,end_seconds], ...]` keep ranges or `timeline(project)['kept']` rows with `source_start` / `source_end` 30fps frame indexes through `--cedar-keeps-json`.

**KESTREL-DELTA004 podcast workspace:** pass a document containing chronological non-overlapping transcript segments shaped as `{id,start,end,speaker?,text,verified?}` through `--transcript-json`. The adapter accepts the direct document or a `{document:{...}}` envelope.

Neither peer directory is imported, edited, or duplicated.

## Selection

A supplied transcript produces one clip per chosen cue. Each cue is used at most once. The cue and its 150ms padding both stay inside the source and inside a single keep range; a midpoint inside the keep is not enough. If fewer cues fit than `--moments`, `init` exits nonzero and names the shortfall. It does not repeat cues and it does not fill the gap with generic footage.

With no transcript, clips are distinct non-overlapping windows inside the keep ranges, or inside the whole source when no keep is given. Ranges that are too short to hold that many windows are an error.

An explicitly empty keep selection (`[]`, `{"keep":[]}`, or `{"kept":[]}`, including a nested timeline) means no footage is eligible. `init` exits 2 without saving a project. Omit `--cedar-keeps-json` to allow the whole source. Supplied keep/transcript files containing JSON `null` are invalid; omitting an optional file is the way to leave that input unspecified.

`summary` reports `selection_mode` (`transcript` or `generic`) and `distinct_moments`.

## CLI

```bash
python managed_clipping.py init source.mp4 project.json \
  --transcript-json episode.json \
  --cedar-keeps-json keep.json \
  --moments 20

python managed_clipping.py edit project.json clip-007 \
  --start-ms 7120 --end-ms 12440 \
  --caption "Revised caption" --hook "New hook" \
  --crop 0.1,0.0,0.8,1.0

python managed_clipping.py render project.json renders/
python managed_clipping.py render project.json renders/ --clip clip-007
python managed_clipping.py handoff project.json customer-handoff/
python managed_clipping.py summary project.json
```

`ffmpeg` and `ffprobe` are required for media probing and rendering. Captions are delivered as editable SRT sidecars; caption text is not burned into the source or silently flattened.

Before creating a handoff directory, the command checks every enabled clip's retained render against its current source, boundaries, caption and crop. A stale or missing render returns exit 2 with the clip ID so it can be rerendered. Unchanged clips can retain renders from earlier project revisions; a hook-only edit does not require new media. Disabled clips are excluded from the video/caption handoff, and a project with no enabled clips produces an explicit error. The full editable project remains included in successful handoffs.

## Acceptance exercised by the test suite

The real-media acceptance test creates a clearly labeled synthetic 24-second A/V source, imports 20 KESTREL-shaped transcript moments and a CEDAR-shaped keep range, renders **20 distinct playable MP4 clips**, then changes clip 007 boundaries/caption/hook/crop and rerenders only that clip into a new revision. It reopens the saved project, verifies the original source SHA-256, confirms old renders were unchanged, and exports a 20-video/20-caption customer handoff with CSV + project + hash manifest.

Run:

```bash
python -m unittest -v test_managed_clipping.py
```

No external posting, customer media, transcription provider, account action, or paid infrastructure is used by the acceptance suite.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
