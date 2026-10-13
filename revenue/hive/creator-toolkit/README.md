# Creator Desk

A runnable resource library and voluntary follow-up drafting workspace for Hive demand `bm-hive-20260908-037`. Python 3.10+ and SQLite from the standard library are sufficient for the application. No external service or model is called.

## Run in an existing cloud environment

Creator Desk is a shared trusted workspace. Its users can open member records,
creator controls, follow-up drafts, and workspace backups without an operator
key or an initialization step.

From the Commons repository root:

```sh
python3 revenue/hive/creator-toolkit/app.py \
  --db /path/to/persistent/creator-desk.sqlite3 --port 8768
```

Open `http://127.0.0.1:8768/` in a browser that can reach that environment.
Choose an existing persistent private cloud directory for `--db`; do not
commit the SQLite file or put live member records in the source repository.
No new paid infrastructure is provisioned by this application.

The resource library, delivery view and creator workspace are three tabs of
the same app. Opening **Creator workspace** loads the existing creator controls
directly. Members can browse resources, reconnect to a delivery record, change
their follow-up preference, and submit a creator request. This shared operating
model does not distinguish authenticated members from creators: anyone who can
reach the listener can use its workspace operations and see its records.

Existing workspaces retain their resources, deliveries, consent history,
inquiries and retry records. Legacy `creator_security` rows are left in place
but are not consulted. No credential migration or rotation is needed. The
browser no longer loads an unlock layer, reads a saved operator key, or attaches
that key to requests. Multi-community routing is described in [HOSTING.md](HOSTING.md).

## Completed workflow

Resources retain their original bytes, file name and SHA-256. A member requests a resource and receives a durable delivery reference. Repeating that resource request for the same normalized email address returns the existing reference rather than creating a second delivery or restarting a sequence. Files can be downloaded again; this is one durable delivery record, not a restriction on redownloading.

An unchecked opt-in box schedules no messages for that request and does not change an existing preference. An affirmative choice records the displayed consent wording and schedules that resource's optional sequence. A repeat resource request never changes consent. The separate **My deliveries** controls are the way to change an existing preference.

Stopping follow-ups cancels all queued drafts in one transaction. Enabling the preference again leaves cancelled drafts cancelled; it does not reschedule old requests. A future request for a different resource may explicitly opt into its sequence. Stale preference edits return a conflict so an older browser does not overwrite a newer choice.

Sequence offsets are integer minutes from the original opted-in request, with at most 20 steps. Each step contains `delay_minutes`, `subject` and `body`. Queued subjects, bodies and due times are snapshots; editing a resource does not change already queued messages. File bytes and external destinations are immutable. To replace an asset, archive its resource and add a new one. Archiving hides it from the library while preserving prior deliveries.

The member can submit a request for the creator, and the creator can resolve it through Creator workspace. Members can export their current record, delivery references and consent history as JSON. The browser remembers only a reconnect reference; the authoritative records live in SQLite.

## Follow-up handoff, not automatic sending

The operator outbox shows queued, cancelled and externally recorded entries. A due queued item can be downloaded as an `.eml` draft from Creator workspace. Export rechecks its state, due time and current member preference. The file includes `X-Unsent: 1`, a stable workspace reference and an opt-out instruction; no sender is fabricated and no SMTP connection is made.

The operator supplies the sender and uses their existing mail workflow. Immediately before an external send, check the current preference again. An already downloaded file cannot be recalled by this app, and replies requesting unsubscribe are not automatically ingested. Apply those replies through **My deliveries**. After an actual external delivery, its reference can be recorded through Creator workspace. The resulting `recorded` state is an operator statement, not independent provider verification. Exporting or recording a draft does not send mail.

Native community-platform installation, supported provider event ingestion, automatic email delivery, billing, customer acceptance and a hosted multi-community service remain separate work. This version does not claim those integrations or a sale.

## Workspace HTTP surfaces

The established routes remain available:

- `GET /api/operator` — compatibility response `{"operator": true}`;
- `GET /api/dashboard` — resources, outbox, inquiries and workspace counts;
- `GET /workspace.sqlite3` — checked online SQLite snapshot;
- `GET /draft.eml?id=...` — due follow-up draft export;
- `POST /api/change` — resource, inquiry, outbox and member operations.

These routes do not require an Authorization header. Member reconnect
references select records; they do not authenticate people. Use this application
for a shared workspace whose users may access its records and creator actions.
It does not implement a user-account system or per-member isolation.

Input validation, file/body limits, consent transitions, draft due-time checks,
operation-ID replay handling and revision conflicts still apply. Application
limits are 8 MiB per original file, 12 MiB per HTTP request, 20 sequence steps
and bounded text fields. SQLite records, resource bytes and operation results
persist until the operator manages the database.

For older integrations, `/operator-auth.js` serves an inert compatibility asset.
The legacy `OperatorAuth` names and `operator_auth.py init/rotate` commands
remain importable/callable but perform no credential checks, issue no keys, and
do not open or alter the database. The CLI reports the shared-workspace mode.
Legacy Python `initialize()`/`rotate()` return an empty string; `verify()` and
`verify_header()` return true without inspecting their input.

## HTTP integration surface

`GET /api/catalog` returns visible resources and the consent wording. `GET /api/member?id=...` returns the selected record, deliveries and consent history. `GET /api/delivery?id=...` returns delivery metadata; `GET /download?id=...` returns original file bytes. Workspace endpoints are listed above.

`POST /api/change` accepts `application/json`:

```json
{
  "action": "request",
  "operation_id": "stable-client-operation-reference",
  "payload": {
    "resource_id": "resource-id-from-catalog",
    "email": "reader@example.invalid",
    "name": "Fictional reader",
    "opt_in": false
  }
}
```

Actions are `resource.create`, `resource.update`, `request`, `preferences`, `inquiry`, `inquiry.close` and `outbox.record`. Their executable contracts are in `Store.mutate`. The browser exercises those same routes; it is not a second storage implementation. All actions use the shared-workspace model described above.

Reuse an operation ID and identical payload when retrying a request whose result is uncertain. Reusing it with different content returns HTTP 409. Successful retries return the original response snapshot without reapplying the mutation; read the current GET endpoint afterward when current state matters. Resource updates and preference changes additionally require `expected_revision`. New request IDs for an already-delivered member/resource also coalesce, including concurrent callers. Queues are created transactionally with the original delivery, not by a separate polling worker.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
