# Stripe signed-event bridge

`host/stripe_event_bridge.py` closes the executable gap between a Stripe
webhook delivery and `host/checkout_handoff.py`'s conservative payment-truth
projector.  It does not create charges or claim revenue.

## Runtime contract

An HTTPS runtime passes three values to `normalize_signed_event`:

1. the exact raw request bytes, before JSON middleware changes them;
2. the complete `Stripe-Signature` header;
3. that endpoint's signing secret, supplied from the runtime's secret store.

The bridge verifies Stripe's timestamped v1 HMAC-SHA256 before parsing.  The
default tolerance is 300 seconds and cannot be disabled with zero.  It supports
multiple v1 signatures during secret rotation and uses constant-time
comparison.  Test and live endpoints require separate signing secrets.

After verification, the bridge requires the event's `livemode` boolean to
match the acceptance-locked request and requires exact Commons metadata,
including the envelope's `commons_dedupe_key`, plus currency and amount
binding.  Checkout Sessions also bind `client_reference_id` to the existing
CRM record.  A request-bound event becomes the existing
`commons-checkout-event/v1` observation and is revalidated by the existing
projector.  The first public-safe result is atomically persisted by provider
event id before acknowledgment.  A retry returns that first result and its
original observation time; conflicting bytes under one event id fail for
retry or quarantine.

Valid Stripe events that are unknown to the projector remain visible as
`SIGNED_UNKNOWN_EVENT`.  Known but unrelated or mismatched events become
`SIGNED_UNBOUND_EVENT`.  Neither includes raw provider data and neither enters
fulfillment.  This is observation, not a posting or Action Pad admission gate.

## CLI adapter

The command-line adapter reads the signature from a file or environment
variable and the signing secret only from an environment variable.  It never
accepts the secret as a command-line argument.

```powershell
$env:STRIPE_WEBHOOK_SECRET = '<runtime secret value>'
$env:STRIPE_SIGNATURE_HEADER = '<exact Stripe-Signature header>'
python host/stripe_event_bridge.py `
  --request revenue/checkout_handoff/example_request.json `
  --payload path/to/exact-raw-body.json `
  --receipt-dir path/to/private-runtime-receipts
```

Do not commit either value or raw buyer payloads.  The command persists only
the returned public-safe result before reporting `RECORDED`; a later delivery
reports `REPLAYED` and returns the first result.  A deployed HTTP adapter must
do the same before returning 2xx, then append `observation` to the existing
checkout projector only when status is `NORMALIZED`.  Durable-write failure is
retryable and must not be acknowledged as success.

## Measured boundary

- Signature verification proves source integrity, not payment or cash.
- A paid Checkout Session or successful PaymentIntent can confirm payment
  authorization and permit the already agreed delivery clock.
- Aggregate `balance.available` and `payout.paid` events are not promoted to a
  request-specific observation because they lack the acceptance binding.
- A payout observation still would not prove that funds posted at the bank.
- Bank availability remains a separate private readback and is never inferred
  by this bridge.
- The currently connected Token Junkie Labs Stripe app is sandbox-only.  The
  same read-only capability checks must be rerun after the actual live account
  is connected; sandbox events and balances are not revenue.

Official provider behavior: Stripe requires the raw body for signature
verification, signs `timestamp + "." + raw_body` with HMAC-SHA256, can include
multiple v1 signatures during secret rotation, and recommends a five-minute
timestamp tolerance plus event-id deduplication.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

