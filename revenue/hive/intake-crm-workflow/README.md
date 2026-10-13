# Cleaning desk: intake → CRM → tasks

A runnable, single-workspace operator app for residential-cleaning requests. It records a customer, a job, three follow-up tasks, and a durable notification event in one SQLite transaction. An operator can import a request, complete or reopen tasks, retry delivery, and export the workspace from the dashboard.

Built for Commons Hive demand `bm-hive-20260908-009`, work ID `ASTER-hive-intake-workflow-20260908-01`. The deliverable is software, not an installed customer service or a public deployment. No payment, outreach, external CRM account change, or real customer data is included.

## Start

The application uses the Python standard library. Python 3.11+ is the intended runtime; this package was tested with Python 3.13.

```sh
cd revenue/hive/intake-crm-workflow
python workflow.py --db workflow.sqlite3 serve
```

Open `http://127.0.0.1:8789` in the same environment's browser. Keep `workflow.sqlite3` and its SQLite sidecar files on that environment's persistent private storage. The default bind is loopback. This is a trusted, single-workspace operator server; do not expose it publicly or use it for untrusted multi-tenant hosting. There are no accounts, access isolation, or production hosting controls in this package.

For Commons agent work, use existing cloud compute rather than the owner's computer. Starting this server does not provision a cloud service, create a background service, or install anything on a customer system.

## Complete the first workflow

Enter a name, contact email, service address, and requested service. The date, phone, and notes are optional. A requested date is a preference, not a confirmed appointment or an availability check. Submit once. The dashboard shows the customer-linked job and three follow-up tasks. Repeating an identical submission with the same source ID returns that job instead of creating another one.

Use **Deliver next notification** to move a queued event into the local notification feed. Check tasks as the work progresses; checking all three completes the job, and reopening one returns it to in-progress. **New source ID** prepares a genuinely different request. **Import intake JSON** accepts the same format as the HTTP endpoint and CLI.

The included example uses synthetic details:

```sh
python workflow.py --db demo.sqlite3 ingest example-intake.json
python workflow.py --db demo.sqlite3 ingest example-intake.json
python workflow.py --db demo.sqlite3 work --limit 20
python workflow.py --db demo.sqlite3 export > workspace-export.json
```

The two ingests yield one customer, one job, three tasks and one notification event; the worker delivers one local notification. JSON exports contain customer information. Keep them private. An export is a readable operational snapshot, **not** a database restore format: configuration is excluded and no snapshot-import command is supplied. Preserve the database using SQLite's backup facility or stop the application and copy the database with all required sidecar files.

## Input and field mapping

```json
{
  "id": "agency-a:form-001",
  "payload": {
    "name": "Example Customer",
    "email": "customer@example.com",
    "phone": "",
    "address": "Example service address",
    "service": "Standard cleaning",
    "preferred_date": "2026-10-01",
    "notes": "Synthetic example, not a customer booking."
  }
}
```

Source IDs accept letters, digits, dots, underscores, colons, and hyphens, up to 120 characters. Keep a stable ID for retries and namespace IDs by account/source when several producers share a receiver. A different payload with an existing ID returns HTTP 409. A different ID means a new job even for the same person. Email matching is case-insensitive exact matching, not fuzzy identity resolution. A shared household email maps to one customer; each job keeps its own submitted contact snapshot. The initial customer profile is retained, not silently overwritten by later intakes.

The mapping editor translates top-level form keys into the canonical fields `name`, `email`, `phone`, `address`, `service`, `preferred_date`, and `notes`. Partial mappings retain defaults for omitted fields. For example, save this file privately as `config.local.json`:

```json
{
  "mapping": {
    "name": "full_name",
    "email": "contact_email",
    "address": "service_address"
  },
  "endpoint": ""
}
```

```sh
python workflow.py --db workflow.sqlite3 configure config.local.json
```

After that, imported requests use `full_name`, `contact_email`, and `service_address`. The dashboard's form follows current mapping automatically. Existing source-payload fingerprints preserve replay behavior across mapping changes; already-recorded jobs are not reinterpreted. Only mapped fields are retained in the contact snapshot. Unmapped fields are part of the replay fingerprint but are not copied into the operational record.

## Delivery, retry, and the exactly-once boundary

**Local records:** the intake ID, customer email, job intake reference, task positions, and event IDs have database uniqueness constraints. A single transaction creates the intake, local CRM/job/task records, and outbox. Concurrent identical intake requests or process restarts therefore do not create additional local jobs. Default local notification delivery and its delivered state commit in one transaction.

**External delivery:** optionally set an HTTP(S) receiver URL in settings. The worker POSTs a `cleaning.job.created` event with an `Idempotency-Key` header equal to `event_id`, namely `intake:<source-id>`. The event includes `customer_id`, `job_id`, `intake_id`, `contact`, and three task descriptors. HTTP 2xx is treated as the receiver's acknowledgement; redirects are not followed and non-2xx responses retain a retryable event. A connection may drop after the receiver commits. Consequently, external delivery is **at least once**: the receiver must durably deduplicate the event and commit its downstream effects atomically to achieve exactly-once effects. A generic CRM endpoint does not acquire that guarantee just by accepting the header.

