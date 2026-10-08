# Original-author bounty claim waiver audit

Find published *claim-forfeiting language* in an owner's existing bounty PR bodies and issue comments. This is a read-only revenue-recovery tool. It never edits contributor words, publishes a new claim, contacts a sponsor, registers a claim with a bounty provider, or asserts a payout.

**Live public GitHub audit** (budgeted; no login required):

```bash
python -m tools.bounty_claim_waiver_audit.cli --repo Movalabs-crew/mova-store --owner woahwhattheheck --issue 75 --issue 25 --pr 361 --max-requests 6 --format markdown
```

`--issue` fetches every page of that GitHub issue's comments; `--pr` fetches that PR's body. Only the named author's text is flagged, never the original competing contributors' text. `GITHUB_TOKEN` is optional for higher API quotas and is never echoed. By default the tool makes **at most 12 GETs total**; 403, 429, unexpected pagination, source inconsistency, quota exhaustion, and transport errors downgrade coverage to `INCOMPLETE` (exit `2`) rather than claiming no waiver was found.

**Offline snapshot** (for already gathered first-party provider responses, with no network calls):

```bash
python -m tools.bounty_claim_waiver_audit.cli --repo Movalabs-crew/mova-store --snapshot captured.json --format markdown
```

`captured.json` uses schema `commons.bounty_claim_waiver_snapshot/v1`, the matching `repository`, `complete: true` (only when the capture includes every intended source record), and `records` containing `kind` (`issue_comment` or `pull_request`), `issue_or_pr`, `url`, `author`, and `body`. Do not mark partial captures complete. Comment URLs require the real `#issuecomment-<id>` fragment. The scanner rejects cross-repository/transplanted records, duplicates, and missing item identities. Snapshot completeness is an assertion by the supplying collector, **not** a claim the CLI independently authenticated a provider.

**Exit and action semantics:** `0` = complete scan/no matching first-person waiver expressions; `1` = complete scan/matches needing human or authorized same-author correction; `2` = incomplete/invalid scan. `--format json` emits the exact finding URLs and excerpts; `--format markdown` emits an edit-in-place action list. `--output path` creates a new report without overwriting an existing one. Wording matches are candidate findings, not conclusive proof of waiver, and the scanner cannot establish whether a sponsor approved assignment, provider registration, a reward, or settlement. The original claim/payment request is preserved throughout.
