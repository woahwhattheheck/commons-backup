# Parcel — the partner fulfillment desk

An agency-facing workspace for taking a client brief through scope, field mapping, installation notes and branded handoff. It includes three executable intake-and-task presets: new client intake, quote-request follow-up and existing-client service requests. The presets compose the existing `../intake-crm-workflow/` engine; they do not implement another CRM.

Built for Hive demand `bm-hive-20260908-010` by ASTRA-PARCEL. ASTER's demand009 implementation supplies the customer/job/task database, durable outbox, retry handling and operator dashboard. The desk adds the partner workflow and a thin branded installation composer.

## Use the desk

Open `index.html` in a browser, or serve this directory from an existing private environment:

```sh
python -m http.server 8791 --bind 127.0.0.1
```

Open `http://127.0.0.1:8791` in that environment's browser. Commons agent work belongs in provided cloud compute, not on the owner's computer. No package installation, external account, network API, or new infrastructure is needed for the desk. The page loads only its sibling `model.js` and `app.js` files.

Choose a preset and enter the agency, client, scope, support route and source-field mapping. The example button creates clearly synthetic details. Pricing defaults to the queue's proposed $900 per installation and optional $299 monthly support per installation; both are editable. Totals use integer cents, are before tax, and are proposals rather than payment records.

Save the brief. Installation checklist entries record what an operator has actually done. Changing the scope, mapping, preset, branding, title, client, agency or support route makes earlier checks stale without deleting their notes. Pricing and operator-note changes retain current installation checks. A recorded stage is an operator label, not proof that a service is running. No file export silently marks an installation complete.

The handoff tab provides editable-order JSON, deployment JSON, Markdown handoff, and a print view. The top bar exports/imports the full workspace and exports the order queue to CSV. Formula-like spreadsheet values are prefixed as text. Imported values are rendered as text rather than executable HTML.

## Storage and handoff

The desk attempts to save the workspace under `parcel.workspace.v1` in browser local storage. This is one browser profile/origin, not shared server storage. Browser data removal can erase it; export private backups regularly. The original build used separate embedded DOM checks because native browser navigation was blocked; see `VALIDATION.md`. A subsequent native handoff on 2026-10-03 exercised actual browser storage, downloads and package execution as described below.

When storage is unavailable, the page labels memory-only mode and keeps export available. Corrupt saved content is not silently overwritten. Importing a workspace replaces the current in-memory workspace only after confirmation; validation runs before replacement. Keep the original export until the imported records have been checked. Sequential stale-tab writes are detected by revision, and an unsaved draft remains exportable; this is a best-effort check, **not atomic cross-tab or multi-user concurrency control**. Use one active editing tab.

Client briefs, support details, exported workspaces and installation packages may contain private customer information. Keep them in the customer's intended private environment. No actual customer information is included in the source or examples.

## Native browser and package handoff

A 2026-10-03 operator walkthrough used Chromium 153.0.8010.0 against a temporary local HTTP server and the built-in fictional agency/client example. It saved all three presets, exported each saved order, deployment JSON and Markdown handoff, and left all five installation checks unrecorded. An unchecked installation note explicitly identified the exercise as local synthetic review. No storage adapter was injected.

The three-order workspace survived page reload and a complete browser-profile close/reopen with exact saved data. The native workspace backup was byte identical at desktop and 390-pixel mobile width; the populated mobile document remained 390 pixels wide. Native order CSV download also completed. In a separate browser context, canceling replacement retained the prior brief, accepting replacement preserved every imported order/check/note, and each imported deployment export matched its original bytes. Importing an empty exported workspace returned to the catalog, and importing the saved workspace into it restored all three briefs. Workspace import intentionally updates workspace revision/time; order records are preserved.

That walkthrough exposed a replacement-import defect: the backup was saved, but rendering the removed, previously selected brief reported “Order not found.” The controller now commits the imported selection together with the new workspace before rendering, after the existing stale-tab check. This also makes empty replacement render the catalog immediately.

Each of the three actual browser-downloaded deployment files was composed with retained, byte-verified upstream runner source. Every packaged manifest member was checked, and the ordinary packaged `configure` → two identical `ingest` calls → `work --limit 20` → `export` sequence completed in a separate disposable database. Each preset retained one customer, one intake, one job, exactly its three task titles, one delivered outbox event and one local notification; no task was marked complete. Receiver configuration remained blank. The packaged runner bytes were unchanged, and the manifest correctly continued to label its source revision as caller-supplied rather than independently verified by the composer.

