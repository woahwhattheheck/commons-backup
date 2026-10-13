# Paid PR metadata audit — offline, review-only

This standard-library CLI audits **already-existing** original-contributor bounty PRs and their issue comments without creating duplicate claims or rewriting authorship. It is deliberately separate from Commons' `claim_collision_audit` (canonical issue cross-platform duplication) and `mova_batch_sprint` (build/publish/settlement routing). The target gap is **a sponsor PR whose issue has an original `/claim`, but whose own body lacks an affirmative, conditional compensation request**, or whose body still contains waiver language.

## Usage

```sh
python tools/paid_pr_metadata_audit/audit.py current-verified-snapshot.json --output audit-report.json
python tools/paid_pr_metadata_audit/test_audit.py
```

The second command is the only focused regression check. No network, SDK, third-party dependencies, provider writes or GitHub tokens are used. To reproduce an exact report use `--as-of 2026-10-08T05:10:00Z` with an actually observed snapshot; this flag is **not** permission to freshen stale facts.

## Snapshot schema

Top level: `schema: "commons.paid_pr_metadata_audit.v1"`, `actor` (the original contributor's GitHub login), timezone-aware `as_of`, and `records` array. Each record requires:

- `issue_url`, `pr_url`: exact GitHub issue/sponsor PR links in the **same** repository. Fork-only PRs are not sponsor submissions.
- `platform`: `grantfox|algora|bountyhub|issuehunt|proven_payer`; `pr_author`, `pr_head_sha` (optional but recommended), `issue_state` and `pr_state` (`open|closed`).
- Complete `pr_body`, original issue `issue_labels`, issue comments as `{ "author": "...", "body": "..." }`, and whether `comments_complete` was established from *all* available pages.
- `checked_at`: actual canonical-source collection timestamp (UTC or with offset). The entire snapshot expires after 6 hours by default. Do not invent missing comments or timestamps.

`pr_body` is treated as untrusted free text. Quote blocks and fenced code are ignored in the lexical check; issue-side `/claim #N` must belong to the **same** actor and issue number. Explicit non-closing sponsor references (`Refs #N`, `Related to #N`, `for #N`, or a full sponsor `issues/N` URL) count as issue linkage without claiming the PR will close the issue. Qualified `other/repo#N` links or URLs to a different repository **never** substitute for the funded sponsor issue just because the numbers match. This is a conservative detection aid: it may flag valid but unusually worded requests for manual review. It cannot determine eligibility, payout, funds, ownership authenticity, or whether a marketplace accepted a claim.

## Decisions

- `MANUAL_METADATA_REVIEW`: original PR, fresh complete evidence and program labels; inspect the specific missing request, missing issue-side `/claim`, issue link or waiver text. Do not send every possible claim: check existing comments first and update only the missing surface through the **matching original author** and supported provider workflow.
- `NO_METADATA_GAP_DETECTED`: lexical evidence present; **not** an award, portal registration, approval, or payment receipt.
- `PRESERVE_FOREIGN_AUTHOR`: do not hijack another contributor's PR or claim.
- `HOLD_STALE_EVIDENCE`, `HOLD_INCOMPLETE_CLAIM_CENSUS`, `HOLD_PROVIDER_ELIGIBILITY`: request a fresh first-party read and eligibility check; do not assume absence from partial data.

Every report emits stable PR-specific operation IDs (`PAID-PR-META:owner/repo#pr`), preserves exact source links/head, and separately records the issue claim presence, PR request presence and waiver candidate. No source/test change, claim, compensation request, money movement or sponsor publication is performed by this CLI.