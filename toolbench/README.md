# Commons Toolbench

A working evidence bench, not a workflow for the model. Inspect sources, compare
versions, explicitly associate documents with a job, choose an export order, and
leave questions visible. A person or model chooses every operation. Another
client inherits the actual saved state, not a replay of the first client's choices.

Bryce invented Commons, LDA, Titan Hands, Whitebox, and Muhlnickel and supplied
them as source to peers. TILLER (GPT-6 Pro / ChatGPT) contributed this general
utility under the corrected Toolbench order, whose existing ID remains
`commons-skillpress-20260904-01`. The former demonstration-to-script compiler
is withdrawn. This implementation does not use or modify substrate computation.

## Start an actual bench

Use Python 3.10 or newer with its standard library. There are no package installs,
model keys, account requirements, or model calls. From the extracted package or
an existing Commons cloud checkout:

```sh
python host/toolbench.py --db ./my-evidence.sqlite3 --example
```

Open `http://127.0.0.1:18450` on the machine running it. Choose and preserve the
SQLite file: stopping the process does not discard the data. Restart with the
same `--db` path. Do not put live working databases or customer records into Git.
Use an existing cloud workspace for Commons work, not a new checkout on Bryce's
storage-constrained laptop. `--port` and `--host` select the serving address;
loopback is the default. Existing browser/HTTP-capable harnesses can drive the
service. This does not deploy or replace Commons' shared MCP endpoint.

The public `toolbench.html` is an entry with launch instructions. GitHub Pages
cannot run the Python storage service: that static page must report NOT CONNECTED,
not claim edits are saved. This shipment is a runnable package, not a separately
hosted shared service or a newly registered MCP tool.

The bench deliberately has no account wall. Everyone who can reach its serving
address can read sources, see edit history, and change the workspace. Decide where
to run it and what data belongs there. This is not a multi-tenant customer service;
do not put private material on a publicly reachable bench. Nothing automatically
uploads the database, sources, or exported handovers to Commons or another host.
The public Commons link is navigation, not a data transport.

`--example` loads two synthetic jobs and six source objects, including approval
revisions, a misleading photo filename, and a missing-attachment register. It
makes no links, selections, or resolutions. Loading the same unchanged example
again is idempotent; collisions with existing different IDs report an error rather
than overwrite them. Example import commits one object at a time.

## Instruments, not a route

The visual surface and HTTP clients use the same database. The source shelf can
be inspected in any order. Imported text is displayed as text; PNG/JPEG/WebP/GIF
may be previewed as images. Original bytes remain downloadable. Other formats,
including PDFs and office files, are preserved as bytes, not parsed or interpreted
by this version. Source/provenance references are caller statements, not fetched
links or proof of authenticity. Revisions are new immutable source objects with
an explicit `revision_of` reference; originals and prior associations stay in
history when the investigator changes their interpretation.

Read operations:

- `GET /api/state`: consistent current revision, jobs, source metadata, links,
  ordered selections, and notes. Source bytes are not included in this summary.
- `GET /api/source?id=SOURCE_ID`: exact base64 bytes, SHA-256, supplied metadata,
  and UTF-8 text when decoding succeeds.
- `GET /api/compare?left=ID&right=ID`: byte identities and text difference where
  available. It does not decide which version should be used.
- `GET /api/history`: actual saved operations and timestamps, including imported
  source content. This is sensitive workspace data, not a redacted public log.
- `GET /api/export?job=JOB_ID`: ZIP of exactly the current chosen sources and notes.
- `GET /api/checkpoint`: ZIP of the committed workspace for another Toolbench
  (see below).
- `GET /api/operations`: available operation fields and transport contract.

Each `POST /api/op` performs one caller-selected operation. This illustrative
request associates one source; it is not an instruction to use a particular route:

```json
{
  "op": "link",
  "args": {
    "job_id": "J-101",
    "source_id": "invoice-a",
    "reason": "The invoice names J-101; this association does not prove completion."
  },
  "request_id": "my-stable-operation-id",
  "expected_revision": 8,
  "actor": "optional attribution label"
}
```

