# Sponsor PR census — reusable issue-to-contributor inventory

A **GitHub issue being open and unassigned is not evidence that its bounty is unclaimed**. The Oct 8 PocketPay Mobile #526/#522 incident demonstrated that narrowly searched issue keys missed existing, original-author upstream PRs #556/#552; duplicate source work was subsequently suppressed.

This standalone stdlib-only tool consumes an **already captured, fully paginated, authenticated sponsor `GET /repos/{owner}/{repo}/pulls?state=open&per_page=100&page=N`** response. It makes *no* provider calls, so multiple swarm workers can reuse a single bounded capture when GitHub Search is secondary-rate-limited.

## Capture contract

Collect with your authorized GitHub provider action or existing shared read coordinator, **not by adding a new token or rotating identities**. Save each response's PR `number`, `state`, `title`, `body`, `html_url`, `user.login`, `head.sha`. Capture only the actual sponsor repository, not the fork. The snapshot must declare:

```json
{
  "repository": "Stellar-PocketPay/pocketpay-mobile",
  "source": "github-rest-pulls-authenticated",
  "captured_at": "2026-10-08T05:15:00Z",
  "page_size": 100,
  "pages": [
    {
      "page": 1,
      "pull_requests": [
        {
          "number": 556,
          "state": "open",
          "title": "feat(wallet): balance refresh state machine",
          "body": "Closes #526.",
          "html_url": "https://github.com/Stellar-PocketPay/pocketpay-mobile/pull/556",
          "user": {"login": "woahwhattheheck"},
          "head": {"sha": "7a06d2c03f9cd84449af8f1139228c7584830500"}
        }
      ]
    }
  ]
}
```

`captured_at` must reflect the real provider read time, in UTC or another explicit offset, **not a fabricated freshness time**. A capture must be no more than 15 minutes old. Pages are sequential, 1-indexed, and every nonfinal page must have `page_size` rows. If the last page is exactly full, capture a subsequent page (even if empty) to establish exhaustion. The offline reader trusts the *declaration* of authenticated collection; it does **not** prove that a snapshot was genuinely obtained from GitHub. Preserve original provider read receipts.

## Run and interpret

```bash
python -m tools.bounty_pr_census.census \
  --input /path/to/pocketpay-sponsor-pulls.json \
  --repo Stellar-PocketPay/pocketpay-mobile \
  --issue 526
```

- **HOLD_EXISTING (exit 3):** one explicit issue-linked PR; preserve its author/branch/claim. Review its real acceptance scope, do not submit another.
- **HOLD_COLLISION (exit 3):** two or more explicit issue-linked PRs; reconcile competing source before any work or claim.
- **REVIEW_NO_MATCH (exit 4):** *not* a GO or empty-supply finding. Audit unmapped PR titles/bodies, **closed/merged/all-state PRs**, the current sponsor source tree, any existing claims and Slack leases.
- **HOLD_INCOMPLETE (exit 2):** wrong repository, malformed/incomplete pagination, stale/missing/non-authenticated capture declaration. Obtain one fresh canonical provider snapshot when quota permits, never infer absence.

The result includes exact incumbent PR URLs, original-author login, head SHA, PR count and a conservative set of unmapped PR numbers. Matching accepts explicit `Closes #526`, `Fixes #526`, `issue #526`, sponsor issue URLs, or a PR title ending in `(#526)`. Bare `#526` elsewhere is intentionally **not** taken as conclusive (it may be an unrelated reference). Cross-repository issue references are not treated as local matches.

This is a **pre-TAKE advisory inventory**, not a marketplace claim, entitlement or payout validator. It does not authenticate a collector, inspect closed/merged PRs, resolve GitHub branch heads live, check maintainer acceptance, or establish payment. Recheck actual sponsor source and publication paths before final submission. Never use the result to negate another contributor's earned attribution.

## Focused regression

```bash
python -m unittest tools.bounty_pr_census.test_census
```

This focuses six acceptance cases: original incumbent, multiple incumbents, no-match hold, foreign repo, stale/full-last-page rejection, and complete pagination.
