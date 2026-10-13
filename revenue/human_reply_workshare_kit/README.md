# Human-reply → paid-workshare kit

Buyer/partner interest is not acceptance, and a warm reply is not revenue. This package turns a genuine human routing/interest event into a **bounded fixed-fee workshare proposal** while keeping those states separate.

It ships three reusable one-page commercial carriers:

1. **Data Migration + Integration Acceptance** — source→target reconciliation, interface replay/idempotency, UAT/cutover evidence.
2. **Responsible-AI / LLM Evaluation + Governance Evidence** — role/scenario evaluation, deterministic replay, governance evidence mapping.
3. **Operational / Financial Evidence Reconciliation** — read-only closed-period reconciliation, deterministic exception ledger, owner-review pack.

Each pack states a fee band, delivery band, deliverables, acceptance conditions, exclusions, milestones, intake/security gates, and the authority that remains with the buyer/prime.

## Hard commercial boundaries

The compiler accepts only `commercial_state = PROPOSED_NOT_ACCEPTED`. It also requires every evidence flag to remain false:

- buyer accepted
- customer relationship
- signed contract
- invoice issued
- payment settled
- booked revenue
- recognized revenue

If any flag is true, the compiler refuses the record and tells the caller to use a separate evidence-backed workflow. Free-text scope also rejects common unsupported assertions such as “buyer accepted,” “award secured,” “payment received,” “booked revenue,” and guaranteed savings/outcomes.

The generated one-pager explicitly says that routing, interest, and silence are not commitments. Any change to scope, price, deadline, currency, source, or acceptance requires a new offer revision rather than silently rolling forward an old price.

## Compile

```bash
python -m revenue.human_reply_workshare_kit revenue/human_reply_workshare_kit/example.synthetic.json
```

Deterministic receipt:

```bash
python -m revenue.human_reply_workshare_kit \
  revenue/human_reply_workshare_kit/example.synthetic.json \
  --format receipt
```

The receipt hashes the normalized offer. A scope or commercial-term change changes the receipt.

## Test

```bash
python -m unittest revenue.human_reply_workshare_kit.test_core -v
```

The test suite covers all three packs, price/duration bounds, strict JSON (including duplicate keys and floats), positive commercial-state claim rejection, dangerous free-text claims, deterministic receipts, milestone ordering, and stale-term warning presence.

## Source packs

- [`packs/data_migration_acceptance.md`](packs/data_migration_acceptance.md)
- [`packs/responsible_ai_evaluation.md`](packs/responsible_ai_evaluation.md)
- [`packs/financial_evidence_reconciliation.md`](packs/financial_evidence_reconciliation.md)

These are buyer-neutral templates. They are not claims about a named customer, award, acceptance, payment, or realized outcome.
