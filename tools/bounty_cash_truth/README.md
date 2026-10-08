# Bounty cash truth — source and payment reconciliation

This tool provides **read-only**, offline classification of author/claim/merge/award/payout records for a fleet executing many independent bounty tasks. Its purpose is to prevent **platform onboarding ≠ claimant verification ≠ accepted PR ≠ award ≠ cash received** from being collapsed into one green flag.

## Usage

```sh
python tools/bounty_cash_truth/audit.py evidence.json > receipt.json
python -m unittest discover -s tools/bounty_cash_truth -p 'test_audit.py'
```

The input object requires an offset-aware `snapshot_at` and `records`. Each record uses `id`, a canonical sponsor `pr_url`, nonnegative `advertised_usd` (an *offer*, never an invoice), and optional evidence objects for `payment_setup`, `claim`, `merge`, `award`, `payment`. Evidence objects need `status`, `source_kind`, `source_url`, `observed_at`. For a verified marketplace claim, additionally require `claim.pr_url` to equal the exact sponsor PR. A verified merge needs matching `merge.pr_url` from GitHub. A **cash receipt** needs `payment.status=received`, independent `source_kind=processor|bank|chain`, a `receipt_id`, positive `amount`, cash `currency`, clean HTTPS `source_url`, and a timestamp not later than the snapshot. Non-redeemable credits are not cash.

```json
{
  "snapshot_at": "2026-10-08T06:00:00Z",
  "records": [{
    "id": "bh-claim-3155-2994",
    "pr_url": "https://github.com/example-org/test-project/pull/42",
    "advertised_usd": "4999",
    "payment_setup": {"status":"unverified","source_kind":"marketplace","source_url":"https://example.test/marketplace/claim","observed_at":"2026-10-08T06:00:00Z"},
    "claim": {"status":"registered","source_kind":"marketplace","pr_url":"https://github.com/example-org/test-project/pull/42","source_url":"https://example.test/marketplace/claim","observed_at":"2026-10-08T06:00:00Z"},
    "merge": {"status":"open","source_kind":"github","pr_url":"https://github.com/example-org/test-project/pull/42","source_url":"https://github.com/example-org/test-project/pull/42","observed_at":"2026-10-08T06:00:00Z"}
  }]
}
```

**Example is synthetic illustrative input, not a newly verified provider observation.** The tool does not verify that a named `source_url` actually says what the input asserts; intake operators must attach credible, point-in-time provider readbacks before treating results as evidence. Outputs include a next-action category but **never take actions**. No automatic emails, GitHub claims, portal registrations, provider polling, scheduled checks, escrow claims, or payout assertions.

## Operational rules

- Distinguish `advertised_usd_not_receivables` from `cash_receipts_by_currency`. Keep separate totals per currency.
- `MERGED_CLAIM_UNVERIFIED`: pursue retrospective eligibility decision, not duplicate claim registration.
- `MERGED_REGISTERED_NO_AWARD`: obtain actual sponsor/platform award decision rather than promise payment.
- `AWARD_RECORDED_NOT_PAID`: verify existing payout setup/settlement, not mark cash received.
- `CASH_RECEIPT_RECORDED`: reconcile independent processor/bank/chain evidence with an actual statement; user-supplied evidence is not itself an audited accounting conclusion.
- Do not echo secret-bearing query strings, account IDs, wallet addresses, or payment details into Slack; output intentionally contains no source bodies, payout email, credential URLs, receipt IDs, or raw provider payloads.
