# Durable events for the catering workspace

This optional service adds SQLite event persistence to the existing catering browser product. The original browser calculator, menu import, quotes, kitchen export and local-browser save continue to work. There is no second calculator. The service stores the browser's complete JSON document without changing prices, payment fields, dietary notes or future fields.

## Run

Use Python 3.10 or newer from the existing product directory:

```sh
python3 event_store.py --port 8080
```

Open `http://127.0.0.1:8080`. The server serves the existing `index.html` and its assets. It requires no packages or external service. The default database is `~/.hive-catering/event_store.sqlite3`, outside the public browser asset directory. A different private storage location can be selected with `--database /path/outside/assets/events.sqlite3`. Retain that file when moving the workspace; use SQLite's backup API for a consistent copy while it is running. No data is stored on an owner's device by the build or its tests: all implementation and validation occurred in the cloud container.

Opening the browser product directly or using its static host keeps the existing browser-only experience. Durable storage is available when the optional Python service is running on the same origin. This is not a public multi-tenant hosting service or a deployment claim.

## Browser integration contract

`GET /api/status` returns `{"service":"hive-catering-event-store","schema_version":1}`. A browser can use this to display the disk-save controls only when the companion service is present, while leaving local-browser saves and document exports intact.

`POST /api/events` accepts:

```json
{
  "document": {"your_existing_event_document": "unchanged"},
  "id": null,
  "expected_revision": 0,
  "title": "October lunch",
  "operation_id": "one-stable-id-for-this-save-attempt"
}
```

`document` is the complete existing event object. No catering-specific field names are required. `id: null` and revision zero create a new event. A successful save returns:

```json
{
  "id": "a-generated-32-character-hex-id",
  "revision": 1,
  "title": "October lunch",
  "document": {"your_existing_event_document": "unchanged"},
  "sha256": "digest-of-canonical-document-json",
  "saved_at": "UTC timestamp"
}
```

For the next edit, send the returned `id` and `revision` as `expected_revision`. Store these alongside the browser session's currently opened event, not inside the calculation model. On success, update the revision. On HTTP 409, keep the user's unsaved edits intact and reopen the newer event separately so they can compose them; never silently retry a stale document using a newer revision number.

The optional `operation_id` makes ambiguous network retries idempotent. Generate it once per intended save and reuse the exact request body for retries. The same ID and contents return the original saved revision even after newer edits. The same ID with changed contents returns 409. A later intentional edit receives a new operation ID. Disable overlapping save clicks or queue them in the UI so a newly created event does not become two independent events.

The remaining read endpoints are:

- `GET /api/events`: metadata-only list with `id`, `revision`, `title`, `updated_at`.
- `GET /api/events/{id}`: current revision and complete document.
- `GET /api/events/{id}/revisions`: retained revision metadata, newest first.
- `GET /api/events/{id}/revisions/{n}`: exact earlier saved document.

To restore an earlier revision, load its document and save it against the *current* revision. This creates a new revision and keeps all intermediate history. Merely opening history does not change anything.

Malformed documents return 400; absent events or revisions return 404; stale updates and operation-ID content conflicts return 409; a transient busy database returns 503. JSON requests are limited to one megabyte. Duplicate JSON keys and non-finite numbers are rejected rather than silently rewritten. The operation does not send messages, verify payments, infer dietary suitability or recalculate quotes.

## Validation

```sh
PYTHONWARNINGS=error::ResourceWarning python3 -m unittest -v test_event_store.py
python3 -m py_compile event_store.py test_event_store.py
```

The 19 tests exercise real SQLite persistence, independent events, retained revisions, recovery, concurrent stale saves, concurrent retry deduplication, original-revision retry readback, malformed JSON, Unicode and future-field preservation, existing static asset serving and complete loopback HTTP flows. Browser integration is the responsibility of the existing workspace's frontend owner; the sidecar's source handoff does not itself claim those controls have been consumed.

## Source and ownership

Demand: `bm-hive-20260908-043` in `#hive-original-builds`, thread `1788850150.183169`. ASTRA-MARIGOLD retains the original UI, calculation and customer-confirmation scope. CAIRN-CATERING owns only this sidecar, its tests and this document. An initial simultaneous claim was reconciled before publishing source; the alternative prototype UI/calculator is not part of the product delivery.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
