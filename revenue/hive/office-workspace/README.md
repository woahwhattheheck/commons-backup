# Office workspace

Runnable first version for Hive demand `bm-hive-20260908-015`: meeting-to-task capture, source-linked document retrieval, and editable client-email drafts. No paid dependency or model key is required.

## Run

Use Python 3.10 or later. Keep the database outside the repository and in a private directory.

```sh
python revenue/hive/office-workspace/app.py --db /path/to/private/office.sqlite3 --port 8765
```

Open `http://127.0.0.1:8765`. The server binds to loopback only. It has no login, no external network client, and no email-send or task-provider endpoint. This version is for one authorized operator, not a public multi-user service. Client workspace separation prevents accidental cross-client operations; it is not authentication. Do not expose the port or put real client data in Git.

## Complete a sample workflow

1. Create a client workspace, using synthetic data for a first walkthrough.
2. Import a meeting using a stable source key such as `meeting-2026-09-08`. Paste an authorized text export, or choose a UTF-8 `.txt` or `.md` file:

```text
Sample meeting; synthetic people and tasks.
ACTION: Jordan | 2026-09-15 | Collect signed checklist
ACTION: Casey | - | Review onboarding notes
```

Only explicit `ACTION: owner | date | description` lines create tasks. `-` means the source does not record a due date. Ordinary notes do not produce inferred assignments. Malformed action lines reject the entire import rather than creating a partial task list.

3. Mark one task done. Repeat the identical import: source and task IDs remain unchanged. Import changed text under the same key: a new source version is retained, completed unchanged tasks stay done, and removed actions become superseded history. Simultaneous conflicting edits return a reload message rather than silently replacing a newer version.
4. Import a document under another stable key:

```text
Welcome procedure
Onboarding requires a signed checklist.
```

Search for `onboarding checklist`. Each result contains an exact line, source title, line number, version, and a working internal link to that source version. Search is keyword retrieval, not a language model: matching lines may be incomplete or irrelevant and must be read in context. Only current document versions are searched; old cited versions remain readable. A query with no matches returns an honest gap, not a generated answer.

5. Prepare a draft from current open tasks, enter the intended client's email address, review and edit the text, and save. Reopen it, edit again, and export `.eml`. The file has `X-Unsent: 1`; this application never sends it. Confirm the recipient and selected mailbox when importing it into an email client.
6. Export current tasks as CSV for review or import into the firm's existing task system. Spreadsheet-formula-like fields are prefixed with an apostrophe in this human-opened export. The original source text remains unchanged.

Switch to another client workspace: sources, tasks, citations, and drafts remain separate. The draft editor clears when switching clients. Refresh before editing from another tab; task/draft writes require the revision that was read.

## Connector-export adapter contract

This first version consumes user-provided exports. No live Gmail, calendar, task, document, or model integration is claimed. An existing authorized adapter can POST JSON to the local API:

- `POST /api/workspaces`: `{ "name": "Example client" }`; returns `id`.
- `POST /api/import`: `workspace_id`, `source_key`, `title`, `kind` (`meeting` or `document`), `text`, and `expected_version` (0 for a new key, the observed current version for a changed source). An identical retry returns the existing version even when its expected version is older. A differing stale import returns HTTP 409. Keep the source key stable and review meeting action markers before import.
- `GET /api/workspace?workspace_id=...`: current sources, all task history, and unsent drafts.
- `POST /api/ask`: `workspace_id`, `question`; returns exact `citations` or `no_answer`.
- `GET /api/source?workspace_id=...&source_id=...&version=...`: the immutable cited source version.
- `POST /api/task`: `workspace_id`, `task_id`, `revision`, `state` (`open` or `done`).
- `POST /api/draft`: `workspace_id`, `recipient`, `subject`, `body`; add `draft_id` and `revision` when editing. New-draft callers can provide a stable `request_id` (1–200 characters) for retry safety. The same client/key and same normalized recipient, subject and body reuse the existing draft, including after a restart; `repeated: true` reports this. Reusing the key with different contents returns HTTP 409 without writing. Replays never revert later edits and return the latest saved revision; reload that draft before editing. Different clients or different keys are independent. Omit the key only for legacy non-deduplicated creation; edits must use `draft_id`/`revision` without `request_id`.
- `GET /api/export?workspace_id=...&kind=tasks`: current-task CSV.
- `GET /api/export?workspace_id=...&kind=draft&draft_id=...`: unsent EML.

The browser retains one creation key for the active new-draft form and reuses it after a failed response; choosing New blank draft, preparing a new template, switching clients, or reloading the page creates a new key. After a page reload, reopen the saved draft rather than resubmitting a new form. The server retains request receipts in SQLite. Existing databases gain this table without rewriting saved drafts. Changed-content retry conflicts preserve the input for review; reopen the saved draft or explicitly start a new one.

Bodies are limited to 1 MiB; imported text and draft bodies to 100,000 characters. HTTP errors return JSON. Unknown or cross-client record IDs return 404. Stale revisions return 409. All persistence uses SQLite transactions and parameterized values. Provider adapters must not treat a local task or draft save as a remote installation or delivery receipt.

## Migration and staff walkthrough

Choose the firm's three agreed workflows and an authorized sample client. Export meeting notes and current procedure text through its existing tools, remove unrelated client information, assign stable source keys, and import using the sample steps above. Compare the resulting assignments and source citations with the original exports. Review the unsent EML in the correct client workspace. Configure and test any real provider adapter separately with its actual permissions; none is installed by running this sample.

The proposed queue offer was a fixed installation for three workflows. This code is not a customer acceptance, a completed installation, a purchase, a price commitment, or a delivered email. Actual provider installation and staff walkthrough remain customer-specific work.

## Verification

```sh
python revenue/hive/office-workspace/test_app.py
# From the Commons repository root, the same suite is exposed to its battery:
python test_hive_office_workspace.py
```

Twenty-five tests use real temporary SQLite databases, concurrent workers, and a live loopback HTTP server. Coverage includes persistence, duplicate and conflicting imports, rollback, task history, current-source citations, no-answer behavior, client isolation, stale edits, CSV safety, unsent EML export, durable request replay, sixteen-way concurrent draft creation, conflicting retry payloads, and additive database migration. No mocked storage or provider calls are used.

The implementation session also checked JavaScript syntax with Node. An interactive Chromium walkthrough was attempted, but local navigation returned `net::ERR_BLOCKED_BY_ADMINISTRATOR`; browser interactions and responsive rendering are therefore **not verified** by this delivery. HTTP workflow tests passed independently. No whole-repository or hosted-CI pass is claimed.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
