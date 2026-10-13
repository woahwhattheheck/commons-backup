# Commercial Offer Contract Rail

This package turns a scoped commercial opportunity into a deterministic, tamper-evident offer contract without confusing a draft with a send, buyer acceptance, fulfillment, payment, or revenue.

## Why this exists

Revenue work currently has strong opportunity discovery, qualification, submission, settlement, and closeout primitives. The missing middle is a reusable authority boundary for a **non-bounty commercial service offer**: exact money, exact deliverables, exact acceptance terms, owner approval, and an explicit destination-bound send authorization.

The rail is intentionally side-effect-free. It creates evidence and authority receipts; it does not send email, mutate a provider, create a checkout, perform fulfillment, collect payment, or recognize revenue.

## State machine

1. `compile_offer(spec)` validates and normalizes exact offer terms and emits `READY_FOR_OWNER_APPROVAL`.
2. `approve_offer(..., owner_secret, key_id, approved_at)` emits an HMAC-SHA256 owner approval bound to the exact canonical offer bytes and moves to `OWNER_APPROVED`.
3. `authorize_send(..., destination_sha256, channel, authorized_at)` emits a second HMAC receipt bound to the offer, owner approval, exact destination digest, channel, and authorization time. Only then is `external_send_authorized=true`; no send occurs here.
4. `capture_buyer_acceptance(...)` captures content-addressed acceptance + identity-verification evidence for the exact offer/buyer while deliberately leaving `buyer_acceptance_verified=false` and `fulfillment_authorized=false`. A downstream human/provider authority must decide those states.

`payment_collected` and `revenue_recognized` are invariantly false. This rail cannot self-assert either.

## Contract invariants

- Money is integer minor units only. Python `bool`, float, decimal strings, NaN/Infinity, and coercive values are rejected.
- Currency is exactly three uppercase ASCII letters.
- Every deliverable is assigned to exactly one milestone; milestone amounts must sum exactly to `total_amount_minor`.
- Deliverables carry explicit acceptance criteria and an evidence SHA-256.
- Input schemas are exact; unknown fields fail closed.
- JSON ingestion can use `load_json_strict()` to reject duplicate keys and non-finite values.
- Time is canonical whole-second UTC `...Z`; approval, send authorization, and buyer acceptance are fenced to the offer validity period.
- Owner HMAC secrets must be at least 32 bytes and are never embedded in output.
- Send authority is bound to a SHA-256 of the exact destination identity rather than retaining the address/account itself.
- Buyer acceptance evidence is bound to the exact offer digest and opaque `buyer_ref`.

## Example

```python
from revenue.commercial_offer_contract.offer_contract import compile_offer, approve_offer, authorize_send

compiled = compile_offer(spec)
approved = approve_offer(compiled, owner_secret, key_id="sales-owner-v1", approved_at="2026-09-13T10:00:00Z")
ready = authorize_send(
    approved,
    owner_secret,
    destination_sha256=destination_digest,
    channel="email",
    authorized_at="2026-09-13T10:05:00Z",
)
```

The caller still performs the external send. A transport integration should verify `verify_send_authority()` immediately before dispatch using trusted current time and the same owner secret.

## Validation

Run from the repository root:

```bash
python -m unittest -v revenue.commercial_offer_contract.test_offer_contract
python -O -m unittest -v revenue.commercial_offer_contract.test_offer_contract
python -m py_compile revenue/commercial_offer_contract/offer_contract.py revenue/commercial_offer_contract/test_offer_contract.py
```

The hostile suite covers coercive money, milestone arithmetic, duplicate/unknown deliverables, schema drift, duplicate JSON keys, non-finite JSON, timestamp/currency bounds, weak/wrong owner secrets, offer/approval/destination tampering, unsupported channels, expiry, mismatched buyer/offer acceptance, future acceptance, and forbidden payment/revenue self-assertion.
