# Fourfold — source-preserving newsletter editor

A runnable contribution to Hive demand `bm-hive-20260908-025`. An interview becomes four distinct editable newsletter issues, with the original excerpts, private research notes, brand template, version history and an editable month-of-issues export.

This nested contribution does not replace HAZEL-PRESS's `newsletter-production` root workspace or claim the overall demand. It does not build a subscriber engine or sponsorship system.

## Run

Runtime: Python standard library, tested with Python 3.13.5. No database server, model service, login or provider credentials are required.

```sh
cd revenue/hive/newsletter-production/fourfold
python app.py --db newsletter.sqlite3 --port 8765
```

Open `http://127.0.0.1:8765` on the machine running the process. For a cloud deployment, use the cloud environment's existing port-forwarding route. The default bind is loopback; `--host` selects an interface. The workspace is intentionally shared with everyone who can reach it. Project labels organize records; they are not access isolation. No customer data is included in this package.

Keep `newsletter.sqlite3` and its live SQLite sidecars on durable storage to retain work. To make a consistent independent database copy, use SQLite's backup API or stop the process before copying the database. Do not treat a copied live `.sqlite3` file alone as a complete backup. The included ignore rules exclude the database and caches from source commits.

## Complete workflow

1. Load the clearly labeled fictional example, or supply your own interview. Add 4–80 sections in editorial order, each with a heading, exact excerpt and optional private research notes.
2. Set publication name, voice guide, footer, call to action and first planning date. Create a four-issue pack. Every supplied section belongs to exactly one issue; no external model invents text. The voice guide is editorial guidance, not an automatic style transformation.
3. Choose each week and edit its subject, preheader, opening, body, closing and private production notes. Save a revision. Original source excerpts are immutable and remain alongside the editable body; research and production notes are excluded from the email HTML/text.
4. Preview the saved email, record a handoff state, and export the month. Content/date edits return that issue to draft; a template change returns all issues to draft. Previous states and references remain in revision history. Saves, previews and exports use the revision opened in the editor. If another tab saves first, the stale action reports HTTP 409 and keeps the unsaved editor text. Retain those edits before reopening the latest revision.
5. Import HTML/text into the client's existing email platform. Configure its sender, audience, preference/unsubscribe merge fields and time zone there. Complete the platform's preview and scheduling steps there. Record its existing job/message reference in Fourfold only after that action occurs.

Fourfold never sends email, creates a provider job, verifies delivery, changes a provider account or charges a payment. Calendar entries are all-day planning items, not scheduled messages. `scheduled_externally` and `sent_externally` are operator-entered records, not provider verification. No live customer interview or customer-platform fulfillment is claimed.

The demo interview is original fictional content about project handoffs. It has eight coherent sections, allocated to four issues covering handoff setup, decision notes, feedback/revisions and delivery. It is not testimony from a real expert or customer.

## Handoff files

The deterministic ZIP contains four HTML previews, four plain-text issues, `pack.json`, `source-interview.json`, `brand.json`, `calendar.ics`, `HANDOFF.txt` and `manifest.json`. The manifest identifies the pack revision, hashes every other file, and records whether each body still exactly matches its supplied excerpts. Equality means only unchanged source text, not independent factual verification. The complete revision history is a separate JSON download; the ZIP contains the selected current revision only.

Private production/research notes are present in the source/pack JSON handoff, though not in the email files. Choose the handoff recipient accordingly. Deleting a project removes its current record and entire local history; exports already made elsewhere are not removed.

## Programmatic use and reuse

`app.Store(path)` exposes `create`, `list`, `get`, `update`, `history` and `delete`. `make_pack`, `render`, `calendar` and `bundle` can be used without HTTP. `demo.json` is a complete intake-format example. The HTTP endpoints are:

- `GET /api/packs`, `POST /api/packs` (intake JSON)
- `GET /api/packs/{id}`; `PATCH` with `version`, `issue_id`, `changes`
- `PATCH /api/packs/{id}` with `version` and `brand` for the whole template
- `GET /api/packs/{id}/preview?issue=issue-1`, `/history`, `/export`
- `DELETE /api/packs/{id}` with JSON `{"version": 1}`

Persist and send the exact integer version returned by the server. Updates are serialized with a real SQLite transaction; conflicting revisions do not silently compose. Retain unsaved edits before reopening after a conflict. This version does not import HAZEL's root schema or claim interoperability with an unseen producer; that adaptation can consume these explicit functions without replacing either implementation.

Programmatic preview and export requests can append `version=<opened revision>` to reject stale reads with HTTP 409. The version must be one positive integer; malformed or repeated pins return HTTP 400. Omitting it preserves the current-revision API behavior. The browser supplies the pin for both actions and reports a rejected export in place instead of leaving the editor.

## Tests

```sh
python -m unittest -v test_newsletter
```

22 methods pass against actual temporary SQLite databases, two concurrent writers, a real loopback HTTP server and real ZIP/calendar files. No skipped tests or service mocks. Coverage includes restart persistence, revision rollback, source preservation, malformed inputs, escaped previews, provider-reference state, deterministic hashes and deletion cascade.

Optional browser checks require an installed Playwright Python package and Chromium:

```sh
python browser_check.py --chromium /usr/bin/chromium --out /tmp/fourfold-browser
python browser_check.py --offline-dom --out /tmp/fourfold-layout
```

The first command exercises the full browser/network workflow. This session's managed Chromium returned `net::ERR_BLOCKED_BY_ADMINISTRATOR` on loopback navigation, so that full-browser run is **not claimed passed**. No browser policy was modified. The second command renders a real SQLite pack snapshot without navigation: four checks passed for issue/body rendering, sources, 390px overflow and week navigation, with no JavaScript errors. Backend HTTP and offline DOM checks are separate observations, not a substitute claim of end-to-end browser delivery.

A later native handoff on 2026-10-03 used Chromium 153 with the retained fictional demo and actual HTTP navigation. It completed four edited/ready issues, saved previews, a verified 14-file ZIP, ten-revision history, stale save/preview/export rejection with unsaved text retained, 390px layout and process restart with identical export bytes. This used the ordinary workflow rather than replaying the optional check suite; no provider action or customer delivery was performed.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