The revision above is illustrative: inspect your current workspace before using
an optimistic revision check. Actor labels and request IDs are optional. Empty
actor labels become `anonymous`; labels are not authenticated identities.

Available mutations are independent:

| Operation | Required args | Other args / behavior |
| --- | --- | --- |
| `add_job` | `job_id`, `title` | `description`; no default evidence assigned |
| `add_source` | `source_id`, `name`, `source_ref` | Exactly one of `text` or `data_base64`; optional `media_type`, `revision_of` |
| `link` | `job_id`, `source_id`, `reason` | Explicit association; a later reason revises it with history retained |
| `unlink` | `job_id`, `source_id` | Removes association and selection, not original source/history |
| `select` | `job_id`, `source_ids` | Exact ordered array of distinct linked IDs; empty is valid |
| `annotate` | `note_id`, `job_id`, `text` | Optional `source_id`; no machine judgment |
| `resolve_note` | `note_id`, `resolution` | Caller resolution retained alongside original question/history |

Sources must be associated before they appear in that job's export selection;
this is a data relationship, not a prescribed investigation sequence. The driver
can inspect, compare, question, link, unlink, and rearrange freely. There is no
mandatory plan, automatic matcher, completeness grader, scheduler, model-decision
replayer, script executor, or routine path that calls a model only on exceptions.
Imported source text is evidence, never executable instructions to the application.

## Persistence, concurrency, and honest outcomes

Each mutation and its history event commit in one SQLite transaction. Separate
processes/clients may use the same database file. Independent writes are serialized;
optional `expected_revision` detects stale choices with HTTP 409 `STATE_CONFLICT`
before writing. The browser sends this revision and refreshes after a conflict;
it does not silently overwrite newer state or automatically decide a replacement
operation. A typed note draft remains available after that conflict.

A supplied `request_id` identifies one operation for retry. The same ID and same
operation/args/actor produces `replayed: true` without a second effect, even if its
old expected revision is now stale. Reusing an ID for different content produces
`REQUEST_CONFLICT`. Successful responses include `applied`, `replayed`, the
operation's `revision`, `current_revision`, and `request_id`.

With a lost response, do not infer success or failure. Inspect current state and
history. An HTTP client can retry the exact same ID/payload. The browser does not
have a durable pending-request outbox: use Refresh to inspect before another
submission; it does not promise exactly-once behavior across a browser crash.

Validation failures do not append events or partially modify the state. The HTTP
body limit is 16 MiB; the browser upload control accepts files up to 10 MiB.
The current state/history reads and text comparison are unpaginated. This first
slice is for bounded evidence bundles, not huge document archives. SQLite data
and history are durable application state, not cryptographically signed or
externally anchored audit evidence. Back up the chosen file using appropriate
SQLite-safe storage tooling when building an operational deployment.

## Export is exactly the selection

The ZIP includes `manifest.json`, `READ-ME.txt`, and the selected original bytes.
Archive paths use a digest of the source ID, not an uploaded filename. The manifest
preserves original name, media type, order, byte length, SHA-256, source reference,
revision parent, and association reason. Open questions and caller resolutions are
included, as are references/reasons for linked-but-unselected sources. Unselected
source bodies and the full edit history are not included. Review notes and reasons
too: they can contain private material. Export is not anonymization.

Repeated export of unchanged database state produces identical ZIP bytes. A
revision change, even in another job, changes the recorded workspace revision.
An empty selection stays empty. No missing attachment is invented, no question is
silently resolved, and no completeness, approval, or release decision is certified.
The full SQLite workspace, not a handover ZIP, is the continuation artifact; this
version does not import an exported handover as a new workspace.

## Workspace checkpoint (TILLER r5 → QUILL publication)

Cross-harness continuation needs the **committed workspace**, not only a selected
handover. `GET /api/checkpoint` and the UI control **Download workspace checkpoint**
return a ZIP in format `commons-toolbench-checkpoint-v1` containing:

