# Download a finished Lantern leaderboard

This is an additive operator workflow for the existing Lantern application and
SQLite database, not another event store or scoring engine. It uses `Store.state`
for the native event phase and competition ranks, including ties and players who
submitted no answers. It does not finish events or change their records.

## Download from the event page

After an event finishes, its **Leaderboard** section offers **Download CSV results**
and **Download JSON results**. They also appear for events with no participants.
The links are absent for scheduled/open events; direct premature requests receive
HTTP 409 with a JSON error and do not end the event. Event URLs and participant
reconnect behavior stay unchanged.

The same downloads are available at these read-only routes:

- `GET /api/events/{event_id}/results.csv`
- `GET /api/events/{event_id}/results.json`

Successful responses use an attachment filename of `lantern-results.csv` or
`lantern-results.json`, a matching content type, and `Cache-Control: no-store`.
Participant references are not needed or added to download links. Unknown events
return the application's normal JSON 404. The download remains available after
restarting Lantern with the same database.

## Export from an existing workspace

Run beside `app.py` in `revenue/hive_community_events` using Python 3.10 or newer:

```sh
python -B results_export.py --db /path/to/events.sqlite3 \
  --event EVENT_REFERENCE --format csv --output leaderboard.csv
python -B results_export.py --db /path/to/events.sqlite3 \
  --event EVENT_REFERENCE --format json --output leaderboard.json
```

Replace `EVENT_REFERENCE` with the event reference in its Lantern URL or event
list. The database must already exist. Finish through the existing application,
or let the scheduled end pass. Scheduled/open events fail without creating an
output file. Unknown events preserve the application's not-found behavior.
Existing output paths are never replaced; choose a new filename for a later copy.
Exit status is 0 on success and 2 on a handled input/storage/output error.

The database is opened with SQLite `mode=ro` and `query_only=ON`. The exporter does
not initialize schemas or write event data. It reads committed WAL changes, not
pending transactions; SQLite may still use its ordinary WAL coordination files.
Keep the application's database and any live WAL files together.

## What is in the downloads

JSON is UTF-8 with schema `lantern.results.v1`. It contains public event metadata,
the participant count and the final leaderboard. Names and metadata are retained
exactly as stored by Lantern. Export timestamps are deliberately absent, so an
unchanged finished event has identical output bytes across repeat exports.
The `ends` value is the scheduled end, not a fabricated manual-finish timestamp.

CSV is UTF-8 with a BOM and CRLF records. Its columns are:
`event_id,event_title,room,rank,display_name,points,answered`.
It preserves native ordering and tied ranks such as 1,1,3; same-name participants
remain separate rows. An empty event produces a header-only CSV; use JSON to keep
that event's metadata as well. Quoted commas, quotes and multiline names round-trip.
Common formula-like text prefixes receive an apostrophe in CSV for spreadsheet
use. That transformation is intentional; JSON is the lossless text alternative.

Neither format exports participant reconnect references, personal answer rows,
question text, answer keys or unrelated events. Names and scores are still
participant information: retain/share downloads only for the community's intended
purpose. They are unencrypted and are not anonymized or verified identities.

The writer stages a complete file and publishes it with a same-filesystem hard
link. An existing file, directory or dangling link causes refusal, including when
another writer wins a race. Staging files are removed after success or failure.
A filesystem without hard-link support returns an error; there is no fallback
that could replace an existing file. This is atomic visibility, not a promise of
power-loss durability or a multi-file transaction.

## Application integration

An existing route can call `export_bytes(store, event_id, "csv")` or `"json"` and
send the returned bytes with `text/csv; charset=utf-8` or
`application/json; charset=utf-8`. `results_document` returns the allowlisted
Python object. Neither API mutates the supplied store. The native `Problem(409)`
means results are not final. Lantern's two GET download routes consume this
function directly. Their error handling also works when `app.py` is launched as
`__main__`, rather than imported by a test or another application.

## Focused acceptance

```sh
PYTHONWARNINGS=error::ResourceWarning python -B -m unittest -v test_results_export.py
PYTHONWARNINGS=error::ResourceWarning python -B -m unittest -v test_results_download.py
```

The export suite uses the actual Lantern Store, SQLite transactions and WAL,
fresh CLI processes and filesystem operations. The download suite starts the
actual `python app.py` server process and covers HTTP attachment bytes/headers,
unfinished-event JSON errors, Unicode, event separation and restart persistence.
Four optional Node.js tests execute the page's real `render()` function against
an explicit DOM fixture and fetch the generated links through the native server.
Those are JavaScript/HTTP integration checks, not real-browser layout or download
acceptance. Node.js is needed only for those tests, not to run Lantern.
No live community data, hosted deployment, external platform or paid service is
claimed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

