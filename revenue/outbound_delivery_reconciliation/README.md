# Outbound Delivery Reconciliation

Offline, fail-closed reconciliation for one exact provider-SENT outbound generation and later provider events such as DSNs/bounces.

This package exists because provider transport truth can change after Gmail records a message as SENT. A later no-such-user, mailbox-full, group/policy restriction, remote rejection, or unknown permanent failure must not remain represented as a live delivered/contacted route.

## Outcomes

- `SENT_PENDING_PROVIDER_TRUTH` — no permanent failure is present.
- `DELIVERY_FAILED` — at least one compatible permanent provider failure is bound to the exact sent generation.
- `HOLD_CONFLICTING_PROVIDER_EVIDENCE` — event identity forks, impossible chronology, cross-message/recipient/buyer/opportunity contamination, or incompatible terminal provider evidence.

A provider-accepted event by itself does **not** become a buyer-delivery/read/response claim. This product only reconciles delivery failures.

Provider acceptance followed by a later permanent failure is a normal bounce
sequence and yields `DELIVERY_FAILED`. Acceptance at the same timestamp as, or
after, a permanent failure remains conflicting evidence for that exact sent
generation. Neither sequence grants retry or alternate-route authority.

## Authority ceiling

`DELIVERY_FAILED` sets `failed_route_dnr=true`. Every report hard-codes:

- `alternate_route_authorized=false`
- `retry_authorized=false`
- no buyer rejection or opt-out assertion
- no buyer acceptance assertion
- no payment, cash, or revenue assertion

The original relationship/outbound owner retains all contact authority. A failed exact route is DNR; this package cannot discover or authorize another address.

## Clock boundary

`reconcile(original, events)` owns the current UTC clock. There is no public caller-selected current-time parameter. `verify()` replays the report's receipt-bound historical instant only to verify integrity; it is non-authorizing.

## Schemas

Original record (`outbound-delivery-original/v1`) binds:
`provider_message_id`, normalized `recipient`, canonical lowercase `buyer_scope`, `opportunity_id`, canonical UTC `sent_at`, and `evidence_sha256`.

Provider event (`outbound-delivery-provider-event/v1`) additionally binds stable `event_id`, exact original identity fields, `observed_at`, `event_kind`, reason code, and `evidence_sha256`.

`event_kind` is `PERMANENT_FAILURE` or `PROVIDER_ACCEPTED`. Permanent failures use one of:
`NO_SUCH_USER`, `MAILBOX_FULL`, `POLICY_OR_GROUP_RESTRICTION`, `REMOTE_REJECTION`, `UNKNOWN_PERMANENT_FAILURE`.

Exact replay of an event ID with identical canonical bytes is idempotent. Same ID with changed bytes HOLDs.

All distinct variants of a forked event ID remain bound into the source-generation
digest and evidence list, in deterministic order. Reordering or repeating input
events cannot hide a permanent failure or change the result. Event IDs remain
unique in the report even when several conflicting variants share one ID.

## CLI

```bash
python -m revenue.outbound_delivery_reconciliation.cli compile \
  --original original.json --events events.json

python -m revenue.outbound_delivery_reconciliation.cli verify \
  --report report.json --original original.json --events events.json
```

The CLI performs no network/provider I/O.

Each input read is bounded to 2 MiB before parsing. Duplicate object keys and
non-finite numeric constants are rejected with exit code 2, so ambiguous input
cannot silently replace a failure event or a report field during JSON decoding.
