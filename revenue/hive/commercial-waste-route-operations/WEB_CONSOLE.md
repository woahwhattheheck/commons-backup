# Commercial Waste browser operator

The browser console exposes the existing waste/container route desk, not the separate laundry product. It uses the same `WasteRouteDesk` methods and SQLite database as `desk.py`. It does not change the manifest, service-date, exception, invoice-line custody, or immutable-draft rules.

## Start

From the repository root, with Python 3.10 or newer:

```sh
python revenue/hive/commercial-waste-route-operations/web_console.py --db /path/to/waste-desk.sqlite3
```

Open the printed address, normally `http://127.0.0.1:8786/`, directly in a current browser. `--port 8790` selects another loopback port; `--port 0` selects a free one and prints it. There is no LAN bind option. No installation, package manager, hosted service, bank account, or API key is needed. An IANA business timezone still requires the host's timezone data, as in the existing engine; UTC and SYSTEM_LOCAL are alternatives at initial setup.

Use the existing database to continue work. A missing database is created by the existing engine. Opening legacy databases runs the engine's existing migration, so preserve a normal database backup before upgrading. Stop with Ctrl-C; the SQLite state remains. Do not copy a live WAL database as a single-file backup or delete its sidecars. This change does not introduce a backup/restore system.

## Complete operator workflow

1. **Initialize once.** In Workspace, choose a retained UTF-8 manifest or paste its original JSON. Or choose/paste the twelve-column recurring-service CSV from [CSV_INTAKE.md](CSV_INTAKE.md), enter the business timezone, and press Preview CSV. Preview is read-only. A valid preview shows customer, site, container, and plan counts and copies the converter's manifest text into the editor verbatim, which can be downloaded. Invalid CSV stays one structural error, including its line when the converter reports one; it does not replace a reviewed manifest or that manifest's download. A non-UTF-8 or over-1-MiB CSV file does not replace the paste box. Review the business timezone, customers, sites, containers, weekdays and integer minor-unit prices, then initialize explicitly. The existing fictional sample can be loaded into the editor for a separate demonstration database; loading it is not an import. The manifest cannot replace an initialized workspace, and that workspace disables the CSV and manifest controls. The console transmits original JSON text to Python, preserving duplicate-key detection and integer precision rather than parsing and reserializing it in JavaScript.
2. **Plan and open a route.** Choose its service date, then Generate planned route or Load saved route. Future dates are planning-only. Saved route history shows the latest 120 dates; any older date remains loadable by date. The desk does not choose an optimized route or dispatch a vehicle.
3. **Record actual service.** Each elapsed pending stop offers Record serviced or an explicit skipped-service exception code. The engine remains responsible for date and terminal-state enforcement. A click is an operator assertion, not independent evidence of real-world service.
4. **Resolve exceptions.** The cross-date queue shows the oldest 200 unresolved stops and the total outstanding count. Other exceptions remain available through their route dates. Choose no service/no charge or actual billable makeup; the latter requires an elapsed date on or after the original service date. No automatic resolution occurs.
5. **Retain invoice drafts.** Enter customer ID and service period. The existing engine rejects missing scheduled stops, unresolved service, future-ended periods, and stops already claimed by another draft. Creating a draft permanently claims its included stops. There is no edit/delete/rebill API. Drafts can be viewed, printed or downloaded; nothing is sent, charged, or marked paid. On narrow screens, the retained digest wraps inside the preview and line items scroll horizontally within their own region. Tab from Print selected draft to Invoice draft line items, then use the arrow keys to inspect the table; the next Tab reaches its JSON download. The latest 100 drafts are listed; any retained ID can be opened directly.
6. **Export and recover.** Download route JSON/CSV/Markdown, exact retained invoice JSON, or the complete native event log. Activity lists the newest 100 events, the full count, and operation keys for lookup. The UI displays all amounts as exact strings in currency minor units; it never assumes a two-decimal currency. Downloaded native JSON preserves the engine's integer numbers. CSV formula-like text is apostrophe-prefixed in the download only; stored source values are unchanged.

## Interrupted requests and retries

A failed HTTP response does not prove a mutation failed. Before submitting, the console creates an operation key and retains the exact request in this tab. Failure exposes that key, an exact-retry button and a recovery-request download. Repeating the same structured request uses the same key and the engine returns its retained result. Different inputs are never quietly sent under an unresolved pending key.

Look up the key in Activity to establish whether it is recorded. A found operation returns its saved result and refreshes the database view. An absent key clears the pending request so the operator can correct the inputs. Retry material may include the original customer manifest: keep its optional download private. The tab's pending request is not persisted in browser storage and is lost on tab close/reload unless downloaded or its key copied. The database's operation/event history remains durable. Refresh the workspace before recording replacement actions from another tab.

If a write succeeded but the following read failed, the notice explicitly says the change was saved. Refresh the view instead of inventing a replacement write. A server restart rotates the local session key; reload the page to resume. Read-only operations do not perform business mutations; schema initialization/migration occurs through the existing engine when the server starts.

## Local boundary and limits

The server binds only 127.0.0.1, validates the exact Host/Origin, rejects cross-site requests, and requires a per-process header token for its API. Browser data is rendered as text, not executable HTML. Assets are local and the page makes no third-party requests. There is no arbitrary file-serving route or caller-selected database path in HTTP. Request bodies are limited to 2 MiB; the file picker limits manifest files to 1 MiB. Requests are served serially through one engine connection. Independent CLI processes still use the engine's existing SQLite writer transactions and idempotency rules.

These are local-browser boundaries, not multi-user authentication or protection from code already running as the same OS user. Do not expose the process through a public tunnel or reverse proxy. This console is not vehicle navigation, a compliance determination, payment processing, accounting advice, or a customer deployment.

## Source and delivery

The addition consists of `web_console.py`, `web_console.html`, `web_console.js`, and this guide. No engine, old test, workflow, dependency, or policy file is changed. Original product lineage remains #14651 / #14581 (ZNS-R8K5, ZOH-V7Q5, ZPBW-K8Q2 and predecessors); console delivery is #19254 by yZ-Basalt-6N4. Implementation publication is not a claim of production customer acceptance, hosted execution, or earned revenue. Runtime execution status belongs in the PR shipping note, not an invented test result here.

## Native operator handoff

The 2026-10-03 continuation exercised the retained fictional manifest in Chromium 153 against the original loopback server and engine: elapsed routes, service and skipped-service recording, blocked invoice recovery by operation-key lookup, explicit no-charge resolution, an immutable 12900 USD minor-unit draft, exact native downloads and database restart. Repeating the draft retained the same invoice and event counts; a future route exposed planning only. The draft and full event downloads survived restart byte-for-byte. This does not assert that real service occurred or that an invoice was sent.

The populated preview exposed a 390-to-544px page overflow; wrapping the digest and making the narrow table a labeled keyboard scroll region restored a 390px page. Desktop pixels and one-page A4 print text stayed unchanged, and the downloaded invoice still matched the exact stored payload. There were no page exceptions, CSP errors, failed transport requests or external requests; the deliberate unresolved-invoice rejection produced the expected HTTP 409 console response. No new project tests or dependencies were added. The already-accepted CSV-preview workflow and all engine, converter, input and accounting semantics remain unchanged.