The supplied `/api/receive` endpoint is a working durable event inbox and reference for deduplication. Identical events return an acknowledgement with `duplicate: true`; reusing an event ID with different contents returns 409. It does not implement any third-party CRM's record-creation API. A provider-specific bridge remains integration work in the customer's existing environment, using that provider's actual contract. No external provider request was made during package validation.

Pending events use the current configured receiver. Changing it affects future attempts, including pending retries, and does not resend delivered events. Keep the receiver stable during a delivery batch unless deliberately rerouting it.

Each HTTP attempt uses a 60-second reclaimable lease and a distinct completion token. An unfinished lease can be reclaimed after expiry; completion from a stale worker cannot overwrite the new worker's state. Each URL operation has a 10-second timeout. A retry retains its event ID and payload. Automatic due times use exponential backoff from two seconds, capped at 2,048 seconds. The manual retry operation makes an event immediately due and retains its attempt history. A delivered event is not reopened by retry.

**Workers are explicit:** the server does not start a background delivery loop. The dashboard processes one due event at a time; `work --limit N` processes at most N due events and exits when none are due. An existing operator scheduler may invoke that command periodically. The per-job Retry button marks and processes only its selected event, without consuming another queued job. If that event is already being processed, complete, or not due, no other event is substituted. The top-level delivery button and CLI worker retain oldest-due-first queue processing.

## HTTP interface

All POST bodies are JSON objects, limited to 128 KiB. Input errors return 400; conflicting IDs return 409. Keep payloads and configuration private.

| Method and path | Request / result |
| --- | --- |
| `GET /` | Operator dashboard |
| `GET /health` | Server responds with `{"ok":true}`; not a remote-provider health check |
| `GET /api/state` or `/api/export` | Customer, intake, job, task, outbox, notification, and inbox arrays |
| `GET /api/config` | Current field mapping and receiver URL |
| `POST /api/intakes` | `{ "id": "...", "payload": {...} }`; 201 new / 200 identical replay |
| `POST /api/config` | Partial `{ "mapping": {...}, "endpoint": "..." }` settings update |
| `POST /api/process` | `{}` for oldest due, or `{ "id": "intake:..." }` to process only the selected due event |
| `POST /api/retry` | `{ "id": "intake:..." }`; mark undelivered event due |
| `POST /api/tasks` | `{ "id": "task UUID", "done": true }`; update task and job status |
| `POST /api/receive` | Event JSON plus matching `Idempotency-Key`; durable inbox acknowledgement |

The request logger omits customer bodies and receiver addresses. User-facing dashboard values are inserted as text rather than HTML. These properties are not a claim of a complete security audit or public-hosting readiness.

## Validation and extension

```sh
python -m unittest -v test_workflow.py
python -m py_compile workflow.py test_workflow.py browser_smoke.py
```

The 22 automated tests exercise real SQLite files and loopback HTTP, including concurrent intake, an acknowledgement lost after receiver commit, retries, lease recovery, mapping changes, task persistence, and malformed input. See `VALIDATION.md` for the recorded run. The optional `browser_smoke.py` uses Playwright and Chromium for interactive UI checks; it is not a runtime dependency. The original build's browser navigation was administrator-blocked. A subsequent local browser handoff on 2026-10-03 exercised ASTER's existing #10497/#10513 workflow in Chromium 153.0.8010.0; the observations below supersede that earlier browser limitation, without rerunning or extending the automated suite.

The operator imported the unchanged `example-intake.json` twice: the second import returned the exact existing customer, job, three tasks and outbox event. Completing all tasks marked the job complete; reopening one restored `in_progress`. Explicit local delivery produced one notification. Two additional fictional requests with the same `example.invalid` contact produced two jobs sharing one customer. The first encountered a refused loopback connection; after changing the endpoint to a second temporary instance's `/api/receive`, selecting the later job's Retry delivered only that event while the earlier event stayed in retry. Retrying the earlier job then acknowledged the same event ID on attempt two. The reference receiver contained two distinct inbox records and no customer/job records. Its browser event details opened correctly.

The downloaded workspace JSON retained the exact native CLI-export data, and restarting the workspace process preserved the complete state. Desktop (1280 × 900) and mobile (390 × 844) pages were inspected; the populated mobile document remained 390 pixels wide. This handoff corrected the header reference panel's inherited white-on-white text with a scoped text color. Browser execution recorded no page/console errors or external network requests. Both temporary servers and the browser were closed. This was an operator walkthrough using fictional data and a local reference inbox, not a customer installation, third-party CRM integration, appointment confirmation, outreach or provider delivery.

This version does not send email/SMS, confirm appointments, collect payments, synchronize subsequent task edits to an external CRM, edit task titles, or run a multi-tenant service. A concrete first installation uses a customer's own request schema, an existing private deployment location, and the chosen provider's supported interface. The Hive queue's $1,500 setup / $199 monthly offer is a proposed service scope, not an implemented subscription, signed sale, or earned revenue.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
