# Podcast Content Desk

A runnable, single-workspace production app for turning an authorized recording and its supplied transcript into editable show notes, a newsletter, and five source-distinct post drafts. Hive demand `bm-hive-20260908-004`; canonical implementation by **KESTREL-DELTA**.

## Start

Python 3.10 or later, with SQLite support. The runtime uses only the standard library.

```sh
cd revenue/hive/podcast-content-workspace
python app.py
```

Open `http://127.0.0.1:8786`. The database defaults to `data/workspace.sqlite3`; set `--db PATH`, `--host ADDRESS`, or `--port NUMBER` as needed. This is one shared workspace without user accounts, not a public multi-tenant service. Do not put customer recordings on an unrestricted public endpoint; use the deployment's existing access boundary. No external requests, transcription services, email sends, social publishing, or provider-account operations occur.

## Complete a delivery

Create an episode. Import a timestamped transcript JSON file or enter segments manually. Attach the original recording and set its duration in seconds. Supported containers are WAV, MP3, M4A, OGG, FLAC, MP4 and WEBM, limited to 64 MiB; actual playback depends on the browser's codec support. Stored media bytes are not transcoded or modified.

Edit text, speaker labels and timing while playing the recording. Segments must be chronological and nonoverlapping. Add chapter titles and timestamps. A reviewed checkbox records an operator's review, not automatic audio verification. Editing segment text, timing or speaker in the editor clears its reviewed state.

Save the source, then generate. Five distinct post drafts require at least five transcript segments. The generator divides the source into five disjoint chronological groups; it does not duplicate one passage to claim five different posts. Drafts are intentionally extractive: no invented paraphrases, speakers, names or quotations. Add your introduction, context, links and platform-specific editing in the seven Markdown editors.

Save and export the complete folder. The ZIP contains `episode.json`, exact source `transcript.json`, captions in VTT/SRT, `chapters.csv`, editable `show-notes.md`, `newsletter.md`, five `posts/post-XX.md` files, `source-map.json`, and the attached original in `source-media/`. Timestamp links point back to that original. Markdown presentation escapes source markup, and spreadsheet-like chapter titles are display-escaped in CSV; exact source text remains in JSON.

Source corrections preserve existing draft edits and mark them stale. Explicit replacement requires confirmation. Stale exports remain possible and include warnings and source hashes. The source-map's **current source groups** describe the current transcript, not a verification of subsequently edited drafts. Editing or deleting in competing tabs uses revision checks; a stale writer receives HTTP 409 rather than silently overwriting another edit.

## Transcript format

```json
{
  "title": "Episode title",
  "duration": 180,
  "description": "A short description",
  "synthetic_demo": false,
  "segments": [
    {"id":"s1","start":0,"end":15,"speaker":"Host","text":"Exact source text.","verified":false}
  ],
  "chapters": [{"start":0,"title":"Introduction"}]
}
```

This small schema example has only one segment and therefore cannot generate five posts. Import accepts this document or an exported `episode.json` containing it. Import replaces source fields, not the saved recording or draft edits. The runtime does not infer transcript timestamps from audio. Supply an authorized transcript and check it against the recording.

## Original synthetic demo

`make_demo.py` contains an original six-part script and generates an approximately 85-second synthetic voice recording with frame-derived segment timestamps. It requires the optional `espeak` or `espeak-ng` executable. The app does not require that executable.

```sh
python make_demo.py --output data/demo
python app.py --import-document data/demo/transcript.json --media data/demo/source-first-demo.wav
python app.py
```

Open the imported episode and generate its working package. The sample explicitly identifies itself as original synthetic material, not a customer recording, real speaker interview, verified transcription or customer fulfillment. Exact duration can vary with the installed speech engine; timestamps are measured from its actual WAV frames.

## Validation and operation

```sh
python -m unittest -v test_app
```

Thirty real SQLite, concurrency, HTTP, media-range and ZIP tests pass in the development cloud container. There are no test skips or external account calls. The tests exercise Unicode, invalid JSON/timestamps, optimistic conflicts, stale-source preservation, original-byte exports, captions and deletion. Deletion removes records from the application; it is not a claim of secure physical erasure from SQLite, backups, browser caches or earlier exported files.

An optional real-browser workflow script is supplied for an environment with Playwright and an allowed Chromium installation:

```sh
python browser_check.py --document data/demo/transcript.json --media data/demo/source-first-demo.wav --output data/browser-check
# To use an already installed Chromium:
python browser_check.py --browser /path/to/chromium --document data/demo/transcript.json --media data/demo/source-first-demo.wav --output data/browser-check
```

**Browser validation boundary:** development Chromium returned `ERR_BLOCKED_BY_ADMINISTRATOR` on localhost navigation. The full browser script has therefore NOT passed here. Separate offline, network-disabled DOM rendering checks passed at 1440px and 390px, including draft tabs, source-review invalidation and no horizontal overflow. Those rendering checks are not substitutes for a browser/HTTP end-to-end receipt. The actual HTTP tests passed separately.

Before deploying customer work, exercise that complete browser workflow in the intended environment, use an appropriate shared-workspace access boundary, and keep the SQLite database/WAL/SHM files together when making a stopped-service backup. Keep runtime data and recordings out of source control. Export a working folder before deleting an episode or moving the workspace.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
