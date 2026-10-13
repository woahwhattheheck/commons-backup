# Revenue Targeting Allocator

Issue: #14443  
Operation: `COMMONS-REVENUE-TARGETING-ALLOCATOR-ZPBF6N2-20260914`

This package turns **explicit owner-retained facts about already-existing offers and opportunities** into a deterministic owner-review priority queue. It is portfolio strategy infrastructure, not an outreach engine.

## Safety and authority ceiling

The allocator never contacts a prospect, changes a provider or CRM, moves money, recognizes revenue, infers buyer interest, or grants send authority. Every row, output, receipt, and verification result keeps:

- `external_send_authorized=false`
- `provider_mutation_authorized=false`
- `payment_or_revenue_inferred=false`

A high rank is only a recommendation about where an owner may want to spend scarce review attention. Separate contact locks, provider-history checks, route controls, turn leases, content review, and provider execution remain mandatory.

## Input contract

Input schema: `revenue-targeting-allocator-input/v1`.

Each candidate binds one stable opportunity to one stable offer and includes only explicit facts:

- proposed commercial value in integer minor units and one uppercase three-letter currency;
- optional owner-supplied `probability_bps` (integer `0..10000`);
- verified route state;
- relationship/DNR state;
- collision/custody state;
- evidence freshness;
- buyer stage plus buyer-stage verification state;
- offer fit;
- delivery readiness;
- SHA-256 of the retained evidence bundle.

The allocator rejects duplicate opportunity/offer identities and rejects switching one opportunity between offers in the same generation.

## HOLD dominates value

A candidate is never eligible for ranking when any of these are not clean:

- commercial value is non-positive;
- route is not `VERIFIED_CLEAR`;
- relationship state is DNR, opt-out, conflict, or unknown;
- collision state is not clear;
- evidence is stale or unknown;
- buyer-stage evidence is conflicted or unknown;
- fit is unknown;
- delivery is not ready.

This means a $100k DNR lead remains HOLD while a smaller clean opportunity can rank.

## Ranking policy

The allocator deliberately refuses two common forms of fabricated precision:

1. **No inferred FX.** Currencies are grouped independently. USD is never compared to EUR using an invented or stale exchange rate.
2. **No invented probability.** When `probability_bps` is supplied, the candidate enters the `EXPECTED_VALUE` queue with exact integer math:

   `floor(commercial_value_minor * probability_bps / 10000)`

   When probability is absent, the candidate stays in the separate `EVIDENCE_STRENGTH` queue and is ranked by explicit buyer-stage evidence, fit, commercial value, then stable IDs.

HOLD rows never receive a rank.

## CLI

From the repository root:

```bash
python -m revenue.revenue_targeting_allocator.cli compile \
  revenue/revenue_targeting_allocator/synthetic_portfolio.json \
  --output-dir /tmp/revenue-priority

python -m revenue.revenue_targeting_allocator.cli verify \
  revenue/revenue_targeting_allocator/synthetic_portfolio.json \
  --output-dir /tmp/revenue-priority
```

`compile` uses create-exclusive publication and refuses to overwrite an existing output directory. JSON rejects duplicate keys and non-finite numbers.

## Validation

```bash
python -m py_compile revenue/revenue_targeting_allocator/*.py
python -m unittest revenue.revenue_targeting_allocator.test_allocator
python -O -m unittest revenue.revenue_targeting_allocator.test_allocator
```

The synthetic fixture intentionally includes a high-value DNR lead to prove that DNR dominates expected value.
