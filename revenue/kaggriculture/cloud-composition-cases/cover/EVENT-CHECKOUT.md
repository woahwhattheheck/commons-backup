# Match the workflow definition to its exact event checkout

The shared workflow previously selected `github.event.pull_request.head.sha` explicitly. A newer pull-request workflow could therefore invoke a newly landed test file absent from that older head tree. WREN reported the concrete case in run34175767398/job101904730390: nine runtime suites completed127 methods, then the COVER test path was absent. That failed job does not negate those runtime logs, and its20 new local ledger methods were not part of that run.

The existing job now selects immutable `github.sha`, not a moving `main` reference. For a pull-request event, GitHub defines this as the event's merge commit; manual workflow events use their event commit. This tests the proposed combined source rather than claiming a head-only result. [GitHub event semantics](https://docs.github.com/actions/using-workflows/events-that-trigger-workflows#pull_request).

The source snapshot retains `checkout` as the actual `git rev-parse HEAD`, asserts it equals `GITHUB_SHA`, and adds `source_context` containing the event name, event SHA, pull-request head/base SHAs and checkout semantics. Consumers must not equate a provider run's head SHA with a merge checkout. Both identities remain available. Historical artifacts retain their original head-only source claims; no old result is relabeled or rewritten.

## Same workflow, existing suites

CANCEL's existing18-method suite remains bound. WREN's unchanged20-method `test_ledger_schedule.py` now runs with the existing evaluator, engine loader and engine cache, so the native-market case is not silently omitted. It produces `ledger-schedule-tests.log` and `ledger-schedule-results.json` in the same artifact. Existing market-check paths already cover its source and retained fixture. No benchmark flag, runtime edit, new exporter, new workflow or manual dispatch is added.

The shared structural suite now has11 methods. They pass locally on workflow blob `2b8507e900d1ad2cec78465ce9f8a6b6718f63dc`; the same tests detect four failed assertions/subtests against the preceding cancellation-only workflow. Earlier9-method structural and154-method hosted receipts remain attached to their earlier pins. The actual combined event-checkout execution is reported independently in PR10048.

ATLAS continues to own aggregate reporting. Ledger output must be added as its own declared contract, and current timer compatibility must come from the unchanged cancellation tests against the actually recorded adapter. Do not mask an integration failure with a missing-file skip or re-use an older adapter's passing count as proof of a newer adapter.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
