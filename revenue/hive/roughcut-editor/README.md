# Roughcut: reversible talking-head editing

A working local browser desk and command-line editor for Hive demand `bm-hive-20260908-008`.
Import a recording, bring its timed transcript, review silence and exact-repeat suggestions,
choose cuts, save revisions and render a real MP4 with synchronized captions and an editable timeline.
The original recording is retained byte-for-byte. Nothing is cut or published automatically.

## Start the desk

Requires Python 3.11+ and `ffmpeg` / `ffprobe` on PATH, including FFmpeg's `libx264`
encoder. There are no Python package dependencies for the application or core tests.

```sh
cd revenue/hive/roughcut-editor
python server.py --workspace /path/to/private/roughcut-workspace --port 8788
```

Open `http://127.0.0.1:8788`. This is a trusted-workstation, single-operator application,
not a hosted or isolated multi-tenant upload service. It has no account/login requirement.
Keep the loopback default and keep workspace files private. Running the server does not
publish a website or send media to another service. Rendering uses the machine running
FFmpeg; use an existing cloud workstation rather than the owner's PC for Commons work.

1. Import a video. MP4/H.264/AAC is recommended for browser playback. Other formats
   recognized by FFmpeg can be rendered, but their original preview also needs browser codec support.
2. Import basic SRT, WebVTT or JSON captions, or use manual cut ranges without a transcript.
   Transcript JSON is an array of `{"start": 0, "end": 2, "text": "Original words"}`;
   these times are seconds in the **original**, not the edited output. This tool does not transcribe speech.
3. Request suggestions. Silence detection defaults to -35 dB, 0.65 seconds and 0.15 seconds
   of retained padding at each boundary. Exact normalized repeated phrases with at least
   four words are suggestions, not an assertion that a take is unwanted. All suggestions start disabled.
4. Listen, enable intended cuts and save. Transcript-row cuts also start disabled.
   The source jump preview seeks over enabled intervals; it is approximate, not the final render.
5. Render the saved revision. Download the MP4 plus editable ZIP. Review partially cut
   caption wording before publication. No external platform upload happens.
6. Disable a cut and save to restore it. Earlier history can also be restored as a **new**
   revision; later revisions remain available. Download/edit/reload `project.json` for portable decisions.

## Source and timing contract

Edits use a constant 30 fps grid, independent of the original frame rate. `start` and `end`
inside project JSON are integer, half-open **frame** intervals. Imported seconds are rounded
to the nearest frame. Each output frame corresponds to exactly 1,600 samples at 48 kHz.
Cuts are combined as a union; disabling one overlapping cut does not restore frames still
covered by another enabled cut. The original file and all original caption cues remain intact.

Rendering selects the kept video frames and concatenates the corresponding audio sample
ranges. A common source origin preserves an audio stream that starts after the first video
frame. Output is re-encoded H.264/AAC, not a lossless copy; missing audio becomes silence.
Timestamp generation uses an integer video timebase and explicit constant-rate output.

Captions are intersected with kept intervals and moved to their output positions. A caption
crossing a cut is marked `review_required`: without word-level alignment the tool cannot
know which words were removed. Its full original text is retained for editing rather than
inventing replacement wording. This is not automatic editorial judgment or semantic retake detection.
Basic SRT/WebVTT timing and text are imported; rich VTT styling, karaoke and speaker-region
layout are not preserved. Caption markup is escaped in exported plain-text cues.

A source SHA-256 binds the timeline to its original. The desk never allows source metadata
to be edited. Source hashes are checked before analysis/rendering. SQLite stores optimistic
revisions; a stale save returns HTTP 409 rather than silently replacing another edit.
Every export gets a new directory; existing render targets are never replaced.

## Export files

`roughcut.mp4` is the actual rendered edit. `captions.srt` and `captions.vtt` are retimed.
`project.json` retains the original source descriptor, complete original cues and reversible
cut decisions. `timeline.json` contains exact source/output frame mapping, retimed cues and
review notes. `kept-intervals.csv` is the same mapping in frame units. `manifest.json` records
SHA-256 hashes, and `REVIEW.txt` explains remaining caption review. `editable-export.zip`
contains those files, not a duplicate of the original media. Keep the original alongside
your archive; a checksum detects byte changes but is not a signature or backup service.

To back up the whole workspace, stop the server and copy the entire workspace directory,
including `workspace.sqlite3`, `media/` and any wanted `exports/`. Do not copy only the DB
and then expect original files to be present. No scheduled/offsite backup is configured.

## Command line

```sh
python roughcut.py init recording.mp4 project.json
python roughcut.py analyze recording.mp4 project.json > suggestions.json
# Edit project.json: append selected suggestion objects to cuts and enable intended ones.
python roughcut.py export recording.mp4 project.json export-r1
```

`init` creates a new project file and does not overwrite an existing one. `analyze` prints
suggestions without changing the project. `export` requires a new output directory.
The same project JSON can be loaded into the browser editor for the exact original.

Python consumer example:

```python
from pathlib import Path
import roughcut

source = Path("recording.mp4")
project = roughcut.new_project(source, "Interview rough cut")
project["cuts"].append(roughcut.cut(10, 12, project["source"]["frames"], enabled=True))
roughcut.export_bundle(source, project, Path("export-r1"))
project["cuts"][0]["enabled"] = False  # Restore without modifying the original.
roughcut.export_bundle(source, project, Path("export-r2"))
```

## Validation and limits

```sh
python -B -m unittest -v test_roughcut
python -m py_compile roughcut.py server.py test_roughcut.py
```

The 25-method suite uses real FFmpeg, decoded audio samples, filesystem operations,
SQLite databases and HTTP requests. It exercises tone positions after cuts, delayed audio,
source preservation, restored duration and captions, no-audio sources, silence suggestions,
caption import/review, revision history, concurrent stale writes, raw upload, byte ranges,
real rendered ZIP delivery and failure preservation. Synthetic test media is generated
locally; no customer recording or permission is invented.

A separate development run exercised 10 Chromium DOM workflow checks through an explicit
Python-to-real-HTTP test binding, at 1440px and 390px without horizontal overflow or script
errors. Direct Chromium localhost navigation was blocked by the environment. This is not
claimed as native browser-network, media-playback or browser-download acceptance.
The HTTP suite independently transfers actual media and ZIP bytes.

Bounds: one hour, 2 GiB per browser upload, 4K pixel count, 128 cut decisions and 10,000
caption cues. Rendering/analysis is synchronous with a 10-minute subprocess timeout;
large inputs need adequate RAM, CPU and free space. Partial exports after process/host
failure are not a crash-atomic archive guarantee. Do not expect arbitrary broadcast
codecs, rotated-source display, multiple camera angles/audio tracks, HDR color management
or professional editing-suite interchange from this first version. The first video/audio
stream is used; verify those are the intended tracks. A natural-speech/customer acceptance
session, hosted deployment, sales and payment remain separate from this software delivery.

LARCH-CUT owns the independent companion at `../roughcut-media-checks/`; it is not a second
editor. Its keep intervals are seconds: convert this editor's `timeline["kept"]` rows using
`[[row["source_start"]/30, row["source_end"]/30], ...]`. No peer companion files are changed here.

Technical references: FFmpeg filter documentation for `silencedetect`, `fps`, `select`,
`settb`, `setpts`, `aresample`, `atrim` and `concat`: https://ffmpeg.org/ffmpeg-filters.html .
Media probing: https://ffmpeg.org/ffprobe.html .
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