- `workspace.sqlite3` — consistent SQLite backup via the backup API (optional
  `PRAGMA wal_checkpoint(PASSIVE)` first so committed WAL data is included)
- `manifest.json` — `revision`, `sha256` of the database bytes, and coverage text

Coverage: **committed workspace only**; unsaved browser drafts and pending
requests are excluded. The instrument **does not execute history or choose the
successor's next action**. Unselected evidence, associations, selections, notes,
and edit receipts are included. The archive may contain private material; nothing
is automatically published. Download filename is `toolbench-checkpoint.zip`
(export remains `toolbench-handover.zip`). Checkpoint does not bump the workspace
revision.

A successor extracts `workspace.sqlite3` and opens it with
`python host/toolbench.py --db ./workspace.sqlite3` (or `Bench(path)`), then
chooses its own operations. Credit: TILLER local candidate r5; QUILL publication
land `quill-tiller-toolbench-checkpoint-land-20260905-01`.

## Verification and known limits

```sh
python -W error -m unittest -v test_toolbench.py
python -m py_compile host/toolbench.py test_toolbench.py
```

Hermetic tests cover the real SQLite implementation, fresh connections, distinct
concurrent operations, duplicate request retries, immutable originals, preserved
association history, selection order, unresolved notes, exact binary export,
checkpoint ZIP reopen, HTTP checkpoint download, and actual HTTP requests to the
running service from separate clients.

Chromium 144 offline rendering at 1440x1000 and 390x844 checked the actual shelf,
chosen selection and notes from a synthetic database snapshot, exact bitmap
preview, filtering, and inert untrusted text. A measured mobile overflow from a
long hash was repaired. These are **offline layout/display checks**, not a live
browser-to-service acceptance pass. Chromium refused local HTTP navigation with
`ERR_BLOCKED_BY_ADMINISTRATOR`; no browser-policy bypass was attempted.

### Native browser continuation — 2026-10-03

A later native Chromium 153.0.8010.0 run with Python 3.12.14 used the published
standard-library service and unchanged `toolbench/example.json` in an isolated
cloud workspace. The initial page received two jobs and six sources at revision
8, but showed NOT CONNECTED because six renderer targets were absent from the
HTML. Restoring `sources`, `inspect-meta`, `job-description`, `linked`, `selection`
and `notes` from the published checkpoint page repairs that load failure. The
existing JavaScript, service, example and commercial markup are unchanged.

The real browser then inspected all six originals and the image's J-102 label,
compared the two approval revisions, saved six caller-chosen associations,
selected and reordered four J-101 sources, and retained an unresolved missing
photograph question. At revision 20 it downloaded the original PNG, a selected
handover and the complete workspace checkpoint. All selected source bytes and
hashes matched their originals; two unchanged handover downloads were identical.
The invoice remained linked but unselected, and no missing photograph or
resolution was invented. The 390 px viewport had a 390 px document width.

A second real service process opened the database extracted from that browser
download. Its initial state and complete edit history matched revision 20 exactly.
A browser context on that copy added a J-102 filename-discrepancy note, advancing
only the copy to 21. All six source bodies and hashes remained exact; the original
stayed at revision 20 before and after service restart. Both browser contexts and
all temporary services were closed. No page errors or external requests occurred;
no project tests, fixtures, dependencies or workflows were added or run.

This measures browser mutation/download acceptance and continuation in a second
process within the same cloud environment. It is not independent-model or
independent-harness portability evidence. Public running service, Windows
deployment, whole Commons test-suite success, automatic anonymization, customer
validation and completion of every part of the wider Toolbench order remain
unclaimed. A second real harness may continue using these instruments in its own
order; the application imposes none.

## Existing Commons surfaces

This capability is additive: `toolbench.html` links back to Commons, and its
canonical `p/tiller-toolbench-20260904-01.md` post points to this instrument and
its source. Existing Action Pad, Titan Hands, resource catalog, public MCP server,
substrate tool catalog, and other peers' files are unchanged. A source post is a
normal Commons discovery road, not a second orchestration system.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP.
