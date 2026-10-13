# Sponsorship placement calendar

A dependency-free export component for the newsletter sponsorship desk (Hive demand 026). It consumes the desk's records; it is not another booking engine, database, scheduler or browser application.

## Run it

Python 3.10 or newer. From this directory:

```sh
python placement_calendar.py placements.json placements.ics
python -m unittest -v test_placement_calendar
```

Save this fictional input as `placements.json`:

```json
{
  "namespace": "demo-workspace-7d357ae1",
  "generated_at": "2026-09-08T11:30:00Z",
  "records": [
    {
      "id": "booking-01",
      "issue_date": "2026-09-15",
      "summary": "Sample publisher: sample offer",
      "description": "Fictional local placement. Creative handoff is prepared, not sent.",
      "revision": 1,
      "updated_at": "2026-09-08T10:00:00Z",
      "cancelled": false,
      "url": "https://example.invalid/placements/booking-01"
    }
  ]
}
```

The CLI validates the entire input before opening the output. Bad input exits 2 with a diagnostic and leaves an earlier output untouched. A successful write replaces the named file; the write is not a crash-atomic filesystem transaction. Duplicate JSON keys are rejected rather than silently choosing a value.

## Connect the existing desk

```python
from datetime import datetime, timezone
from placement_calendar import CalendarError, build_calendar

# Adapt the application's existing records. Keep its original IDs, persisted
# revisions, last-change timestamps and cancellation history.
records = [{
    "id": str(booking["id"]),
    "issue_date": booking["issue_date"],
    "summary": booking["title"],
    "description": booking.get("notes", ""),
    "revision": booking["revision"],
    "updated_at": booking["updated_at"],
    "cancelled": booking["status"] == "cancelled",
} for booking in existing_bookings]

try:
    data = build_calendar(
        records,
        namespace=persisted_workspace_calendar_id,
        generated_at=datetime.now(timezone.utc),
    )
except CalendarError as exc:
    # Display this input diagnostic using the desk's existing error handling.
    # An empty list has no placements to export; do not create a dummy event.
    raise
# Return data with Content-Type: text/calendar; charset=utf-8,
# Content-Length: len(data), and an appropriate .ics download filename.
```

`existing_bookings` and `persisted_workspace_calendar_id` above are integration placeholders, not names asserted to exist in QUOIN's application. Map them to the actual application schema. The function returns bytes and does not write to the database, mutate inputs, open URLs, send invitations or update a remote calendar.

Required record fields: `id` and `summary` are nonempty Unicode strings; `issue_date` is an exact valid `YYYY-MM-DD`; `revision` is an integer from 0 through 2147483647, excluding booleans; `updated_at` is a timezone-aware datetime object or ISO datetime string. Optional `description` defaults to empty, `cancelled` defaults to false and must be a boolean, and `url` defaults to omitted. A supplied URL must be ASCII HTTP(S), with no credentials, whitespace or backslashes. Percent-encode non-ASCII path/query characters before supplying a URI; use an ASCII hostname.

`generated_at` is also timezone-aware. UTC conversion errors, invalid dates, unsupported control characters, invalid Unicode, duplicate record IDs, malformed record containers and empty calendars raise `CalendarError`. Unknown record fields are ignored, not exported. Inputs are not modified. Timestamp output has whole-second precision; revision numbers distinguish changes made within the same second.

## Update and cancellation behavior

Choose a stable unique namespace for each independent workspace and persist it. Reusing a namespace with the same booking ID intentionally produces the same event UID. Generate the namespace once, not on every request. Namespaces are identity metadata, not credentials.

An event UID depends only on that namespace and booking ID, not on the issue date, summary or revision. Increase the persisted revision and update `updated_at` when changing calendar-visible booking data, including rescheduling and cancellation. The component does not have database history and cannot detect a caller reusing an old revision. `generated_at` is recorded separately as `X-HIVE-GENERATED-AT`; it does not pretend that unchanged events were revised.

Include cancelled bookings with their latest revision and `cancelled: true`. The exporter retains them with the same UID and `STATUS:CANCELLED`; it does not silently drop them. Active local plans are `TENTATIVE` and transparent to busy-time calculations, with a description that does not imply publisher confirmation or payment. The issue date is a one-day all-day event, not a guessed send time. Events are sorted deterministically by issue date and UID.

This is a downloadable snapshot, **not calendar synchronization**. It does not emit invitation/cancellation transactions or claim that importing a file updates or removes an existing event in any particular client. Client import behavior, actual publisher confirmation, scheduled delivery and external calendar changes remain separate. The initial validation did not exercise Google Calendar, Outlook or Apple Calendar.

## Format and validation

The implementation follows the relevant [RFC 5545](https://www.rfc-editor.org/rfc/rfc5545.html) representation rules: CRLF lines; folding by 75 UTF-8 octets; TEXT escaping; UTC timestamp properties; persistent UID and source SEQUENCE; DATE-valued starts with whole-day duration. For snapshots without METHOD, DTSTAMP tracks LAST-MODIFIED, not file-export time. No METHOD, ORGANIZER or ATTENDEE is emitted. A calendar must contain a component, so an empty export reports no placements rather than inventing one.

The 30-method standard-library test suite executes the real formatter, separate byte-level unfolding, real temporary SQLite reopen/reschedule/cancel operations, real CLI subprocesses and filesystem writes, and a standalone loopback HTTP adapter. That adapter demonstrates consumption of the component, not integration with the desk's production route. No third-party calendar-client interoperability, full application workflow, customer fulfillment, deployment or revenue result is asserted by this component's test result.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
