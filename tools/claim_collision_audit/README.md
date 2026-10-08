# Paid-issue claim collision auditor

Read-only, Python-standard-library audit of **verified fleet coordination receipts**. This answers a concrete Oct 8 incident: two paid-issue source races (PocketPay SDK #278 and Raegis SDK #19) were stopped by exact-head checks, but new Slack operation IDs were not reliably discoverable through search-index freshness. The correct unit of comparison is the canonical GitHub **owner/repo#issue**, regardless of bounty platform, Slack session ID or branch name.

The separate MOVA batch planner creates work orders; this auditor reconciles ownership and write receipts once a worker has acted. It does not replace MOVA, bounty funding checks, provider registration, or the original author's payment claim.

## Usage

Requires Python 3.10+; no dependencies, tokens, API calls, background polling, network writes, or broad tests.

~~~sh
python tools/claim_collision_audit/audit.py tools/claim_collision_audit/example-collision.jsonl --now 2026-10-08T04:25:00Z --format slack
python tools/claim_collision_audit/audit.py /path/to/verified-fleet-events.jsonl --format json
~~~

Return code: **0** = no anomalies found in *provided* events; **2** = at least one collision/unsafe mutation/invalid row; **3** = file read failure. Zero never means the whole Slack workspace was scanned; upstream discovery and provider receipt collection are still required. JSON output exposes per-issue owners, last accepted source head, real sponsor PR, and collision / blocked-write counters. Slack output is copy-ready but is **not posted automatically**.

## JSONL evidence contract

Each line is one object with stable unique operation_id, timezone-aware ISO-8601 at, issue_url, session and event. Preserve the actual GitHub issue URL and use the same source owner name across the lease. Accepted events:

- TAKE: optional lease_seconds (60 to 86400, default 900); a second live distinct owner records TAKE_COLLISION and is **not** admitted by this audit state.
- RELEASE: frees only a live lease held by the same session; foreign releases are flagged.
- HEAD_CHECK: record actual head_sha (40 hex) plus either pr_url (sponsor PR **or** original-author fork PR) or branch_url (a GitHub /owner/repo/tree/branch URL). A branch URL is a *source ref*, not a sponsor PR.
- WRITE: expected_head_sha and new_head_sha, with the same pr_url or branch_url as HEAD_CHECK. Requires a live matching owner and a fresh unconsumed HEAD_CHECK (default at most 300 seconds old). Every accepted write consumes that check, so every subsequent write requires another exact-head read. Different known heads or reused checks are flagged as UNFENCED_WRITE.
- PUBLISH: requires a **canonical sponsor-repository** pr_url, a live owner lease, and an actual provider-confirmed PR. Publishing a fork PR as if upstream is refused. A second distinct sponsor PR for the same issue is DUPLICATE_SPONSOR_PR. Provider claims and reward receipts are **not** inferred.

Example successful upstream publication record:

~~~json
{"at":"2026-10-08T04:24:00Z","event":"PUBLISH","operation_id":"ISSUE707-PUBLISH-1","issue_url":"https://github.com/Centurylong/sanctifier/issues/707","session":"cloud-publisher-3","pr_url":"https://github.com/Centurylong/sanctifier/pull/12345"}
~~~

That line is **schema illustration only**. Do not enter fictional PRs or substitute fork carriers as live receipts. Actual source/issue links in the ledger must be gathered from first-party GitHub readback, not assumed from a planner's operation ID.

For every source mutation, read the real branch/PR head immediately before the commit and use the publisher's native expected SHA / compare-and-swap capability. On a conflicting head, STOP and reconcile. A successful audit from old Slack exports **cannot authorize a GitHub write**, replace provider permissions, guarantee that a later session did not take work, or reserve ownership across distinct machines.

## Operating protocol

1. Verify fresh canonical issue URL, assigned/competing PRs and Slack claims. Export authoritative TAKE/RELEASE/HEAD_CHECK/WRITE/PUBLISH receipts as JSONL. Reuse known provider receipts; do not fan out GitHub searches under a secondary rate limit.
2. Run the auditor before dispatch and after source/publication handoff. Any anomaly is a manual RECONCILE/HOLD for that canonical issue; do not automatically skip the original contributor, revoke a legitimate claim or forfeit compensation.
3. Use source-head compare-and-swap and an **external atomic lease service** for cross-host guarantee. This tool's local in-memory lease is an audit/replay simulation, **not** a cross-host distributed lock, and cannot prevent simultaneous live writes. Slack search alone is not an atomic reservation.
4. Publish only real receipts to an internal coordination thread. Preserve existing original-author PRs and affirmative bounty/payment requests. Always distinguish advertised conditional rewards from accepted, awarded or received payouts.

The collision fixture deliberately exits 2, documenting a second TAKE, repeated write without a fresh head read, and attempted post-release publish. It is not a live claim, provider submission or payment record.
