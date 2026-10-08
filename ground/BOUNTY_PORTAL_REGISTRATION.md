# Paid bounty PR ↔ platform registration audit (Commons)

Production command: python3 host/bounty_portal_registration.py retained-input.json --output registration-gaps.json

This is the Commons-side, read-only reconciliation for already delivered GitHub PRs. It does not modify the Sophia-paused bounty-concierge project, register a claim, make a payout, query private accounts, or contact a sponsor. The existing same-author provider operator owns actual IssueHunt/BountyHub registration and payment follow-through. Use normal paid-bounty sponsor intake for new work.

## Inputs (retained current evidence)

The JSON input has schema commons-bounty-portal-audit/v1 plus arrays named owned_prs and provider_snapshots.

Each owned_prs row requires provider (IssueHunt or BountyHub), canonical GitHub issue_url, canonical GitHub pr_url, original claimant GitHub login, verified 40-hex head_sha, github_state (open, merged or closed), github_submitted_at, and github_checked_at. All times are UTC ending Z. The GitHub head and state must be read from the current original PR, not inferred from a Slack post. An allowed cross-repository submission requires submission_repo: owner/repo, verified against the canonical sponsor contribution target.

Each provider_snapshots row requires provider, canonical matching issue_url, source_url, observed_at, explicit Boolean complete, and submissions (possibly empty array).

* IssueHunt source_url must point to the matching official issue at https://oss.issuehunt.io/r/OWNER/REPO/issues/N. Normalize ALL actually registered outputs, not merely activity timeline posts. If the official output list cannot be determined to be exhaustive, set complete to false.
* BountyHub source_url must point to an exact public API bounty detail at https://api.bountyhub.dev/api/bounties/LISTING_UUID. Normalize solver claims[] and exact PR/claimant evidence, not sponsor pledge paymentStatus, amountPaid or advertised totalAmount. If a claim may be ours but lacks a PR URL, preserve that partial output so results fail closed to UNKNOWN.

Each normalized submission has pr_url and claimant; optional state is REGISTERED (default), AWARDED, or PAID. AWARDED additionally requires a specific award_ref. PAID requires independently checked receiving_rail_verified true and a specific receipt_ref. An amount paid by the bounty creator or a platform paid flag is not a solver receiving-rail payout.

## Output and use

The result's stable operation ID binds provider, funded-issue repo and number, original GitHub claimant, submission PR repo and number. States:

* GITHUB_SUBMITTED_PORTAL_NOT_REGISTERED: current, complete first-party issue inventory excludes the exact original-author PR.
* PORTAL_REGISTERED_UNAWARDED: the exact PR and original claimant appear, with no specific award evidence.
* AWARDED or PAID: separately substantiated with the required award or checked receiving-rail references.
* UNKNOWN: missing/stale/incomplete provider inventory, unlinked original-author output, claimant mismatch, stale GitHub head, ambiguous award or unchecked payment rail.

Only genuine registration gaps produce action_items, one for each owned PR. These are idempotent work-order references for the EXISTING authenticated same-author portal operator. The operator must re-read the official platform immediately before taking action. For a BountyHub PR that is already published, the next action is SUBMIT_CLAIM_FOR_PUBLISHED_PR: on the existing matching-GitHub-identity BountyHub login, open the specific listing, choose Submit Claim, attach the exact PR URL, and verify the resulting claim record. A merge is NOT a prerequisite for that claim. AFTER an actual merge, refresh that SAME claim for creator review rather than opening a duplicate claim. Submission, registration, acceptance, award and receiving-rail settlement remain separate receipt-backed states. Never contact the sponsor or create a duplicate platform claim from this report.

By default GitHub and provider observations must both be no older than 2 hours. Use --max-age-hours 0.25 for a strict 15-minute dispatch screen. Input errors exit nonzero; finding an eligible gap is normal success.

## Illustrative JSON shape (NOT a real claim or receipt)

```json
{
  "schema": "commons-bounty-portal-audit/v1",
  "owned_prs": [{
    "provider": "IssueHunt",
    "issue_url": "https://github.com/example/project/issues/3",
    "pr_url": "https://github.com/example/project/pull/9",
    "claimant": "example",
    "head_sha": "1111111111111111111111111111111111111111",
    "github_state": "open",
    "github_submitted_at": "2026-10-07T22:00:00Z",
    "github_checked_at": "2026-10-07T22:05:00Z"
  }],
  "provider_snapshots": [{
    "provider": "IssueHunt",
    "issue_url": "https://github.com/example/project/issues/3",
    "source_url": "https://oss.issuehunt.io/r/example/project/issues/3",
    "observed_at": "2026-10-07T22:07:00Z",
    "complete": true,
    "submissions": [{
      "pr_url": "https://github.com/example/project/pull/8",
      "claimant": "prior-contributor",
      "state": "REGISTERED"
    }]
  }]
}
```

Replace every illustration with current provider captures before using in production. Existing registered outputs from unrelated original contributors NEVER register our distinct follow-on PR.

## Existing live handoff

The IssueHunt follow-on registration batch already belongs to the authenticated operator (https://tokenjunkielabs.slack.com/archives/C0BU51F1PL3/p1791429404603709). At the October 7 live public-page read, egoist/majo issue 9 showed earlier PRs 15/47/51/56 but not original-author PR59; egoist/bili issues 182–184 showed earlier outputs but not original-author PR641/642/640. These are time-specific findings. Refresh before any action; funded listings, earlier-author registration, awards and solver payouts are separate states.
