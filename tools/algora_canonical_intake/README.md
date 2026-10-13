# Algora canonical-source intake

A **read-only offline** reconciliation of Algora's advertised Open bounties
against separately observed canonical GitHub issue/claim-PR state. It
prevents duplicate engineering on closed, moved, archived, contested, or
unverifiable tasks. The same issue produces at most one work order, even
when a board contains multiple price rows.

## Usage

From Commons repository root:

    python3 tools/algora_canonical_intake/cli.py \
      tools/algora_canonical_intake/example.synthetic.json \
      --as-of 2026-10-08T04:00:00Z

    python3 tools/algora_canonical_intake/cli.py snapshot.json \
      --max-age-hours 6 --minimum-usd 15 --output decision.json

The example data is **synthetic**, including timestamps and fictional
GitHub issues. No network, password, GitHub App, or paid provider API is
used. Output is deterministic at fixed --as-of. Missing/untrusted/stale
evidence yields HOLD, never a green build. Malformed data exits 2.

## Required observations

Input schema: commons.algora_canonical_intake.v1.

- provider_source: official HTTPS algora.io or console.algora.io board URL.
- provider_observed_at: actual offset-aware timestamp from **your** board
  observation, not an old third-party crawl display timestamp.
- listings: actual provider listing_id, GitHub issue_url,
  advertised_usd (cent precision), board_state (open or closed) and
  board_claims (nonnegative integer or null if unknown).
- github_issues: separately verified canonical issue_url, state (open,
  closed, not_found), checked_at, repository_archived boolean, assignees
  array, claim_pr_urls array and claim_scan_complete boolean.

Set claim_scan_complete=true **only** after an actual exhaustive sponsor
PR/claim check, including other contributors and linked issue references.
A failed, inaccessible, or partial search is not evidence of zero claims;
set it false. Never infer canonical OPEN status from Algora board wording.
Canonical identity is case-normalized owner/repo/issue number. Duplicate
listing IDs and conflicting GitHub snapshots are schema failures.

## Decision contract

- READY_FOR_COORDINATED_TAKE: official provider and GitHub observations
  fresh; canonical issue open in active repo; no assignees; verified PR
  claim search complete/empty; board claims = 0; one listing meets the
  $15 green-platform minimum. This is only a candidate, NOT an award.
- HOLD: evidence stale/incomplete, below threshold, assigned, or claims
  or competing source PRs already present.
- PRUNE: board no longer open, canonical GitHub issue closed/inaccessible,
  or repo archived.

Each issue gets one decision. Every historical listing stays in the audit
record, including `board_state` and `board_claims`, while `open_listing_ids`
identifies exactly the currently actionable listings. Historical CLOSED rows
cannot veto an independent OPEN bounty for the same GitHub issue, and their
previous claims or larger amounts cannot inflate the open opportunity.
`advertised_max_usd` is the maximum **OPEN** listed amount (0.00 when all
listings are closed); emitted work orders include only active listing IDs.
Amounts are never summed to imply collectible escrow or cash.
reward_awarded and payment_received are always UNKNOWN. Even merged PRs are not payouts.

To act on candidates: reserve one ownership TAKE in Slack, refresh both
first-party provider and GitHub issue/PR evidence, preserve original
contributor identity, include /claim #ISSUE on eligible Algora PRs, and
verify actual payout rules. This tool does not contact maintainers,
submit claims, open PRs or spend money.

One focused optional regression:

    python3 -m unittest tools/algora_canonical_intake/test_cli.py

No broad Commons suite is required.
