# Portfolio Execution Handoff

`portfolio_execution_handoff` is the fail-closed bridge between a verified
`revenue/opportunity_portfolio` selection and a human owner deciding what to do next.

The upstream portfolio is authoritative for **what is selected**. This package does
not add opportunities, re-rank them, contact anyone, or convert a selected row into
commercial authority. It binds every `EXECUTE_NOW` row to fresh custody evidence,
a named owner, one bounded next-action class, and an exact destination/evidence
reference for human review.

## Contract

Compilation first calls the upstream portfolio's independent `verify_receipt()`.
The packet then requires exact one-to-one coverage of the selected portfolio:
missing selected work and handoffs for unselected work both HOLD the packet.

Each handoff binds:

- selected opportunity ID and upstream source SHA-256;
- owner seat;
- custody state, positive generation, claim time, and exact evidence-bound claim reference;
- bounded next-action class and summary;
- exact evidence-bound destination reference;
- expiry.

Accepted reference classes are deliberately narrow: exact Slack message references
and exact GitHub issue/PR comment references. Mutable branch, homepage, channel, or
generic URL references are refused.

`trusted_as_of` is supplied out of band. A handoff is not review-ready when its
claim is in the future, custody is released, its source is stale, its opportunity
deadline has closed, the packet is expired, the expiry crosses the opportunity
deadline, or the handoff lifetime exceeds 24 hours. Re-verification may supply a
later trusted time so a historically valid receipt cannot be replayed indefinitely.

For opportunities already marked `OWNED_BY_THIS_SEAT`, the handoff owner must match
the upstream actor seat. An `AVAILABLE` opportunity may carry a post-selection claim,
but this artifact **records** that claim evidence; it does not grant custody.

## States

Per row:

- `READY_FOR_OWNER_REVIEW`
- `HOLD`

Whole packet:

- `READY_FOR_OWNER_HANDOFF_REVIEW`
- `HOLD`

The strongest state remains review-only. Every external-action authority flag is
false.

## CLI

```bash
python -m revenue.portfolio_execution_handoff.cli compile handoff.json \
  --trusted-as-of 2026-09-13T10:10:00Z \
  --receipt handoff-receipt.json \
  --markdown handoff.md

python -m revenue.portfolio_execution_handoff.cli verify handoff-receipt.json \
  --trusted-as-of 2026-09-13T10:20:00Z
```

`verify` always checks the receipt digest, normalized-input digest, upstream
portfolio verification, and deterministic recompilation. With `--trusted-as-of`,
it additionally re-evaluates current freshness/expiry and fails if the packet is no
longer review-ready.

## Authority boundary

This package cannot send outreach, reply to a buyer, submit a bid or bounty claim,
spend funds, sign or amend a contract, mutate a provider, execute/refund a payment,
infer acceptance, fulfill work, or recognize revenue. It also refuses common
secret-shaped and PII-shaped metadata in handoff material.
