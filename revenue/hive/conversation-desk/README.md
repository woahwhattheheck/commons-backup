# Conversation Desk

A working local conversation-drafting workspace for Hive demand
`bm-hive-20260908-005`. Import text or an original screenshot, correct the
transcript, write what you want to communicate, compare three tone options,
edit your reply, and copy it yourself. Saved drafts and screenshots survive
restarts in SQLite. No message is sent by this application.

## Start

Python 3.10+ and its standard library are sufficient for the application.
From an existing private cloud workspace or another suitable trusted host:

```sh
cd revenue/hive/conversation-desk
python3 app.py --db /existing/private/path/conversations.sqlite3 --port 8769
```

The database's parent directory must already exist. Open
`http://127.0.0.1:8769` on that host. The default bind is loopback; `--host`
is configurable. This is a shared single-workspace application, not an
isolated multi-customer SaaS. Anyone able to reach the running service can
read, edit, export or erase its workspace. Do not put real chats in a
publicly shared instance. No account, telemetry, remote model call or
automatic email/message delivery is present.

Optional screenshot transcription uses the locally installed `tesseract`
executable and its English language data. With no OCR installation, manual
transcription and all other features remain available. OCR is approximate:
review the extracted text before appending it to a transcript. Source images
are never silently substituted with the transcription.

## Complete the workflow

1. Choose **New conversation** or **Try a fictional example**. Paste the
   transcript and add private context notes.
2. In screenshot intake, select a PNG/JPEG/WebP up to 6 MiB, then choose
   **Save screenshot**. The original bytes are stored and can be opened.
   **Transcribe locally** runs one bounded local OCR operation. Correct its
   text and choose **Append corrected text to transcript**; then save.
3. Choose an intent: respond, follow up, invite, set a boundary, or close.
   Enter your point/proposal and optional question. Follow-ups require a
   question; other intents require a point. **Save and draft three options**
   gives warm, direct, and light framing. Boundaries and closure use gentle
   framing instead of a playful option.
4. Select a draft, edit it, and save or copy it. Copying is not sending.
   Where the clipboard API is unavailable, the draft is selected for manual
   copying. Reload or reopen a saved conversation to continue later.
5. Export saved data as JSON, delete an individual image or conversation,
   or type **ERASE** to remove every saved conversation and image.

## What the drafting engine does

This version is explicitly **template-based**, not a language model. It
uses the proposed words and selected intent, adding different framing. It
does not claim to understand an entire chat or infer interests, availability,
feelings, identity, consent or personal facts. Context notes and the transcript
stay beside the draft for the user's review; they are not mined for new claims.
The user chooses and sends the final message in their own messaging application.

The app has no checkout, usage billing, dating-platform connector, paid
subscription, customer installation or deployed service. The original demand's
proposed price is not an implemented payment product or revenue claim.

## Data, revisions and deletion

Each saved conversation has a revision. Stale edits, screenshot changes and
deletions return HTTP 409 rather than overwriting a newer revision. The UI
keeps unsaved text visible after a conflict; copy it or reload deliberately.
Controls are unavailable while a request is in flight so typing cannot be
silently overtaken by a completed save. Concurrent editors still need to
reconcile their changes; there is no real-time collaboration.

Screenshots are BLOBs linked to their conversation, with SHA-256 and size
metadata. Deleting a conversation also deletes its screenshots. Removing a
screenshot alone does **not** erase text already copied into the transcript.
Whole-workspace erase removes all saved chat rows and images and clears the
visible editor. SQLite `secure_delete` is enabled; this is not a promise of
forensic erasure from operating-system snapshots, disk media or backups.
Previously exported JSON files and downloaded images must be deleted separately.
Exports include the original images as base64 and all saved text. There is no
export-import restoration UI in this version.

Responses carry `Cache-Control: no-store`. Access logging is disabled so chat
paths do not enter access logs. OCR runs in a temporary directory removed after
the process finishes, with a 20-second timeout and no shell invocation. The
server requires UTF-8 JSON objects for writes and has a 9 MiB request limit.

## Tests

```sh
python3 -B -m unittest -v test_app
node --check desk.js
```

The standard-library suite covers actual temporary SQLite databases, reopening,
concurrent revisions, original image bytes, export, deletion, five drafting
intents and a real threaded HTTP server. Its OCR failure-path doubles are
explicit; they do not stand in for the screenshot workflow.

An optional UI smoke requires Playwright, Chromium, Pillow and local Tesseract:

```sh
python3 browser_smoke.py --artifacts /existing/private/path/conversation-ui-check
```

This harness runs the actual JavaScript against the actual local HTTP app
through an explicit Python binding, with a fixture-rendered thumbnail. It
performs one real Tesseract transcription of a synthetic image, applies a user
correction, saves/reopens, generates/edits drafts, exercises a conflict and
removes data. It does not establish native browser networking, clipboard or
download completion. Direct Chromium loopback navigation in the build cloud
returned `ERR_BLOCKED_BY_ADMINISTRATOR`; that limitation is not reported as a
passing native-browser test.

All example text and screenshots used by the tests are fictional. No real
customer chat or contact is included in the source distribution.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
