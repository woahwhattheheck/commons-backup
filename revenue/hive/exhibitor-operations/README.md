# Exhibitor Operations

A runnable, single-organizer workspace for small conferences and trade shows.
Create events, collect exhibitor requirements and original assets, resolve booth
changes, keep the current materials deadline visible, and export an organizer's
handoff packet. This implements Hive demand `bm-hive-20260908-046`.

## Start

Runtime: Python 3.10 or newer with its standard SQLite module. No Python packages,
Node build, external API, account setup, or remote service is needed to run it.
Keep `app.py`, `index.html`, and `desk.js` together.

```sh
python3 app.py --demo
```

Open `http://127.0.0.1:8766/` in the same environment's browser. `--demo` creates
one clearly marked synthetic event only when the database has no events. Leave
it off for an empty workspace. To choose a separate storage file or port:

```sh
python3 app.py --database /path/to/event-work/events.sqlite3 --port 8766
```

Default persistent storage is `~/.exhibitor-operations/events.sqlite3`, separate
from the source/served asset directory. Stop the server with Ctrl+C. Reopening
with the same database preserves saved records and original asset bytes.
Execution for the delivered validation took place in a cloud container, not on
Bryce's computer.

## Complete a working event

1. Create an event with its venue, event start, materials deadline, and current
   instructions. Browser forms use the browser's displayed time zone; saved API
   timestamps contain explicit offsets and are normalized to UTC.
2. Add an exhibitor with contact details, booth code, width/depth in metres,
   requested power in watts, and equipment/access/loading notes. Blank booth
   codes are permitted. Nonblank codes are unique within each event.
3. Upload an original file. The workspace retains its exact filename, contents,
   byte count and SHA-256. A repeated upload of the same filename and bytes
   reuses the stored asset; different contents remain a separate version.
4. Open the exhibitor portal from the exhibitor card. It shows that exhibitor's
   current requirements and the event's current deadline. Record a proposed
   change and its reason without changing the current agreed requirements.
5. In the organizer view, refresh, add a resolution note, and apply or dismiss
   the request. Applying changes the booth requirements and floor-plan export
   together. A request against an older revision stays pending until it is
   dismissed and re-created against the current record; it never overwrites
   newer requirements silently.
6. Update the event deadline when needed. Refresh the portal to see the current
   date. Newly downloaded reminder drafts and calendar files use that revision.
7. Download the floor-plan CSV, original files, per-exhibitor reminder draft, or
   complete event ZIP for the event team.

## What the handoffs contain

**Floor-plan CSV:** one row per exhibitor with stable ID, company, booth,
width/depth, exact decimal area, power, requirements, and saved revision. It is a
requirements handoff, not an automatically drawn floor plan or an aisle,
capacity, electrical, fire-code, or accessibility certification. The organizer
remains responsible for the actual venue layout. Text cells beginning with a
spreadsheet formula indicator receive a leading apostrophe in this CSV; the
original text stays intact in JSON and SQLite.

**Calendar:** materials due and event start as two UTC calendar entries. Their
UIDs remain stable and their sequence advances with the event revision. A
previously imported file is a snapshot, not a live calendar subscription. Review
or replace old entries in the destination calendar when the event changes; no
external calendar is updated by the app.

**Reminder:** an `.eml` draft with the exhibitor's address, current deadline,
venue, booth requirements, and source revisions. `X-Unsent: 1` identifies it as
an unsent draft. Add the appropriate sender/signature and review it in the
organizer's mail workflow. No email is sent, scheduled, or automatically retried.

**Event ZIP:** `event.json`, `exhibitors.json`, `changes.json`, `assets.json`,
`floor-plan.csv`, `deadlines.ics`, per-exhibitor reminder drafts, and all original
asset versions. A single SQLite read transaction supplies a consistent snapshot.
`MANIFEST.json` records byte count and SHA-256 for every other archive member.
The change rows retain the original and proposed JSON plus the resolution.
The ZIP is an export/handoff, not an automatic database restore mechanism.

## Workspace and data handling

