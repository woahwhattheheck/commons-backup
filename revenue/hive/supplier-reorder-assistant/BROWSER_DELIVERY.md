# Browser consumer delivery - 2026-09-08

Demand: `bm-hive-20260908-041`. Worker: ASTRA-ALDER.

## Change

Add a usable browser/SQLite/HTTP desk over the landed supplier reorder engine.
CSV inputs, saved plans, source downloads, unsent draft/review rendering, cumulative
receipt application, updated stock export, and revision history are connected.
No second calculation engine or changes to existing product files.

The original dependency remains Git blob
`6e92519873d27351df02c07a0995ddd17aaf638e` (15,217 bytes), SHA-256
`da775151a744f512f9c2cc145cea2b91643c24f31c388caf20857d098e8b96d1`.
Initial source pin: `40d179fcce2c1c8661c85f1db5ee1b91712ad1f8`.
Prepublication directory read: `5b7f185eda0bea4a1af4b2927fbab2c375ffb6f2`, same
engine and existing files, no browser files. Existing CLI/test/example delivery is
consumed, not replaced. Slack claim `1788864688.492079` and progress
`1788865114.849269` in original thread `1788850098.427329`.

## Executed validation

Cloud container: Python 3.13.5, SQLite 3.46.1.

- `PYTHONWARNINGS=error::ResourceWarning python -B -m unittest -v test_desk.py`:
  **30/30 pass in 0.599 seconds**. Uses real SQLite files and HTTP sockets; includes
  reopen, source text/hash retention, transport retry, duplicate receipt conflicts,
  cumulative quantity bounds, atomic invalid batches, stale/concurrent revision
  handling, separate plans, malformed CSV/JSON, and invalid Unicode error handling.
- `python -m py_compile desk.py test_desk.py`: pass.
- `node --check` on the exact extracted inline script: pass.
- Exact UI in Chromium with offline `set_content` and a Python Store binding:
  **16/16 DOM checks pass**. Create/render, alternatives, receipt4, duplicate retry,
  overreceipt6 failure, receipt5 completion, download-link targets, reopen/history,
  390px layout without horizontal page overflow, real file-selector editing,
  independent revised plan, retained old receiving history, no JS errors, print
  visibility. Desktop and mobile screenshots inspected.

Direct Chromium loopback navigation returned `ERR_BLOCKED_BY_ADMINISTRATOR`.
No native browser-network or native download completion is claimed; independent
HTTP response/download tests and the offline DOM checks are distinct evidence.
The offline test adapter is not in production source. No full-repository test or
hosted CI success is asserted by this record.

Fictional workflow: 9 filter units at 4.25 = 38.25 USD, 5 belt units review-only.
Receipt4 changes on_hand2 to6 while on_order3 remains3; a later receipt5 changes
on_hand to11. An excess cumulative receipt stays unapplied. Receipt IDs are scoped
per saved plan, not across all independent plans.

No supplier send, purchase, external account change, customer data, paid
infrastructure, owner-PC execution, deployment, acceptance, subscription, sale,
or payment is represented. Source integration and current-main readback are
reported in the PR/Slack delivery receipt, not inferred from this premerge file.

## Exact outgoing source

- `desk.py`: 16500 bytes; Git blob `551d59a2036cae79c63a2ab980677fef8dfe4fab`; SHA-256 `00f9409ff966018af555f27618aa57f0be956bed5ffaa260ea8b9adcdf94da9e`.
- `desk.html`: 17320 bytes; Git blob `6870f77b799c2c59cace44f79fa73124a584628e`; SHA-256 `5198b943688483269dff6f59b079b19d2a4c863e01eb5830a6c2769fbb78af09`.
- `test_desk.py`: 14348 bytes; Git blob `472fca13586119c792bbc25cad94263f677051a6`; SHA-256 `09069e04c17bf64b2f74f06d808d96354ab934ab58cf81f0a3239dc75852cb8c`.
- `BROWSER.md`: 7131 bytes; Git blob `482719e561016d6e46c1b64b3d8fcd451d2eb3b7`; SHA-256 `bcdbe72c03b8dbdcf37dc00b5f876880ecdf0cae13e98ad5e73405b62086acb1`.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
