# Paid PR focused-validation receipt reuse

A read-only, **offline** helper for Mova-style paid bounty delivery. It turns already-recorded focused-check receipts into per-check advice so a swarm does not rerun the same tests on the same source revision, or mistake **test authored** for **test passed**. It makes no GitHub/Slack/marketplace calls and performs no tests, builds, claims or payment actions.

It is intentionally separate from `tools/mova_batch_sprint` (canonical issue/owner/claim planning), `tools/github_rate_admission` (provider request admission), and `tools/evidence_authority` (source identity/authority). This CLI does not assert that a supplied URL really contains passing CI evidence; its judgment is an **advisory over operator-supplied receipts**. Obtain and verify original provider/log output first.

## Example

Save a current-source snapshot (full 40-character commit IDs only):

```json
{
  "repository": "woahwhattheheck/pocketpay-sdk",
  "pull_request": 21,
  "current_head": "16cf802c3a93ebb0cb5fb88ce6e3d093dd333f00",
  "checks": [
    {"id": "tests/trustline.test.ts"}
  ],
  "receipts": [
    {
      "check_id": "tests/trustline.test.ts",
      "head": "16cf802c3a93ebb0cb5fb88ce6e3d093dd333f00",
      "outcome": "not_run",
      "checked_at": "2026-10-08T01:57:00-04:00"
    }
  ]
}
```

```bash
python -m tools.paid_validation_receipts.audit /path/to/snapshot.json --format slack
python -m tools.paid_validation_receipts.audit /path/to/snapshot.json --format json --max-age-hours 168
```

The example generates `PERFORM_FOCUSED`; these tests are **not** falsely claimed to have run. Never substitute an authored fixture, typed PR description, or generic green check badge for the actual executed check's first-party log/receipt.

## Input schema and bounded decisions

- `repository`: exact GitHub `owner/name`; `pull_request`: positive PR number; `current_head`: the **current verified full** lower-case 40-hex SHA. This is an input claim, not a fresh GitHub read.
- `checks`: 1–200 unique focused check IDs (`[A-Za-z0-9_./:-]`, max 96), each as `{"id":"..."}`. A check should correspond to one required behavioral target or focused test command. Use stable IDs across fleet sessions.
- `receipts`: up to 1000 entries, each identifying a requested `check_id`, exact 40-hex `head`, timezone-aware `checked_at`, and `outcome: passed|failed|blocked|not_run`. Only actually executed `passed` or `failed` requires a real HTTPS `evidence_url` with no credentials or query fragments. `blocked` and `not_run` **must not** have an evidence URL; unexecuted source does not prove success.
- `max_age_hours`: defaults to 168 (7 days), configurable 1–720. Future-dated execution receipts are rejected. Input JSON rejects duplicate keys and oversize files, and refuses unrecognized fields or unknown check IDs.

| Decision | Meaning / next action |
| --- | --- |
| `REUSE_REPORTED_PASS` | Latest recorded executed check passed **at the identical complete source SHA** within chosen freshness window. Reuse the verified log rather than repeating the same focused check, subject to source/log review. |
| `SOURCE_HEAD_CHANGED` | Passing evidence only covers another commit; inspect the changed code and run the relevant focused check if needed, **not** a broad suite. |
| `PERFORM_FOCUSED` | No executed evidence on the exact head, or only `not_run`/`blocked` records. Execute the direct relevant check when acceptance requires it. |
| `FOCUSED_FIX_REQUIRED` | Latest exact-head executed check failed. Repair the acceptance behavior; never substitute an earlier pass. |
| `REVIEW_OLD_RECEIPT` | Exact-head pass exists but exceeds the selected age; review environmental dependencies and selectively refresh only if material. |
| `RECONCILE_RECEIPTS` | Mutually inconsistent executed outcomes have the same timestamp; resolve the evidence before deciding. |

The machine JSON output declares `external_evidence_authenticated: false`. Neither a `REUSE_REPORTED_PASS` result nor a saved `passed` record is an independent certification, a maintainer acceptance, a portal claim, a payout receipt, or permission to merge. This helper never triggers tests. If a HEAD changed but a particular check appears unaffected, an engineer must inspect the exact diff; this CLI deliberately will not call stale-head evidence a current pass.

Use `python -m unittest tools.paid_validation_receipts.test_audit` for **one focused local check** of this isolated component when validation is genuinely needed; do not run the Commons repository suites.
