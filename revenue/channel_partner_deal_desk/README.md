# Channel Partner Deal Desk

A local-first operations product for firms that sell through agencies, systems integrators, referral partners, marketplaces, or other channel relationships.

The desk answers a concrete revenue-operations question without hand-waving: **which partner owns which protected opportunity, which exact commercial terms govern it, what externally evidenced buyer/payment events have occurred, and what commission is arithmetically due for owner review?**

It is software, not a proof memo. State is persisted in SQLite, mutations are idempotent, deal registrations are collision-safe, old deals remain bound to the exact terms generation they were registered under, exact minor-unit commission math survives restarts, and deterministic JSON/CSV/Markdown exports carry content hashes.

## Why this exists

Partner programs create a distinct failure mode from direct sales. A company can win a buyer and still lose margin or partner trust because:

- two partners claim the same buyer/opportunity;
- the referral terms changed after registration and nobody knows which revision applies;
- buyer acceptance happened after a protection window expired;
- settlement, reversal, and partner-payment evidence are mixed together;
- a commission is described as “paid” because someone approved it, rather than because payment evidence was actually recorded;
- spreadsheets are overwritten and old attribution history disappears.

This desk keeps those states mechanically separate.

## Authority boundary

The strongest state, `COMMISSION_DUE_FOR_OWNER_REVIEW`, means the supplied evidence and the deal-bound terms compute a positive outstanding commission. It is **not** a payment instruction, debt/legal conclusion, accounting conclusion, or revenue-recognition statement.

`PAID_EVIDENCE` means an operator supplied a distinct `PARTNER_PAYMENT_RECORDED` event with evidence metadata and the recorded amount exactly covers the computed commission. The program does not independently inspect a bank/provider and does not move money.

The program performs **no network calls, email/DM/contact-form sends, CRM writes, provider mutations, invoice issuance, charges, refunds, payouts, contract signing, accounting posting, or customer/partner acceptance inference**.

## Core contract

### Partner terms generations

Each immutable terms row binds:

- partner ID and revision;
- commission basis points (0–10,000);
- registration-protection window in days;
- `SETTLED_PAYMENT` trigger;
- effective time;
- operator-supplied source reference + SHA-256;
- canonical terms SHA-256.

A deal binds one exact `terms_id`. Later terms do not rewrite old deals.

### Collision-safe deal registration

The pair `(buyer_key, opportunity_key)` is globally protected by the first successful registration. A second claim becomes `HOLD_REGISTRATION_CONFLICT` and is durably recorded; it does not silently overwrite the first partner.

All buyer/opportunity identifiers are opaque operator-defined keys. The desk does not discover or contact buyers.

### Event ledger

Supported evidence events:

- `BUYER_ACCEPTED`
- `BUYER_DECLINED`
- `PAYMENT_SETTLED`
- `PAYMENT_REVERSED`
- `PARTNER_PAYMENT_RECORDED`
- `DEAL_CANCELLED`

Financial events require prior buyer-acceptance evidence and the exact deal currency. Reversals cannot exceed supplied settlement evidence. Partner-payment evidence cannot exceed the currently computed commission.

Commission is exact integer minor-unit arithmetic:

`floor(net_settled_minor * commission_bps / 10_000)`

No floating-point money is accepted.

### Deterministic states

A registered deal compiles to one of:

- `REGISTERED`
- `DECLINED`
- `CANCELLED`
- `HOLD_PROTECTION_EXPIRED`
- `ATTRIBUTED_AWAITING_SETTLEMENT`
- `ATTRIBUTED_NO_COMMISSION`
- `COMMISSION_DUE_FOR_OWNER_REVIEW`
- `PAID_EVIDENCE`
- `HOLD`

Buyer acceptance must be evidenced no later than the deal's computed protection expiry to create attributed commission eligibility. A late acceptance remains visible but is held instead of being silently credited.

## Idempotency and concurrency

Every mutation takes an `operation_key`. Replaying the same key with identical semantic input returns the original result. Reusing the key with changed input fails closed.

Mutations run under SQLite `BEGIN IMMEDIATE`; unique constraints protect partner-term revisions, event IDs, and buyer/opportunity registrations across concurrent/restarted operators.

## Exports

`export` writes create-exclusive files:

- `channel_partner_snapshot.json`
- `channel_partner_deals.csv`
- `channel_partner_review.md`
- `SHA256SUMS.json`

The JSON snapshot includes an internal SHA-256 over the semantic body. `verify-export` recompiles the current database and requires exact snapshot bytes plus all artifact hashes to match. Existing artifacts are never overwritten.

## Operator mutations

The CLI accepts strict JSON mutation envelopes, so an operator does not need to edit Python or the SQLite file directly:

```bash
python channel_partner_deal_desk.py apply ./desk.sqlite ./mutation.json
```

Supported actions are `ADD_PARTNER`, `ADD_TERMS`, `REGISTER_DEAL`, and `ADD_EVENT`. Unknown fields, duplicate JSON keys, non-finite values, symlink/nonregular input, and files over 1 MiB fail closed. Every mutation carries its own stable `operation_key` for replay safety.

## Demo

From this directory:

```bash
python channel_partner_deal_desk.py demo /tmp/channel-partner.sqlite /tmp/channel-partner-export
python channel_partner_deal_desk.py verify-export /tmp/channel-partner.sqlite /tmp/channel-partner-export
```

The synthetic demo records a 12.5% partner relationship, registers a $15,000 opportunity, records buyer-acceptance and settlement evidence, and ends in `COMMISSION_DUE_FOR_OWNER_REVIEW` with a $1,875 computed commission. It does not contact anyone or move money.

## Validation

```bash
python -m py_compile channel_partner_deal_desk.py test_channel_partner_deal_desk.py
python -m unittest -v test_channel_partner_deal_desk.py
python -O -m unittest -v test_channel_partner_deal_desk.py
```

The hostile suite covers idempotent replay, changed-operation conflicts, competing deal registration, terms-generation binding, protection-window expiry, acceptance/currency gates, reversals, overpayment rejection, restart-safe export verification, export tamper, overwrite refusal, bool/int money traps, strict duplicate-key/non-finite JSON, stable snapshots, and a real end-to-end demo.

## Commercial shape

This is suitable as an installable operations workspace for consultancies and product companies that use referral/SI/channel programs. A commercial engagement can include importing an operator's current partner terms and open registrations, configuring its opaque buyer/opportunity keys, and installing the deterministic owner-review export. Pricing, legal interpretation of partner agreements, actual payout approval, and any external partner communication remain owner decisions outside this software.
