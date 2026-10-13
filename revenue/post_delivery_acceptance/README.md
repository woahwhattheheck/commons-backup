# Post-delivery buyer-acceptance evidence

A buyer-neutral, standard-library-only evidence compiler for the boundary **after technical delivery** and **before earned/revenue/payment claims**.

Existing Commons rails already separate accepted scope, execution evidence, delivery, and settlement. This package answers a narrower question: **did the counterparty accept this exact delivered version against the milestone's exact criterion set?**

## Truth boundary

These are intentionally different:

- technical acceptance rows PASS → our evidence says the work met the declared checks;
- `DELIVERED` → transport/counterparty evidence says this exact version was delivered;
- `BUYER_ACCEPTED_EVIDENCE` → verified counterparty evidence accepts every required criterion on this exact delivered version.

No state here authorizes fulfillment, contact, payment, invoicing, accounting, revenue recognition, testimonial/endorsement use, or a legal/contractual conclusion.

A new deliverable version never inherits buyer acceptance from an older version.

## Evidence authorities

- `DELIVERED`: `delivery_transport` or `counterparty_evidence`;
- `BUYER_DISPOSITION`: **counterparty_evidence only**;
- `SUPERSEDED`: `owner_approved`.

Internal/owner evidence cannot mint buyer acceptance.

## States

- `DELIVERED_PENDING_BUYER_ACCEPTANCE`
- `PARTIALLY_ACCEPTED_EVIDENCE`
- `BUYER_ACCEPTED_EVIDENCE`
- `REVISION_REQUIRED`
- `REJECTED`
- `HOLD`

Revision/rejection events bind the entire criterion set. Criterion-level ACCEPTED evidence can arrive incrementally. Required criteria determine full acceptance; optional criteria remain visible in the version binding but do not block full required-criterion acceptance.

## Exact version binding

Every event binds a SHA-256 of the immutable version core:

- version + milestone IDs and ordinal;
- artifact ref + artifact SHA-256;
- exact criterion IDs;
- upstream scope-agreement SHA-256;
- upstream delivery-receipt SHA-256;
- version creation time.

Changing or transplanting any of those fields invalidates the event.

## CLI

```bash
python revenue/post_delivery_acceptance/post_delivery_acceptance.py compile \
  --input revenue/post_delivery_acceptance/examples/synthetic_delivery.json \
  --json-out /tmp/acceptance.json \
  --markdown-out /tmp/acceptance.md \
  --csv-out /tmp/acceptance.csv

python revenue/post_delivery_acceptance/post_delivery_acceptance.py verify \
  --input revenue/post_delivery_acceptance/examples/synthetic_delivery.json \
  --ledger /tmp/acceptance.json
```

`--fail-on-hold` exits `2` when any milestone is HOLD. Outputs are create-exclusive and final-component symlinks are refused.

## Tests

```bash
python -m py_compile revenue/post_delivery_acceptance/post_delivery_acceptance.py
python -m unittest discover -s revenue/post_delivery_acceptance -p 'test_*.py' -v
python -O -m unittest discover -s revenue/post_delivery_acceptance -p 'test_*.py' -v
```

The synthetic fixture is not a real buyer or contract. It demonstrates one fully buyer-accepted milestone and one delivered-but-not-accepted current version.
