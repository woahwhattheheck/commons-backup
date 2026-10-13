# Outbound Transport Reconciler

`outbound_transport_reconcile` closes a specific commercial-operations gap: a Gmail message can be provider-`SENT` while the Slack sales/coordination ledger has no matching send receipt. A worker who trusts only Slack can then duplicate prospect contact.

This package is deliberately **provider-free**. It consumes complete normalized snapshots supplied by a trusted caller and performs no Gmail, Slack, network, CRM, customer, payment, or deployment action itself.

## Trust contract

A Gmail SENT row is transport evidence only when the normalized snapshot carries its exact opaque provider `message_id`, recipient identity as a SHA-256 digest, canonical `sent_at`, and evidence digest. A Slack send receipt is bound only when it cites the same provider message ID and the same recipient digest. No subject, company name, domain, timestamp-nearness, or fuzzy matching can turn two rows into a match.

Both snapshots must declare `complete=true`, be current under the supplied policy, and contain no future/chronologically impossible rows. Exact stable-ID replay collapses. Stable-ID reuse with changed canonical bytes holds the entire reconciliation.

Every distinct conflicting variant remains in the normalized snapshot digest and
chronology checks. Reordering a snapshot cannot choose which evidence survives,
and changing any variant changes the bound digest. Counts
remain counts of unique provider message IDs and Slack event IDs; conflicting
variants do not inflate send or receipt totals. Conflict-free snapshots and exact
replays retain their previous normalization.

Report schema `outbound-transport-reconcile-report/v2` binds `common_coverage_through`, the earlier of the two complete snapshot capture times. Negative evidence is allowed only when the counterpart snapshot actually covers the event: a Gmail SENT row newer than the Slack capture cannot become `PROVIDER_SENT_NOT_RECORDED`, and a Slack-only claim newer than the Gmail capture cannot become `SLACK_SENT_WITHOUT_PROVIDER_SENT`; those cases HOLD instead. A bound Slack send receipt also cannot predate the Gmail provider `sent_at`. Positive matching evidence may be recorded after the common horizon when its provider event is already present and its chronology is valid.

The v1 normalized record model intentionally carries one `recipient_sha256` per provider message. A caller must therefore normalize only single-recipient commercial sends into this schema. A multi-recipient provider message is outside the v1 acquisition contract and must not be projected to one recipient as if that represented the complete transport fact; retain it outside this artifact or move to a future recipient-set schema.

## Outcomes

The aggregate report is exactly one of:

- `LEDGERS_CONSISTENT`: every bound Slack send receipt has provider SENT evidence and every provider SENT row has exactly one same-recipient Slack receipt.
- `RECONCILIATION_REQUIRED`: valid complete snapshots contain an exact discrepancy such as `PROVIDER_SENT_NOT_RECORDED`, `SLACK_SENT_WITHOUT_PROVIDER_SENT`, `SLACK_RECEIPT_UNBOUND`, `PROVIDER_RECIPIENT_CONFLICT`, or `DUPLICATE_OR_CONFLICTING_RECEIPT`.
- `HOLD`: the snapshots cannot safely support reconciliation because completeness, freshness, chronology, common coverage, or stable-ID integrity is missing.

A discrepancy is a ledger fact, **not send authority**. In particular, `PROVIDER_SENT_NOT_RECORDED` must never be interpreted as permission to resend. Every report fixes Gmail write, Slack write, customer contact, resend, payment, and revenue-recognition authority to `false`.

## PII boundary

Durable input/output uses `recipient_sha256`; raw email addresses, subject/body text, names, notes, credentials, tokens, and message content are outside this artifact.

## Library

```python
from datetime import datetime, timezone
from revenue.outbound_transport_reconcile import compile_report, verify_report

report = compile_report(gmail_snapshot, slack_snapshot, policy, as_of=datetime.now(timezone.utc))
assert verify_report(report, gmail_snapshot, slack_snapshot, policy, as_of=datetime.now(timezone.utc))
```

The caller owns snapshot acquisition/authentication. Compile-time `as_of` is an out-of-band trusted clock input; it is never selected from either snapshot. Verification recomputes the receipt at the report's bound historical `as_of` and uses verifier-owned current UTC only to reject a future-dated report, so a valid receipt remains auditable after its creation second. The verifier also recomputes and binds `common_coverage_through`; tampering or replay against different capture horizons fails verification.

## CLI

The production CLI samples UTC internally:

```bash
python -m revenue.outbound_transport_reconcile.reconcile compile \
  --gmail gmail.json --slack slack.json --policy policy.json --report report.json

python -m revenue.outbound_transport_reconcile.reconcile verify \
  --gmail gmail.json --slack slack.json --policy policy.json --report report.json
```

Inputs are bounded regular UTF-8 files parsed with duplicate-key and non-finite-number rejection. Report creation is create-exclusive and refuses an existing/final-component-symlink target.

## Authority ceiling

This package never reads or writes Gmail/Slack, never sends/retries/reroutes a message, never infers buyer intent/acceptance, never mutates a CRM or contract, and never authorizes payment, cash, or revenue recognition.
