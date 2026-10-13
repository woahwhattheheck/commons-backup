# GrantFox sponsor PR-reference audit

The bounty supply problem is not just duplicate source **we** publish. A GitHub issue can appear OPEN, unassigned, and labelled "GrantFox OSS / FWC26 / Maybe Rewarded" while an unrelated contributor has an OPEN competing PR linked only in an issue comment. The existing issue metadata and a sparse workfeed can miss that incumbent.

For example, LFGBanditLabs/Quipay issue #1078 has a first-party comment linking another author's PR #1093, whose current sponsor PR was independently confirmed open at intake time (2026-10-08). A second generic fix would duplicate the contributor's work and potentially compete for their compensation.

This **offline** companion tool exposes such references for a *fresh canonical read* before build or dispatch. It does not modify or replace the established workfeed compiler or invoke GitHub/GrantFox. It preserves incumbents, authors, and payout positions.

## Input

Use the existing GrantFox compiler's JSON array or JSONL issue snapshots with `repository`, `number` (or `issue_number`), and `issue_comments` containing raw GitHub comment objects (with `id`, `user.login` and `body`). A missing `issue_comments` field is **CENSUS_MISSING**; an explicitly supplied empty array is merely **NO_PR_LINKS_IN_SUPPLIED_CENSUS**, never conclusive proof that no PR exists.

A same-sponsor GitHub URL ending in `/pull/<number>` or an explicit `PR #<number>` / `pull request #<number>` in those comments becomes `PR_REFERENCE_REVIEW`. Issue references without a PR noun and PR URLs from another repository are excluded. Multiple comments linking one PR are deduplicated while retaining all comment IDs/authors.

This is a *pointer*, not a verified PR status: references can be stale, closed, unmerged, or unrelated. All `pr_open_verified` flags are deliberately false until a separate first-party GitHub read establishes the actual current PR head, state, author, changed scope, and claim history. A verified closed/rejected incumbent need not block all future work; verify sponsor expectations.

## Run

```bash
python -m tools.grantfox_pr_reference_intake.scan issues.jsonl --format slack
python -m tools.grantfox_pr_reference_intake.scan issues.jsonl --format json > reference-audit.json
```

`--max-issues 20` limits the Slack-view display, not the JSON audit. Input is bounded at 5,000 issues and 5,000 comments per issue. The tool does **not** fetch more comments, query PRs, claim a bounty, comment on issues, or make an award/payment assertion.

## Dispatch contract

1. If a PR reference appears, **hold the automatic generic BUILD dispatch** for that issue, follow each linked sponsor PR, and compare live scope/state/author to the outstanding acceptance criteria.
2. If the reference is an open incumbent implementation, preserve their contribution and claim; route only a demonstrated residual/maintainer-requested task. If stale or unrelated, record that evidence before publishing fresh work.
3. If comment census is missing, fetch it through the **rate-admitted canonical GitHub account** rather than quietly labelling the bounty unclaimed.
4. If the verified existing PR is open, populate the workfeed compiler's `open_pull_requests` with **only that verified PR**; if there is an actual claiming contributor, populate `claimant_comments` with the observed person. Never backfill these authoritative fields solely from a bare link.
5. No mention of a platform campaign or maybe-rewarded label proves funds, entitlement, assignment, or payment. Keep original author and verified claim registration intact.

## Focused check

```bash
python -m unittest tools.grantfox_pr_reference_intake.test_scan -v
```

Coverage is limited to the actual issue-comment PR-link distinction, missing-vs-empty input, same-repo filtering, stable dedup/source receipts, bounded Slack output, malformed snapshots, and JSONL CLI behavior. No repository-wide suite required.
