# Caption transcript intake

Turn supplied SRT or WebVTT captions into an editable, source-preserving transcript handoff. Python 3.10 or newer is required. No network service, model, or provider account is used by the converter.

For browser-based batch intake, run `python workbench.py` and open the printed local address. The [workbench guide](WORKBENCH.md) covers multiple files, per-file options, source-linked previews, individual or batch ZIP downloads, and reopening those saved handoffs with their original caption bytes and retained options. The browser companion reuses `caption_intake.py`; it does not replace the podcast workspace or transcribe recordings.

## Command-line use

From this directory:

```sh
python caption_intake.py examples/demo.vtt \
  --title "Clear project handoffs — fictional interview" \
  --output demo-handoff.zip
python -m zipfile -e demo-handoff.zip demo-handoff
```

Use a new output name for another run; the converter never replaces an existing destination. For a legacy SRT file, provide its known encoding rather than guessing:

```sh
python caption_intake.py captions.srt --encoding cp1252 \
  --speaker "Narrator supplied by the editor" \
  --title "Episode title" --output episode-handoff.zip
```

`--format srt` or `--format vtt` overrides the filename extension. The output parent directory must already exist. Success prints a JSON result and exits 0; invalid input or publication failure prints a diagnostic to stderr and exits 2. Neither command changes the input file.

## What the ZIP contains

`source.srt` or `source.vtt` is the byte-for-byte original, including its encoding, byte-order mark, and original line endings. `transcript.json` contains editable transcript segments and source provenance. `manifest.json` records both files' byte counts and SHA-256 hashes. Extract the ZIP, edit a copy of the transcript, and retain the source and original manifest for comparison; editing does not update the original manifest automatically.

A segment has this shape:

```json
{"id":"c00001","start_ms":0,"end_ms":7250,"speaker":"Morgan","text":"How do you keep a small project handoff understandable?"}
```

The document has `schema: "caption-intake/v1"`, `title`, `segments`, and `provenance`. Provenance includes the source hash/size/encoding, original cue identifiers, timing lines, cue settings, raw cue payloads, source line numbers, and retained header/NOTE/STYLE/REGION blocks. Normalized IDs are generated independently of source IDs. `media_verified` is always false: this program does not listen to or transcribe recordings.

The `speaker` field uses one explicit WebVTT voice annotation wrapping the entire cue, or the caller's `--speaker` label. The default `Unspecified` label is not a speaker identification. SRT dialogue prefixes and names in ordinary text are not interpreted as identities. No inference, summary, rewriting, or quote verification occurs.

## Supported input and limits

WebVTT timings support `MM:SS.mmm` and `HH:MM:SS.mmm`; SRT timings require `HH:MM:SS,mmm`. Timings become integers without a floating-point round trip. Cues remain in source order; equal starts and overlaps are preserved, while backwards starts, nonpositive durations, missing separators, and duplicate nonempty source IDs receive diagnostics. Hours accept two through nine digits. Inputs are limited to 2,000,000 bytes and 10,000 cues.

