# Hive Copy Desk

A runnable, standard-library Python workspace for a copywriting operator. Collect customer briefs, keep a source-linked brand library, work one request at a time per customer, preserve editable revisions, and export the delivery as files. The interface is included; no build step, external model, email service, or package installation is required.

## Run

From this directory, with Python 3.10 or newer:

```sh
python3 server.py --db copy-desk.sqlite3 --demo
```

Open `http://127.0.0.1:8765`. The optional `--demo` flag loads six finished sample documents for the existing Commons purchasing-paperwork operator and a second queued request. Restarting with the same database and flag reuses the recorded example operations rather than duplicating them. Without `--demo`, start with an empty workspace. Database files are runtime data and should not be committed.

`--db`, `--host`, and `--port` are configurable. The default host is loopback. All people reaching a running instance share its complete operator view; customer grouping is organization, not tenant isolation. This is not a separately deployed customer portal. The browser requires modern JavaScript and a secure context (localhost or HTTPS) for operation IDs.

## Complete the sample workflow

The seeded request starts in review with `landing-page.md` and five distinct email drafts. Open a document, edit its source, enter a revision note, and save. To demonstrate a revision cycle, enter feedback, choose **Request revision**, edit the copy, and save another version. Every saved draft retains its original files, selected claim IDs, brand/source snapshot, brand version, timestamp, and revision note.

Choose **Export editable ZIP** to receive `current/` files, all `revisions/`, and `request.json` with source snapshots. Choose **Mark delivered & start next** to complete the local request and start the next queued item for that customer, ordered by priority and then arrival. Delivery is a local workflow status: no file is emailed, no page is published, and no customer acceptance is asserted. Cancelling a request releases its production slot but leaves the next start manual.

Create a new customer with its voice and claim library before adding a request. Claims use this structure:

```json
[{"id":"offer","text":"The actual supported product behavior","source":"A document, file reference, or source URL"}]
```

Sources are editorial context, not automatic verification. Drafts explicitly select claim IDs. Updating a brand preserves prior snapshots and requires an updated draft before a current review can be marked delivered. This prevents silently delivering an older source version; it does not assess whether the copy is true or stylistically appropriate.

## Persistence and concurrent edits

SQLite stores clients, requests, immutable draft versions, and write receipts. A partial unique index permits only one active, review, or revision request per customer. Transactions serialize starts and delivery/next-item promotion. Different customers can have work in progress concurrently. Version checks reject stale writes rather than overwriting another edit.

Each JSON mutation includes an `operation_id`. Repeating the exact operation and payload returns its original result without another mutation, including after reconnect or process restart. Reusing the ID with a different payload is rejected. The browser retains an unacknowledged payload in that tab's session storage and offers **Retry pending edit**. Do not change a payload when retrying it. Unsubmitted editor changes are not saved until **Save draft for review**; save them before changing requests or leaving the page.

To copy a workspace, stop its server and copy its SQLite database. Keep that database private to the intended operator environment. No runtime customer data is included in this source package.

## API

`GET /api/state` returns the shared workspace. `GET /api/export/{request_id}` returns its ZIP. JSON POST endpoints are:

- `/api/client/create` and `/api/client/update`: `name`, `voice`, `claims`; update also takes `id` and `version`.
- `/api/request/create`: `client_id`, `title`, `kind`, `brief`, integer `priority` from 0 to 100.
- `/api/draft/save`: request `id`, `version`, `files` mapping filenames to text, `source_ids`, and `note`.
- `/api/request/action`: request `id`, `version`, and `action` (`start`, `priority`, `revise`, `deliver`, or `cancel`). Priority takes `priority`; revise takes `feedback`.

Every mutation also takes a unique `operation_id`. Filenames are simple `.md` or `.txt` names; exports never use client-supplied directories. A draft contains 1–20 nonempty documents. An example API client can use the imported `Desk` class directly for local integration; the HTTP boundary uses the same implementation.

## Finished copy sample and source

`example.json` contains the actual editable sample, not generated placeholders: a landing page plus five emails covering introduction, normalized inputs, discrepancy follow-up, review handoff, and next steps. The product exists at [`revenue/hive/purchasing-paperwork-operator/`](../purchasing-paperwork-operator/). All four sample claim groups reference its [pinned README](https://github.com/woahwhattheheck/commons/blob/87d704a55dfef6964a41034ae08750fc922fe7d8/revenue/hive/purchasing-paperwork-operator/README.md), blob `cad0e29d0e3846fe368edfb8881eea6527170dbe`.

The copy describes normalized CSV intake, exact vendor/line matching, discrepancy drafts, source references and review-ready accounting CSV. It does not claim OCR, automatic email, accounting-system posting, discrepancy approval, purchases, payment execution, measured savings, testimonials, or guaranteed outcomes. Square-bracket claim IDs are editorial references for the operator. The emails are unsent source documents, not a mailing campaign. Product pricing and service terms are left for the actual offer owner.

This is the implementation and first finished sample for Hive demand `bm-hive-20260908-030`. An actual customer commission, customer acceptance, subscription sale, and external delivery remain separate. The demand's proposed subscription is not an observed sale.

## Validation

```sh
python3 -W error::ResourceWarning -m unittest -v test_desk.py
python3 -m py_compile server.py test_desk.py
```

The initial delivery passed 27 tests with real temporary SQLite files, concurrent threads, process-style database reopen, ZIP readback, and a real HTTP server/client. They cover one-active-request enforcement, next-item ordering, immutable revisions, changed-brand handling, stale edits, retry safety, malformed data, example loading, and transport errors. Browser JavaScript also passed `node --check` when extracted from the inline script.

The original system-Chromium run was blocked before local navigation. A later operator handoff on 2026-10-03 used ordinary loopback navigation in Chromium 153.0.8010.0 and completed FEN-COPY's retained `--demo` workflow. All six seeded source documents matched `example.json`. Two explicit editorial saves, with a revision request between them, produced three immutable revisions while retaining the original draft and every brand/source snapshot. The browser's 26-member editable ZIP retained all six current documents, all eighteen historical documents, delivery notice and exact request snapshot; its member contents matched the native `Desk.export` output. ZIP container timestamps are incidental and are not an exact-byte export contract.

Marking local delivery changed the first request to `delivered` and promoted the retained queued request to `active`. Restarting the process with `--demo` preserved the exact workspace without duplicating the seeded operations. Desktop (1280 × 900) and mobile (390 × 844) layouts were inspected; the populated mobile document remained 390 pixels wide. This handoff fixed the shared-workspace badge's pale-on-pale text and dark header links through scoped header colors; runtime, example and inline JavaScript stayed unchanged. Browser execution recorded no page/console errors or external requests, and its temporary server/browser were closed. No new test suite, dependency, customer commission, email send, provider write, deployment or customer acceptance was involved.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