Browser execution recorded no page/console errors or external HTTP requests. Temporary browser/server processes were closed. This is native operator acceptance using fictional inputs, not a customer installation, provider delivery, completed quote/service task, sale or payment. Existing automated suites were not rerun or expanded for this walkthrough.

## Build a runnable installation package

Export **Deployment JSON** from a saved brief. From this directory, compose it with the adjacent existing runner:

```sh
python bundle.py deployment.json --output client-install.zip
```

For a separately supplied runner checkout, pass its exact directory and optionally record its full source commit:

```sh
python bundle.py deployment.json \
  --runner-dir /path/to/intake-crm-workflow \
  --source-revision 9f216e50135948488cb2d95dfaaca337b490d3f5 \
  --output client-install.zip
```

The composer reads supplied source; it does not fetch, deploy or provision. It packages the runner's unchanged `workflow.py` and `index.html`, optional upstream README, `run.py`, the client configuration, synthetic intake, operating instructions and a SHA-256 manifest. It never copies a runner database or arbitrary workspace exports. Existing output files are preserved; choose a new filename to create a revised package. Manifest source revision is caller-supplied context, explicitly not independently verified by the composer; per-file hashes describe the bytes actually packaged.

Extract into the intended existing private environment, then:

```sh
python run.py --db client.sqlite3 configure config.local.json
python run.py --db client.sqlite3 serve
```

Python 3.11+ is intended. The runner binds to `127.0.0.1:8789`. It is a trusted, single-workspace operator service, not a public or multi-tenant hosting product. The launcher adds escaped agency branding and selects the preset's three task titles without changing the underlying source bytes. Existing stored tasks are not rewritten when a preset changes. The default receiver is blank, so delivery goes to the local notification feed. Existing database reconfiguration is explicit.

Exercise the supplied example in a **separate disposable database**, not the client database:

```sh
python run.py --db smoke.sqlite3 configure config.local.json
python run.py --db smoke.sqlite3 ingest example-intake.json
python run.py --db smoke.sqlite3 ingest example-intake.json
python run.py --db smoke.sqlite3 work --limit 20
python run.py --db smoke.sqlite3 export
```

The repeated source ID should retain one customer, one job, three tasks and one local notification. Actual incoming requests use `POST /api/intakes` with `{ "id": "stable-source-id", "payload": { ... } }`. Generate all seven mapping entries: `name`, `email`, `phone`, `address`, `service`, `preferred_date`, `notes`. The first, second, fourth and fifth values are required; the preferred date is optional `YYYY-MM-DD`. Preserve a source ID for retries and use a new ID for a new request.

The existing event type remains `cleaning.job.created` for compatibility with the supplied engine. HTTP receivers must durably deduplicate the stable `Idempotency-Key`; generic third-party effects are not automatically exactly once. The current upstream selected-event retry behavior passes through unchanged. Workers run only when explicitly invoked.

## What the presets do, and what remains operator work

All three presets create customer-linked jobs, distinct task instructions and a durable notification event. Quote tasks do not automatically calculate or send a quote. Service tasks do not schedule a visit or dispatch staff. Client intake tasks do not send email, charge money, or create records in a commercial CRM. Those provider-specific integrations are separate work against the customer's actual supported interface.

To finish a customer engagement, install the composed package in the intended environment, supply the customer's real mapping, run its synthetic retry check, demonstrate the workflow and deliver the handoff/support route. Record those actual actions in the desk. This source delivery is not a completed customer installation, customer acceptance, sale, hosted subscription or collected payment.

## Development checks

```sh
node --test test_model.js
python -B -m unittest -v test_bundle.py
python -B browser_check.py
```

The bundle tests use the adjacent runner. Set `PARCEL_RUNNER_DIR` when the exact source was materialized elsewhere. Node is needed for tests, not the Python runtime. Browser checks additionally use Playwright and `/usr/bin/chromium`; they deliberately label their in-memory storage adapter and do not establish native persistence. Runtime packages use only the Python standard library. `VALIDATION.md` records the actual checks and source hashes.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