The supplied service binds to loopback and is intended for one organizer's
workspace. The exhibitor URL is a scoped presentation of a record, not an
identity or multi-tenant isolation system. This version does not deploy a
public portal or provide separate-user accounts. A link to 127.0.0.1 on this
workspace does not make it reachable from an exhibitor's own device.

No remote analytics, file host, email provider, payment system, or external
calendar is contacted. Original files are stored as SQLite BLOBs and downloaded
as attachments, rather than rendered as active uploaded pages. Per-file size is
1 byte through 8 MiB; HTTP JSON bodies are limited to 12 MiB. Event ZIP generation
uses memory for the complete packet, so plan storage and memory for the event's
asset volume. Large-event throughput is not characterized by the included tests.

Use a separate database path for each customer workspace. Customer databases,
event packets, original files, and contact details belong in the operator's
private storage, not the public source repository. To copy the database, stop
the server cleanly first, then preserve the complete database file. Keep the
original until a copy has been opened and its event records and assets checked.
There is no destructive reset or deletion command in the app.

## API for an existing operator workflow

All write bodies are JSON objects; responses are JSON except named exports.
Saved event/exhibitor records carry `id` and integer `revision`. An edit must
include its `expected_revision`, so concurrent edits produce HTTP 409 instead
of losing a newer save. That is a data-concurrency check, not a user admission
mechanism. Input errors return 400, absent records 404, and a busy database 503.

| Method | Route | Operation |
|---|---|---|
| GET / POST | `/api/events` | List / create events |
| GET / POST | `/api/events/{event}` | Read full event / update event |
| POST | `/api/events/{event}/exhibitors` | Add exhibitor |
| GET / POST | `/api/events/{event}/exhibitors/{exhibitor}` | Read scoped record / update requirements |
| POST | `.../{exhibitor}/changes` | Request change: `{expected_revision, proposed, reason}` |
| POST | `.../{exhibitor}/changes/{change}` | Resolve: `{decision: "apply" or "dismiss", resolution}` |
| POST | `.../{exhibitor}/assets` | Store `{filename, kind, base64}` |
| GET | `.../{exhibitor}/assets/{asset}` | Download original bytes |
| GET | `.../{exhibitor}/reminder.eml` | Unsent reminder |
| GET | `/api/events/{event}/floor-plan.csv` | Current requirements handoff |
| GET | `/api/events/{event}/deadlines.ics` | Current deadline/event calendar |
| GET | `/api/events/{event}/packet.zip` | Complete export |

Event fields are `name`, `venue`, `starts_at`, `deadline_at`, and `brief`.
Exhibitor fields are `company`, `contact_name`, `email`, `booth_code`, `width_m`,
`depth_m`, `power_w`, and `notes`. A proposed change supplies a full exhibitor
field object; absent required values are not invented. The focused tests
include runnable API examples using only synthetic data.

## Checks and observed scope

```sh
PYTHONWARNINGS=error::ResourceWarning python3 -B -m unittest -v test_app.py
node --check desk.js
```

The initial completed focused run passed **34/34 tests in 2.148 seconds**,
including real loopback HTTP, SQLite restart, concurrent save conflicts, stale
changes, booth collisions, exact binary download, retained asset versions,
current-deadline exports, and archive member hashes.

An optional development-only Chromium/Playwright check is provided:

```sh
python3 -B browser_check.py --chromium /usr/bin/chromium --output /tmp/exhibitor-dom
```

It loads the actual HTML/JavaScript into an in-memory Chromium document, maps
`fetch` to the real temporary SQLite Store through a test binding, and supplies
the portal query in the test harness. **18/18 checks passed in 4.561 seconds**:
forms, upload bytes, proposal/resolution, current deadline, scoped export links,
fresh-document reconstruction, and 1440px/390px layouts. Screenshots were
visually reviewed. This is DOM/Store integration, not native browser HTTP,
reload-origin persistence, or browser download coverage. The container's native
Chromium local-page navigation returned `ERR_BLOCKED_BY_ADMINISTRATOR`; that
restriction was not changed. The separate unittest suite exercises actual HTTP.

No live event, external message delivery, public deployment, customer acceptance,
paid subscription, or revenue is established by these synthetic workflows.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
