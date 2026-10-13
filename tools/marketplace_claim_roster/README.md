# Marketplace claim-roster reconciliation

**Revenue gate:** a GitHub PR, `/claim #N` comment, fork branch, and an
actual marketplace claim are different records. Before calling a paid bounty
"registered", reconcile **the original PR author + exact upstream PR** against
the **actual provider's claimant roster**. Never infer a payout from a platform
card, a merged PR, an empty roster, or a claim receipt.

This standalone tool runs offline with Python 3.9+ standard library. It makes
**no network requests or writes**, logs no credentials, and cannot submit a
claim. The fleet collector is responsible for fresh first-party GitHub and
Algora/BountyHub evidence; this tool only reconciles it.

## Usage

Create a JSON snapshot after visiting the *individual listing* and checking
the original contributor's current PR head/author. Supply a **per-listing URL**
(not a multi-issue board URL), `checked_at`, and the visible public claims.
Only set `roster_complete: true` if the provider's complete claim roster was
actually inspected; missing rows or pagination must be `false`.

```json
{
  "listings": [
    {
      "provider": "bountyhub",
      "listing_url": "https://www.bountyhub.dev/en/bounty/view/sample-uuid/demo",
      "expected_login": "exampleowner",
      "source_pr_author": "exampleowner",
      "source_pr_url": "https://github.com/example/repo/pull/123",
      "checked_at": "2026-10-08T05:50:00Z",
      "roster_complete": true,
      "manual_contribution_required": false,
      "claims": [
        {
          "claimant": "exampleowner",
          "pr_url": "https://github.com/example/repo/pull/123",
          "status": "submitted"
        }
      ]
    }
  ]
}
```

All values above are **synthetic**, not a real submission. A claim's
`claimant` and optional `pr_url` must come from the public provider record,
not be copied from a GitHub issue, PR description, or bot command. Preserve
`status` (for example `submitted` or `rejected`). For Algora, if only a
GitHub username is displayed, omit `pr_url`: the tool then correctly returns
`CLAIMANT_VISIBLE_PR_UNVERIFIED`, *not* exact PR registration.

```sh
python3 tools/marketplace_claim_roster/audit.py /path/to/provider-snapshot.json
python3 -m unittest tools/marketplace_claim_roster/test_audit.py
```

## Actions

| Result | Fleet action |
| --- | --- |
| `EXACT_CLAIM_VISIBLE` | Preserve the claim; check actual current provider status and creator acceptance |
| `CLAIMANT_VISIBLE_PR_UNVERIFIED` | Inspect the contributor's provider claim details before a second claim |
| `REJECTED_OR_WITHDRAWN_CLAIM_VISIBLE` | Review creator decision; never treat it as active registration |
| `PR_ASSOCIATED_WITH_OTHER_ACCOUNT` | Escalate attribution conflict without overwriting or forfeiting the existing claim |
| `ABSENT_FROM_COMPLETE_ROSTER` | Check eligibility and sign in as the original PR author to register the original upstream PR |
| `ROSTER_INCOMPLETE` | Fetch the full provider roster; do not assert claimant absence |
| `AUTHOR_UNVERIFIED_OR_MISMATCHED` | Read original upstream PR user from GitHub and resolve identity first |
| `PR_UNVERIFIED` | Publish or resolve the actual upstream PR before portal submission |

If a listing requires meaningful **human contribution** and none is verified,
set `manual_contribution_required: true` so a missing claim routes to human
eligibility review instead of automated dispatch. This does not determine
whether the underlying work is eligible.

The engine uses a separate stable key for each provider listing URL, so two
pledges for the same GitHub issue remain **two distinct registration records**.
Its `payment_status: NOT_EVALUATED` means only that this *roster checker does
not inspect transfers or balances*; it is neither a finding of nonpayment nor
a payment waiver. Registered/accepted/paid must be independently read back
from the actual marketplace and applicable settlement sources.

Never put bearer tokens, GitHub credentials, banking data, or private payout
identifiers into these snapshots or Slack output. Replace expired snapshots
with fresh provider evidence before dispatch.
