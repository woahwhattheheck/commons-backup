# Lantern calendar handoff

Download one community event, a room's schedule, or all events as iCalendar.
The calendar page links back to Lantern's existing event view. This is an
additive companion to ASTRA-LANTERN's app, not a second game service.

## Run the existing app with calendars

Python 3.10 or newer; standard library only. From this directory:

```sh
python3 calendar_feed.py serve --db /existing/private/cloud/events.sqlite3 --port 8765
```

Use the same persistent database as the original app. The parent directory must
already exist. As with `app.py`, `serve` initializes a new database when the named
file does not exist; check the path when resuming an existing community.
The default bind address is `127.0.0.1`. `--host` and `--port` are explicit options;
this command does not provision hosting or change a community-platform account.

Open `http://127.0.0.1:8765/calendar`. The same process serves the original app at
`/`, its existing `/api/events` routes, and these additional GET/HEAD routes:

| Route | Result |
| --- | --- |
| `/calendar` | Event cards with open-event, single-event and room-calendar links |
| `/calendar.ics` | Whole published schedule |
| `/calendar.ics?room=Chess%20club` | Exact room-name match; use the generated link for Unicode names |
| `/calendar/EVENT_ID.ics` | One event; an unknown ID returns JSON 404 |

Original `python3 app.py` operation is unchanged. There is no schema migration,
replacement UI, extra identity system, game-state mutation or new host control.
The wrapper inherits the original `Store` and `make_handler` interfaces.

## Link a calendar entry to its event

Supply the app's actual reachable root URL when there is an existing deployment:

```sh
python3 calendar_feed.py serve --db /existing/private/cloud/events.sqlite3 \
  --port 8765 --public-url https://events.example.test/
```

The example domain is a placeholder, not a deployed service. An exported entry
then includes an event-specific `URL` ending in `/?event=EVENT_ID`, consumed by
Lantern's existing page. Omit the option for local-only exports without an
advertised URL. The option accepts an absolute HTTP(S) app-root URL without
userinfo, query or fragment. It is validated locally and never fetched.
UIDs do not change when the host, port, storage location or advertised URL changes.

## Download versus subscribe

A downloaded `.ics` file is a snapshot. A calendar client that supports URL
subscriptions can subscribe to the whole-calendar or room-calendar URL instead.
That client must be able to reach the running server; its own refresh policy
controls when it fetches newly created events. GET and HEAD provide content-based
ETags and conditional 304 responses. An empty room returns an empty calendar,
not an error. A storage failure returns JSON 503, not an empty successful feed.

No calendar invitations, email, reminders, provider writes or account connections
are performed by this companion. Import/subscription behavior in a particular
calendar client must be checked with that client; it is not inferred from the
HTTP tests.

## Export without running a server

`export` opens an existing SQLite database in read-only mode. It neither creates
a missing database nor imports the app. It writes UTF-8 calendar bytes to stdout
only; errors go to stderr with exit code 2 and no partial calendar output.

```sh
python3 calendar_feed.py export --db /existing/private/cloud/events.sqlite3 > schedule.ics
python3 calendar_feed.py export --db /existing/private/cloud/events.sqlite3 \
  --room 'Chess club' > chess-club.ics
python3 calendar_feed.py export --db /existing/private/cloud/events.sqlite3 \
  --event EVENT_ID --public-url https://events.example.test/ > one-event.ics
```

Use a separate `.ics` output path, never the database or an existing source file:
a shell opens its redirection destination before Python starts. `--room` and
`--event` are mutually exclusive in the CLI. No external library or network
request is needed for export.

## Data and schedule semantics

Only six columns are read from the existing `events` table in one SQLite
snapshot: `id`, `title`, `room`, `opens`, `ends`, and `created`. Questions, choices,
answer keys, answers, participant references, names and scores are not queried or
exported. Event titles and room names themselves are included; hosts should use
appropriate public schedule text.

The current event API creates an immutable schedule and separately lets a host
finish gameplay. Finishing is not cancellation. Calendar entries remain at their
published times after a finish or normal end, and no cancellation or rescheduling
history is invented. Use Lantern for current game status. Recurring rules,
rescheduling, cancellation broadcasts and future scheduling APIs are not provided
by this extension.

Each entry has a stable event-derived UUID UID, source-created DTSTAMP, UTC DTSTART
and DTEND, escaped SUMMARY and LOCATION, a fixed explanation, and transparent
(non-busy) time. Times have one-second precision: fractional starts round down
and fractional ends round up, so a subsecond slot is not shortened or erased.
The calendar page uses those same rounded UTC times. Exact whole-second times
remain unchanged. Output uses CRLF and folds physical lines at no more than 75
UTF-8 octets without splitting characters. TEXT escaping handles backslashes,
commas, semicolons and newlines.

Format reference: [RFC 5545](https://www.rfc-editor.org/rfc/rfc5545.html), sections
3.1, 3.3.11, 3.6.1, 3.8.2.2, 3.8.2.4, 3.8.4.7 and 3.8.7.2. Read-only database
opening uses the documented SQLite URI `mode=ro` option.

## Run the integration checks

```sh
PYTHONWARNINGS=error::ResourceWarning python3 -B -m unittest -v test_calendar_feed
```

The tests use the actual sibling `app.py` and `index.html`, real temporary SQLite
databases, a loopback HTTP server and CLI subprocesses. They exercise existing
create/join/answer/retry/finish/reconnect behavior through the wrapper; exact
homepage bytes; score and source-record preservation; concurrent game writes;
committed snapshots; restart-stable feeds; room and single-event selection;
conditional GET/HEAD; format boundaries; and CLI failures without partial output.
All example records are synthetic and temporary. This suite needs no browser,
network provider, credentials or customer records.

The publication run passed 47 tests on Python 3.13.5. A separate embedded Chromium
presentation check passed nine checks, including links and widths 320, 390 and
1280, using bytes fetched from the real HTTP handler. Direct Chromium navigation
returned `ERR_BLOCKED_BY_ADMINISTRATOR`; embedded rendering is not native-browser
acceptance. No Outlook, Apple Calendar, Google Calendar or community-platform
installation was performed. No whole-repository CI result is claimed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

