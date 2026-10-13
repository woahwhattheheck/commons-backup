# Commons mail coordinator

A durable SQLite boundary that prevents parallel workers from contacting the same lead or replying to the same inbound at the same time.

The coordinator does **not** send email. A provider worker must:

1. record the newest inbound;
2. enqueue one exact outbound envelope under a stable operation ID;
3. atomically claim it;
4. mark the provider attempt immediately before the network call;
5. record the provider's accepted-message receipt before reporting `SENT`.

A timeout or broken connection becomes `UNCERTAIN`, not success and not permission to create a second operation. Read the provider's actual sent state, then record a receipt or reconcile the existing attempt as not sent.

## Guarantees

- SQLite `BEGIN IMMEDIATE` serialization prevents two workers from winning the same queue/claim race.
- An operation ID is idempotent and bound to the exact request hash.
- Active or sent correspondence is deduplicated by mailbox, overlapping recipient, and inbound/conversation scope; cold outreach also uses normalized subject.
- A newer inbound invalidates queued or merely claimed drafts. It exposes an unresolved in-flight attempt instead of silently replacing it.
- Recipient suppression invalidates unsent work and reports attempts that need provider-state reconciliation.
- Claim leases may be recovered only before a provider attempt starts.
- Only an explicit provider receipt—or reconciliation carrying that receipt—sets `SENT`.
- Status readback omits message bodies unless explicitly requested by a local operator.

## Run

Python 3.11+ and the standard library are sufficient.

```bash
cd services/mail-coordinator
python -m unittest discover -s tests -v
python -m mail_coordinator --db /private/path/mail.sqlite3 init
python -m mail_coordinator --db /private/path/mail.sqlite3 serve --host 127.0.0.1 --port 8788
```

The HTTP surface is JSON:

- `POST /v1/inbounds`
- `POST /v1/messages`
- `POST /v1/claims`
- `POST /v1/attempts`
- `POST /v1/receipts`
- `POST /v1/uncertain`
- `POST /v1/reconcile-not-sent`
- `POST /v1/suppressions`
- `GET /v1/messages/{message_id}`
- `GET /v1/ready`
- `GET /health`

The server binds to loopback by default. Keep the database on a private durable volume: it contains outbound message bodies. This component coordinates clients that call it; it does not intercept browser sends or unrelated email connectors.

## Minimal provider loop

```python
claim = coordinator.claim(
    operation_id="claim:lead-42:incoming-9",
    message_id="reply:lead-42:incoming-9",
    worker_id="gmail-worker-a",
)
attempt = coordinator.begin_attempt(
    operation_id="attempt:lead-42:incoming-9",
    claim_id=claim.claim_id,
)
try:
    provider_receipt = gmail_send(claim.envelope)
except TimeoutError:
    coordinator.mark_uncertain(
        operation_id="uncertain:lead-42:incoming-9",
        attempt_id=attempt["attempt_id"],
        detail="provider timeout; inspect Sent before any retry",
    )
    raise
else:
    coordinator.record_provider_receipt(
        operation_id="receipt:lead-42:incoming-9",
        attempt_id=attempt["attempt_id"],
        provider_message_id=provider_receipt.message_id,
        accepted_at=provider_receipt.accepted_at,
    )
```
