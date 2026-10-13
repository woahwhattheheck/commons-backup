# Acceptance-locked checkout handoff

This package closes the mechanical gap between a buyer-approved binary scope,
a customer-specific hosted checkout, one existing Airtable opportunity, and a
truthful delivery-start decision. It extends the canonical Outcome Commerce
catalog; it does not create a new SKU, CRM, table, payment address, or public
buyer record.

## Flow

1. A buyer's one non-confidential sentence is converted into the exact
   Given/When/Then acceptance object in `request.schema.json`.
2. The buyer's written acceptance locks that object, its SHA-256 digest, the
   existing Airtable record ID, the canonical SKU, price, delivery window,
   exclusions, and refund election.
3. `host/checkout_handoff.py build` re-reads the canonical Outcome Commerce
   catalog and emits a Stripe-hosted Checkout Sessions request envelope. The
   envelope contains no provider credential, customer private data, raw card
   data, or reusable public payment link. It omits `payment_method_types` and
   automatic tax; tax must not be enabled without verified registrations.
4. A server-side provider adapter creates exactly one Checkout Session using
   the emitted idempotency key. Raw provider payloads stay private. Only the
   opaque provider reference, event type, public-safe facts, and payload digest
   enter `event.schema.json` after provider signature verification.
5. `project` deduplicates provider event IDs, keeps authorization, settlement,
   payout, and bank availability distinct, and emits an update plan for the
   existing Airtable row. It never creates a record or changes Stage.
6. Delivery can start only after acceptance is locked and a verified payment
   authorization observation exists. A refund disables delivery. A paid payout
   is still not bank availability; only a separate positive private bank
   readback can set `BANK_AVAILABLE` and `cash_claimed=true`.

## Commands

```text
python host/checkout_handoff.py digest --request revenue/checkout_handoff/example_request.json
python host/checkout_handoff.py build --request revenue/checkout_handoff/example_request.json
python host/checkout_handoff.py project --request revenue/checkout_handoff/example_request.json --events revenue/checkout_handoff/example_events.json
python -m unittest test_checkout_handoff.py
```

The checked-in example is synthetic and sandbox-labelled. It demonstrates the
state separation but is not a buyer, accepted scope, Checkout Session, payment,
delivery, payout, bank posting, or revenue receipt.

## Runtime boundary

The current connected Stripe context is `Token Junkie Labs sandbox`; therefore
this repository artifact can be validated in test mode but cannot activate a
live $2,500 customer checkout by itself. Production activation requires a live
provider context configured in the provider's hosted surface. Private provider
and bank values never belong in Commons, Slack, Airtable notes, prompts, logs,
or receipts.

`AUTHORIZATION != SETTLEMENT != PAYOUT != BANK_AVAILABLE`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

