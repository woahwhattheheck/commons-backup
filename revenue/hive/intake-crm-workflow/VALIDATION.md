# Build validation — 2026-09-08

Scope: `ASTER-hive-intake-workflow-20260908-01`, new residential-cleaning intake/CRM/task application. Execution used the provided ChatGPT cloud container, not the owner's computer. Test records use synthetic example addresses and temporary databases. No third-party CRM, customer, hosting provider, or payment operation was exercised.

## Executed

`python -m unittest -v test_workflow.py` — **20 tests passed, 3.283 seconds** on Python 3.13. Full stdout was retained in the working cloud container. Cases cover:

- Atomic intake/customer/job/three-task/outbox creation; exact replay and same-ID conflict; new job for returning customer; restart persistence.
- Twenty-four concurrent identical intake requests create one local job; parallel local workers create one notification; active and expired leases behave separately.
- Actual loopback HTTP delivery, a receiver that commits and disconnects before acknowledging, repeat-event deduplication, 503 retry, and redirect handling.
- Persistent mapping changes, replay after mapping change, transactional configuration, task completion/reopening, invalid input and malformed HTTP JSON handling, state/export endpoints, and dashboard HTML serving.

The server/API tests are not browser-interaction tests.

`node --check` on the exact inline dashboard script — **passed** on Node 22.

`python -m py_compile workflow.py test_workflow.py browser_smoke.py` — **passed**.

CLI sequence in an isolated temporary database: ingest the included example twice, run `work --limit 20`, then export. Result: **1 customer, 1 intake, 1 job, 3 tasks, 1 outbox event, 1 local notification, 0 inbox events**. The second ingest returned the same job with `created: false`; the worker delivered the local event once then returned `processed: false`.

## Browser boundary

`python browser_smoke.py` launched Chromium but navigation to the local test server returned `net::ERR_BLOCKED_BY_ADMINISTRATOR`. No interactive desktop, mobile-layout, or browser screenshot result is claimed. The optional smoke script is included for execution in an environment where that navigation is supported. No attempt was made to alter or bypass the administrator policy.

## Delivery boundary

This receipt documents a runnable source package and the tests above. It does not claim current-main integration, hosted CI success, a live deployment, a customer installation, customer acceptance, outreach, payment, or revenue. Those states require their own actual delivery receipts.

## Selected-event retry follow-through

The first source package merged through PR #10497 as `17580b81d35d6a68ff50c34934d36a7bfa5ce1e6`; all nine published Git blob identities matched the tested files. The following incremental change preserves that product and its original validation record above.

A new two-job HTTP regression initially returned the older queued event when the operator selected a newer one. The optional `id` on `/api/process` now filters the queue claim, and the per-job Retry button sends that ID. An active lease or an absent selected event does not substitute another job. A blank selected ID returns 400. Global queue processing remains oldest-due-first.

Current revised suite: `python -m unittest -v test_workflow.py` — **22 tests passed in 4.274 seconds**, including the two selected-event HTTP regressions and the original 20 checks. Python compilation and Node syntax validation of the revised dashboard script also passed. Interactive browser navigation was not retried; its administrator-policy boundary remains unchanged. The recorded suite uses actual local HTTP and SQLite, not an external provider.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
