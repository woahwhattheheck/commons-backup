# Paid Outcome → Expansion / Renewal Rail

This package closes a commercial systems gap that appears **after** the first paid
proof is real: turning verified settlement + delivered/accepted work + a fresh,
buyer-authored next-step signal into a deterministic expansion/renewal packet.

It does **not** contact a buyer, negotiate a price, sign a contract, invoice,
charge, start fulfillment, or declare revenue. `EXPANSION_READY` and
`RENEWAL_READY` mean only that the supplied evidence is internally coherent
enough for a human commercial owner to review the next-phase catalog item.

## Why this exists

A sales system becomes unsafe if it conflates any of these facts:

1. a provider says funds settled;
2. a human buyer accepted delivery of the exact sold scope;
3. descriptive measurements were observed after delivery;
4. the buyer actually asked for a next phase or renewal;
5. the seller approved a concrete next-phase catalog item;
6. a new contract/payment/fulfillment event happened.

Those are separate authorities. This rail binds 1–5 and explicitly keeps 6 false.

## Input contract

Each packet is a JSON object with `schema_version: "1"` and a top-level `account_id`.
Every authority-bearing evidence object (`settlement`, `delivery_acceptance`,
`buyer_signal`, and `owner_approval`) must repeat that exact account identity;
cross-account relabeling or splicing fails closed. The packet also carries:

- `offer`: immutable offer/version, currency, exact expected cents, exact
  scope SHA-256, issue/expiry window.
- `settlement`: externally supplied provider evidence for the exact offer/version.
  It must be final `SETTLED`, same currency, at least the expected cents, with
  no refund or dispute, and bounded capture age.
- `delivery_acceptance`: exact offer/version/scope and an explicit
  `BUYER_HUMAN` acceptance event. A system/self assertion is not enough.
- `outcomes`: versioned *descriptive* metric definitions and baseline/observed
  windows. Causal claims are rejected. Metrics are evidence for a review, not
  attribution claims.
- `buyer_signal`: a fresh, `BUYER_AUTHORED` `EXPANSION_REQUEST` or
  `RENEWAL_REQUEST` naming specific catalog IDs.
- `owner_approval`: a human seller approval for exact catalog revisions. Each binding carries `catalog_id`, `version`, and the canonical full-row `row_digest`; ID-only approval is insufficient and fails closed.
- `catalog`: exact bounded price/scope/version entries. The rail never invents
  pricing. A catalog revision identity hashes ID, version, kind, currency, exact
  price cents, scope digest, and activation window. Buyer signal and owner approval
  must occur after that revision becomes active.
- `event_log`: caller-supplied evidence-event payloads. Exact duplicate event
  IDs collapse; changed payload under the same ID causes HOLD.

Time is caller-supplied as `as_of` so hermetic tests remain deterministic. The
authoritative caller is responsible for providing a trusted current time; this
module never treats its own wall clock as buyer/provider evidence.

## Decisions

A clean packet yields `EXPANSION_READY` or `RENEWAL_READY`. Any authority,
identity, freshness, scope, currency, settlement, metric, approval, catalog-revision,
or idempotency problem yields `HOLD` with stable reason codes. Reusing an approval
for the same catalog ID after a version, price, scope, currency, kind, or activation
change is explicitly rejected.

Every receipt hard-codes these authorities to `false`:

- buyer contact
- contract
- invoice/checkout
- payment
- fulfillment start
- recognized revenue
- causal impact claim

The SHA-256 `receipt_digest` is an **integrity digest only**. It is not a
signature and proves no author identity. Production signing belongs at an
owner-controlled integration boundary.

## Commands

From repository root:

```bash
python -m revenue.paid_outcome_expansion_rail.cli acceptance
python -m unittest revenue.paid_outcome_expansion_rail.test_rail
python -O -m unittest revenue.paid_outcome_expansion_rail.test_rail
```

Evaluate one packet:

```bash
python -m revenue.paid_outcome_expansion_rail.cli evaluate packet.json
```

Verify an emitted receipt:

```bash
python -m revenue.paid_outcome_expansion_rail.cli verify receipt.json
```

Exit code `2` means HOLD/invalid; no external side effect is performed.

## Synthetic acceptance

`acceptance.py` generates 120 deterministic synthetic accounts:

- 36 `EXPANSION_READY`
- 36 `RENEWAL_READY`
- 48 HOLDs, eight each for:
  - non-final settlement
  - refund present
  - acceptance scope mismatch
  - stale buyer signal
  - forbidden causal metric claim
  - missing owner catalog approval

The manifest must be identical when the 120 inputs are reversed, all receipts
must verify, and the exact decision/hold counts must match.
