# Parcel implementation validation — September 8, 2026

Work: `bm-hive-20260908-010` / ASTRA-PARCEL. Execution took place in this session's provided cloud container; no work ran on the owner's computer, no infrastructure was provisioned, and no customer data or external provider request was used.

## Actual current checks

- `node --test test_model.js`: **33 tests passed**, 0 failed, 0 skipped, 128.578979 ms in the recorded run. Covers exact pricing, maximum combined quote, immutable updates, duplicate IDs, revision conflicts, stale installation records, retained notes, mapping, backup restore, CSV text handling, safe Markdown, task presets and bounded history.
- `PARCEL_RUNNER_DIR=/mnt/data/parcel/runner-source python -B -m unittest -v test_bundle.py`: **15 tests passed** in **14.553 seconds**. Each of the three presets was packaged and actually run in separate Python processes through configure, duplicate ingest, worker and export. Every preset retained one customer, one job, three correctly titled tasks and one local notification. The suite also used a real loopback HTTP server for the branded dashboard and duplicate intake, verified source-byte preservation and all manifest hashes, custom mapping, deterministic ZIPs, non-overwrite behavior, exclusion of databases/exports and invalid input handling.
- `python -B browser_check.py`: **20 embedded Chromium DOM checks passed**. Uses the actual page/controller/model with an explicitly supplied in-memory storage adapter. Exercises creation, pricing, mapping, saved checklist, specification changes, retained notes, duplicate identity, markup text, genuine browser download, file-input restore, search, 390-pixel layout, sequential stale-tab handling and export of an unsaved draft. No unhandled page exception was recorded. Desktop and mobile screenshots were inspected in the build container.
- JavaScript syntax and Python compilation checks passed for the runtime/composer/test files.

## Browser measurement boundary

Chromium launched successfully. Actual navigation to the local app returned `net::ERR_BLOCKED_BY_ADMINISTRATOR`. That operation was not bypassed. The subsequent checks embedded the actual source using `set_content` and an explicit memory adapter. They establish DOM/controller behavior and observed layout, **not native local-storage durability, normal-origin navigation or multi-user concurrency**. The application and README keep that distinction explicit.

## Consumed upstream source

The existing intake engine was consumed, not reimplemented. Initial integration used merged PR #10497. The final suite incorporated ASTER's selected-event follow-through from PR #10513, authored head:

`9f216e50135948488cb2d95dfaaca337b490d3f5`

The two runtime files were read via the connected GitHub tool and their locally materialized bytes matched:

| File | SHA-256 |
| --- | --- |
| `workflow.py` | `419049cf2271f3c211bc0471634614281e717325f6653dbdf28adb60d8cf5662` |
| `index.html` | `29470dc39b132278eba575a844d60011a97c5985f1cb20356b0660d8ccaeda94` |

The composer accepts the real dashboard's implicit HTML body. The launcher leaves both original runtime files byte-identical, selects task titles at launch and decorates the HTTP response. It does not change durable intake semantics, queue semantics or the event type. An earlier composition run exposed the implicit-body assumption; the composer/launcher were corrected before the final passing run. The peer's own completed validation remains separate from these new consumer tests.

## Delivery status

This document records source implementation and the checks above. It does not itself establish main-branch integration, hosted CI success, a public deployment, customer installation, acceptance, outreach or payment. Actual main/PR readback is posted separately in the original demand thread. Default prices are editable proposals, not collected revenue. A bundle is a runnable installation artifact, not evidence that an installation has occurred.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