WebVTT uses UTF-8, optionally with a byte-order mark. SRT defaults to UTF-8 and permits an explicit Python text-codec override. CRLF and CR are normalized only in the editable view, never in the original source copy. The supported syntax is based on the [W3C WebVTT draft, sections 4.1–4.2](https://www.w3.org/TR/2026/CRD-webvtt1-20260520/) and the [Library of Congress SubRip format description](https://www.loc.gov/preservation/digital/formats/fdd/fdd000569.shtml); this converter is not a full rendering engine or conformance validator.

Plain text, character references, balanced bold/italic/underline spans, and WebVTT class spans are supported. Styling is omitted from plain text but preserved in source provenance. A single outer WebVTT voice span may omit its closing tag. Multi-voice cues, partial-voice attribution, ruby, language spans, inline karaoke timestamps, unsupported markup, and SRT positioning extensions require an explicit source edit or another converter; they are not silently discarded. Escape literal less-than signs as `&lt;`. `X-TIMESTAMP-MAP` headers are rejected because applying them requires knowledge of the recording timeline. STYLE/REGION blocks must precede cues. Cue setting strings are retained but not interpreted or comprehensively validated.

## Publication and preservation

The complete deterministic ZIP is built before publication. A private temporary file in the destination directory is flushed and then hard-linked exclusively to the requested path. A retry, existing file, symlink, directory, or concurrent winner cannot be overwritten. Filesystems must support same-filesystem hard links. No fallback replaces the target. This is a local-file operation, not an upload, deployment, or scheduled job. A process crash can leave a private staging file; this is not a claim of power-loss durability or directory fsync.

## Podcast workspace integration

Use `parse_captions(source_bytes, fmt="vtt", title="...")` to consume the normalized document in Python, or extract `transcript.json` from the bundle. Import only `segments` and metadata your receiving application actually supports. Milliseconds must not be passed into a seconds-based field without conversion. The converter does not write to another application or database.

For the canonical Hive004 podcast runtime, add the recording duration supplied by the editor. Do not infer it from the final caption timestamp. This example explicitly uses a fictional 65-second duration:

```sh
python caption_intake.py examples/demo.vtt --title "Fictional handoff interview" \
  --duration-seconds 65 --synthetic-demo --output demo-episode-handoff.zip
```

The ZIP additionally contains `episode-import.json`: `{title,duration,description,synthetic_demo,segments,chapters:[]}`. Its segment fields are `{id,start,end,speaker,text,verified:false}` in seconds. The original millisecond fields, caption settings and source bytes remain in `transcript.json` and the source copy. Duration must be positive, finite and at most 86,400 seconds. The canonical runtime requires nonoverlapping segments entirely within that duration. The adapter reports overlap or an out-of-range cue without shifting, trimming or discarding anything. Run without `--duration-seconds` for the generic, overlap-preserving bundle instead. Fewer than five cues may be imported but are insufficient for that runtime's draft-generation workflow.

The optional adapter also checks the canonical document limits: title at most 200 characters, speaker at most 120, cue text at most 12,000, and at most 2,000 segments. It reports incompatible inputs instead of truncating, splitting, or guessing. Those limits do not narrow the generic transcript format: omit `--duration-seconds` to preserve a larger generic caption handoff.

The canonical runtime remains under `../podcast-content-workspace/`. To import the generated document into a selected local workspace, extract the bundle and run its CLI from this directory:

```sh
python -m zipfile -e demo-episode-handoff.zip demo-episode-handoff
python ../podcast-content-workspace/app.py \
  --db demo-episode-handoff/workspace.sqlite3 \
  --import-document demo-episode-handoff/episode-import.json
python ../podcast-content-workspace/app.py \
  --db demo-episode-handoff/workspace.sqlite3
```

The import command creates a new episode; rerunning it creates another episode rather than updating the first. The server command opens that same local database. Attach the corresponding authorized recording in the workspace before reviewing names or quotes; fictional captions alone are not a verified recording. Retain the original caption handoff beside the content export: the workspace imports the normalized document, not every caption-provenance field.

An existing local HTTP client may POST the unmodified `episode-import.json` bytes to `/api/episodes`. The canonical HTTP body limit is 2 MiB. A valid document can exceed that after JSON escaping; use the CLI import above rather than dropping text or changing the runtime limit. The converter itself sends no requests. Python callers pass recording duration as a decimal string: `canonical_episode(parsed, "65", synthetic_demo=True)`.

## Managed-clipping integration

The same `episode-import.json` is accepted by `../managed-clipping/managed_clipping.py` through `--transcript-json`. The caption companion does not edit, fork, or import the managed-clipping package.

The bundled fictional demo has six caption segments. Request six moments or fewer after confirming that the source duration and any supplied keep ranges admit those cues:

```sh
python caption_intake.py examples/demo.vtt \
  --title "Fictional clipping handoff" \
  --duration-seconds 63 --synthetic-demo \
  --output clipping-caption-handoff.zip
python -m zipfile -e clipping-caption-handoff.zip clipping-caption-handoff
python ../managed-clipping/managed_clipping.py init \
  /path/to/authorized-source.mp4 clipping-project.json \
  --transcript-json clipping-caption-handoff/episode-import.json \
  --moments 6 --synthetic-demo
python ../managed-clipping/managed_clipping.py render \
  clipping-project.json clipping-renders
python ../managed-clipping/managed_clipping.py handoff \
  clipping-project.json clipping-handoff
```

The source video must be authorized media whose duration and cue boundaries correspond to the supplied captions. The clipping project records the source byte hash and refuses work if the source later changes.

The managed-clipping selector uses each eligible transcript cue at most once. A cue must fit entirely inside the source and, when keep ranges are supplied, inside one keep range; its 150 ms padding is bounded by that same range. If fewer cues fit than `--moments`, `init` exits with an actionable shortfall error before saving a project. It does not repeat cues or fill the gap with generic footage. The six-cue example uses `--moments 6`, corresponding to `c00001` through `c00006` only when all six cues are eligible. Request fewer moments or revise the explicitly supplied source/keep selection when fewer cues fit.

Omit `--cedar-keeps-json` to allow the whole source. An explicitly empty keep collection means no eligible footage and is refused; a supplied JSON `null` is invalid. Omitting the transcript input selects the separate generic-window workflow and does not create additional transcript-derived moments.

After rendering, the managed-clipping handoff preserves source-linked boundaries and source hash together with playable MP4s, editable SRT captions, `clips.csv`, `project.json`, and its hash manifest. Make edits before rendering, or rerender a changed clip before handoff; an earlier render does not acquire later edits automatically.

## Original operating examples

`examples/demo.vtt` and `examples/demo.srt` are fictional caption inputs used by the documented operating commands. They are retained as usable product examples, not customer recordings or evidence of recording verification. Parser, browser workbench, consumer runtimes, source-preserving output and original examples are independent of the retired generated test suites.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.

