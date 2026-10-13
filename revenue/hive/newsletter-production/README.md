# Pressroom: newsletter production workspace

Hive demand `bm-hive-20260908-025`. Turn an authorized interview into a saved,
editable four-issue month, reader previews and an unsent delivery handoff. This
is the production workspace, not a subscriber platform or an automatic writer.

## Run

No third-party runtime packages are needed. Tested with Python 3.13.5 and its
standard-library SQLite implementation in the provided cloud container.

```sh
cd revenue/hive/newsletter-production
python press.py --db newsletter.sqlite3 --port 8765
```

Open `http://127.0.0.1:8765` in your browser. Keep the terminal running. The server
binds only to loopback; use it as a trusted operator's local workspace, not a
public or multi-tenant service. It has no login, role separation, subscriber
store, payment rail or external integration. The client labels organize records;
they are not access-control boundaries.

`newsletter.sqlite3` holds projects and every saved revision, including original
interview text. Stop the app before copying the database for backup. Use a
persistent writable database location; deleting the database deletes the saved
work. Export ZIPs contain content and project metadata, not the full history DB.

## Complete a month

1. Open the fictional sample, or enter a client, title, first issue date and your
   own authorized interview. A `.txt` file can populate the interview field.
   Separate at least four topics with blank lines. The first line of each topic
   becomes a subject; the remaining text becomes editable copy. Extra topics
   are distributed across the four issues without inventing missing facts.
2. Edit each week's subject, body, source IDs and intended UTC handoff time. Set
   the brand name, accent and footer, and retain research questions in notes.
   Save a revision to update the actual HTML reader preview. Original interview
   bytes remain in the project; edit working source sections rather than erasing
   that original. Existing source references accompany every issue.
3. Compare copy with its source and mark each review complete. Review is an
   operator statement, not automated fact checking. Copy, source, brand or date
   changes invalidate the affected reviews; a notes-only edit does not. Duplicate
   subject/body/schedule values also keep the reviewed handoff unavailable.
4. Download the draft ZIP at any time, or the reviewed handoff after all four
   reviews. Reopen from the saved-workspace selector to continue another day.
   Revision links expose read-only historical snapshots; a stale save returns a
   conflict instead of overwriting another operator's revision.

The sample is original **fictional training material** about editorial handoffs.
It does not represent a real expert interview, customer, endorsement, measured
business result, sale or subscription. The four sample issues cover intake,
production queues, revision comparison and delivery handoff. Real customer
interview production remains a separate fulfillment step.

## Delivery files, not remote sends

Each ZIP includes `week1.html` through `week4.html`, four text versions,
`workspace.json`, the unchanged `original-interview.txt`, `schedule.csv`,
`editorial-calendar.ics`, `HANDOFF.txt` and a file-hash manifest. The four calendar
entries are tentative editorial reminders. Neither the ZIP nor calendar creates
send jobs. Every manifest and schedule keeps `delivery_status: NOT_SENT`.

Import the reviewed HTML/text into the client's existing email platform. Check
its sender configuration, required footer and unsubscribe merge tags, audience
preferences and intended UTC times there. Preview and schedule there under the
client's instructions. This app neither reads that platform nor confirms an
import, scheduled send, delivery or customer acceptance. It makes no external
network call from its Python runtime.

The existing export now also calls WREN-MIME's unchanged `email_handoff.py`
component and adds its 16 files under `email-handoff/`, for 30 files total. It
includes four editable multipart `.eml` drafts, four exact body-plus-footer text
files, four fallback HTML previews, a neutral campaign CSV, source metadata and
an unsent manifest. The original branded HTML/text files stay at the ZIP root.
The helper's conservative HTML template is not the editable brand template;
publication name and footer are carried into the email handoff. Source metadata
binds this export to its project, saved revision, source IDs and source hashes.
See `EMAIL_HANDOFF.md` for the component contract and mail-client limitations.
No sender, recipient, Date or Message-ID is invented. The draft hint does not
substitute for a platform's own send controls.

Preview URLs honor the exact saved revision selected by the editor. Both UI
export links carry the displayed revision, and the server rejects a stale pin
with HTTP409 instead of silently downloading newer copy. An unpinned API export
still selects the latest stored revision. Invalid, blank or repeated revision
parameters return HTTP400.

## Check

```sh
python -W error::ResourceWarning -m unittest -v test_press test_press_handoff
python -m py_compile press.py test_press.py test_press_handoff.py
```

The core panel has 24 passing tests, zero skips: actual temporary SQLite
persistence/reopen/history, simultaneous saves, stale revision rejection, source
review invalidation, shape/date errors, byte-inspected ZIPs and real loopback
HTTP routes. Connection contexts commit/roll back and close explicitly.
Ten additional consumer/revision methods exercise the real peer exporter,
multipart drafts and exact component bytes, source metadata, outer ZIP hashes,
unchanged peer source, historical previews and stale/invalid HTTP exports.
WREN's independent 18-method component result is accepted, not rerun here.

The browser script's JavaScript syntax was checked with Node. Desktop and
390-pixel mobile layouts were rendered offline with fixture-backed DOM data and
actual generated preview HTML; the mobile document had no horizontal overflow.
**Browser-to-server integration was not verified:** this cloud environment
returned `net::ERR_BLOCKED_BY_ADMINISTRATOR` for Chromium localhost navigation.
Offline rendering and the separate HTTP tests are not represented as browser
end-to-end evidence. No hosted, full-repository or deployed-service pass is
claimed.

## Interface for composing existing tools

`Store(database)` exposes `create(intake)`, `get(id, revision=None)`, `listing()`,
`history(id)` and `save(id, expected_revision, document, review=None)`. `get`
returns an ID, revision, document, review-needed messages and `NOT_SENT` status.
A document's four issues have `id`, `subject`, `body`, `scheduled_utc`,
`source_ids` and an internally controlled `reviewed_hash`. Brand fields are
`name`, `accent` and `footer`. `export_package(view, ready=False)` returns ZIP
bytes. Do not treat input-provided review hashes as authority; `Store.save`
retains or invalidates only previously recorded reviews.

The HTTP routes mirror those operations under `/api/projects`, with previews
at `/preview/{id}/{week1..week4}` and ZIPs at `/export/{id}?ready=1`. Errors are
JSON: malformed input 400, missing project/route 404, stale or unreviewed handoff
409, storage failure 503. This is a bounded single-operator prototype; deployment,
provider adapters, subscriber processing and actual customer work are not
included in the delivered scope.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
