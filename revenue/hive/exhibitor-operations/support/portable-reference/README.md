# Portable exhibitor reference core

Reusable, dependency-free source for the existing [Exhibitor Operations](../../README.md)
product, Hive demand `bm-hive-20260908-046`. This is a supporting component, not a
second organizer application, served page, persistence layer, or deployment.
ASTRA-JUNIPER retains the canonical app and portable-intake integration.

## Run and use

Tested with Node 22.16.0; no package installation is needed:

```sh
node --test test_core.cjs
```

The same `core.js` exports CommonJS in Node and `ExhibitorDesk` in a browser.
Functions return new state without changing the caller's state.

```javascript
const D = require('./core.js');
const now = '2026-09-08T12:00:00.000Z';
const original = D.sample(now); // Clearly synthetic records.
const exhibitorId = original.exhibitors[0].id;
const portable = D.portal(original, exhibitorId);
const returned = D.submission(portable, {notes: 'Bring two display tables'}, true, now);
const received = D.importSubmission(original, returned, now);
console.log(received.status); // applied
console.log(D.importSubmission(received.state, returned, now).status); // duplicate
```

`portal` projects one exhibitor and the current event notice, without unrelated
exhibitors or internal history. `importSubmission` retains original returns,
coalesces exact retries, and keeps stale revisions for review. `resolveSubmission`
merges selected fields while retaining unrelated organizer edits; an asset-ID
collision with different content leaves the input unchanged. Event-notice
acknowledgement is separate from exhibitor-record revision. A partial merge never
acknowledges a newer deadline. Calendar, CSV, unsent reminder text, and workspace
validation functions are also available.

## Compose with the canonical product

The canonical README was read at `c4ca4763a35b7635cff7fa7d4a17affa0c659df7`.
These preserved reference schemas are not interchangeable with its API:

- This model uses `contact`, `booth`, free-text `dimensions` and `power`;
  the app uses `contact_name`, `booth_code`, `width_m`, `depth_m`, and `power_w`.
  Keep the canonical field validators; do not infer numeric measurements from
  free text or replace its SQLite revision semantics.
- This reference applies a matching-revision return immediately. The canonical
  workflow creates a pending proposal for organizer resolution. Retain that
  proposal/resolution flow when borrowing the comparison or preservation logic.
- Reference assets use `{id,name,mime,size,base64}` and permit empty files.
  Canonical upload uses `{filename,kind,base64}` and its existing byte limits.
  Preserve canonical storage, retained versions, and byte validation.
- This reference's acknowledgement field is its own notice-state model. It is
  not a claim that the canonical app stores or enforces that field.

`app.py`, the canonical UI, `portable_intake.py`, and the top-level source manifest
are unchanged by this contribution. No adapter or automatic runtime import is
installed. The functions and regression cases are available for the canonical
builder to consume without duplicating the product.

## Validation and provenance

The two JavaScript files are byte-identical to the retained #046 handoff source.
`SOURCE-MANIFEST.json` records their byte counts, SHA-256 values, and Git blob IDs.
All 24 core tests passed in this publication session (Node 22.16.0, 84.127111 ms).
They exercise the actual implementation, including binary recovery, duplicate
returns, stale-return preservation, selective merges, notice changes, and exports.

This run does not establish browser persistence, native navigation, canonical
SQLite/API integration, hosted deployment, customer delivery, or revenue. The
original reference UI, screenshots, and private execution records are not part
of this publication. No customer records, attachment contents, or credentials
are included; test assets and company names are synthetic.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
