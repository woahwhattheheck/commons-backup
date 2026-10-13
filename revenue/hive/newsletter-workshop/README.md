# Newsletter Workshop

**Hive demand `bm-hive-20260908-031`: a practical workshop with a working deliverable.**

An offline browser/command-line newsletter workflow plus a complete participant
lesson, three self-checking exercises, worked solutions, and a facilitator guide.
The deliverable is a usable issue compiler and teaching kit, not a mock email
service or a slide outline. Standard-library Python 3.10+ runs the product.

## Start the browser workspace

```sh
python newsletter_workflow.py serve
```

Open the printed loopback address. Edit the publication and issue, change
sources/preferences in the full JSON editor, save a portable working file, and
download an edition ZIP. Applied edits are cached in the browser when storage
is available. Import and full-JSON Apply use the same validator as the CLI;
pending invalid JSON remains downloadable without losing the original text.

Read **[WORKSHOP.md](WORKSHOP.md)** for the lesson and exercise walkthrough.
No account, provider integration, model API, email transmission, or payment is
required. `--host` and `--port` can select another listening interface/port;
this development workspace has no multi-user isolation and should not be used
as a shared customer-data service.

## Use the same compiler from the command line

```sh
python newsletter_workflow.py init work/my-newsletter.json
python newsletter_workflow.py validate work/my-newsletter.json
python newsletter_workflow.py build work/my-newsletter.json --out work/edition-01.zip
python -m zipfile -e work/edition-01.zip work/edition-01
python exercises.py prepare work/practice
python exercises.py check 3 work/practice/solution-3.json
```

Output includes `preview.html`, `newsletter.txt`, an editable `workspace.json`,
`delivery-plan.csv`, `source-map.json`, a byte manifest, and one unsent multipart
MIME draft per eligible subscriber. The planned date is metadata only. A current
unsubscribe, pause, or missing topic excludes the record. Duplicate subscriber
addresses are diagnosed case-insensitively; no preference is silently chosen.
CSV addresses beginning with a spreadsheet formula prefix get a leading quote
in the plan only; MIME recipients and original JSON retain their actual values.

The compiler never fetches source URLs. It verifies that each excerpt occurs in
the supplied source text, not that source text or editorial commentary is true.
Review claims and use authorized material. The starter, its sources, recipients,
and events are original fictional lesson material, explicitly labeled as such.

## What this does not do

No messages are sent, no jobs are scheduled, and no provider is configured.
The reply-to unsubscribe text in a draft is not a hosted preference endpoint.
Exports are snapshots: rebuild against current preferences before using an
existing email platform. Real exports contain recipient data and should stay
private; keep them out of public Git. The ZIP includes the complete workspace,
including excluded records, so the operator can continue editing preferences.

There is no claimed real participant completion, paid workshop, customer
installation, live newsletter, or revenue. The queue's proposed workshop/team
prices are offer ideas, not a minted checkout or recorded sale.

## Tests

```sh
python -m unittest -v test_newsletter_workflow.py
```

These exercise the real compiler, filesystem, subprocess CLI, MIME parser,
archives, live HTTP server, input errors, and source/preference behavior. No
external service is substituted for a claimed integration.

Optional browser checks use Playwright and Chromium:

```sh
python test_browser.py
```

Install Playwright and its Chromium browser in your chosen test environment to
run that optional script. `CHROMIUM_EXECUTABLE` can select an existing browser.
The product itself does not depend on Playwright.

## Files

`newsletter_workflow.py` is the compiler, CLI, and local HTTP server;
`workshop.html` is its browser consumer; `example.json` is the original fictional
starter. `exercises.py` creates and checks three exercises and worked solutions.
`WORKSHOP.md` is the participant/facilitator guide. Tests are alongside the source.
Generated ZIPs and the recommended `work/` directory are ignored by Git.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
