# Live Procurement Partner Fit Gate

`revenue.live_procurement_partner_fit` is a deliberately **authority-negative** pre-Muse qualification gate for paid procurement teaming.

It encodes an observed funnel lesson: a technically plausible partner is not a safe or useful outreach candidate unless the procurement is still live, the paid workshare is already shipped, the role is unambiguous, the partner has enough evidenced delivery runway, the contact route is current and first-party, and current collision/DNR evidence is clear.

The only positive state is `READY_FOR_MUSE`. That means **ready to request a separate Muse single-writer arbitration**; it never means selected, cleared, or authorized to send.

## Required role language

The retained workshare role statement must explicitly include: `paid`, `fixed-fee` (or `fixed fee`), `subcontract` or `workshare`, `not staffing`, `not recruiting`, and `not platform replacement`. This is intentionally literal; the compiler does not infer equivalent marketing language.

## Freshness policy

| Evidence | Maximum age |
| --- | ---: |
| opportunity source observation | 7 days |
| partner-fit first-party observation | 30 days |
| delivery-runway evidence | 30 days |
| current first-party route observation | 30 days |
| relationship / DNR / collision census | 4 hours |

Future-dated evidence fails closed. The opportunity deadline and delivery start must still be future events. `now + minimum_lead_days` must fit on or before the delivery start.

A route clears only with provenance `FIRST_PARTY_CURRENT` and state `CLEAR`. Historical address guesses, dead routes, provider retry/temporary failures, unknown provenance, or any other state produce `HOLD`.

Collision clears only with state `CLEAR`. `DNR`, `SENT`, `AWAITING_REPLY`, `UNKNOWN`, and every other non-clear state produce `HOLD`.

## Commercial truth

The workshare must be retained as landed source and carry commercial state exactly `PROPOSED_NOT_ACCEPTED`. Deliverables and acceptance criteria are required. The gate makes no claim that the partner wants the work, is pursuing the procurement, has budget, has accepted a subcontract, or can satisfy buyer qualifications.

## Authority ceiling

Every receipt hard-codes all of these to `false`:

- `external_send_authorized`
- `muse_selected`
- `provider_mutation_authorized`
- `payment_authorized`
- `revenue_claim_authorized`

The compiler performs no network I/O, email/DM/form/call, Muse request, provider mutation, portal/bid action, payment operation, or buyer/partner mutation.

## CLI

```bash
python -m revenue.live_procurement_partner_fit compile \
  --input candidate.json \
  --now 2026-09-16T22:30:00Z > receipt.json

python -m revenue.live_procurement_partner_fit verify \
  --input candidate.json \
  --receipt receipt.json \
  --now 2026-09-16T22:30:00Z
```

The compile time is part of the deterministic receipt. A later pre-send process must re-census current evidence and run separate Muse arbitration rather than reusing this prequalification as send authority.

## Origin

Operation: `LIVE-PROCUREMENT-PARTNER-FIT-GATE-ZKILN-20260916`

Controlling issue: Commons #15054.

The gate was motivated by provider-grounded funnel evidence: role ambiguity, delivery-calendar mismatch, and stale/dead routes were observed pre-funnel losses, while live-procurement paid-workshare messages produced the deepest human routing/scope events. These observations motivate a falsifiable qualification control; they do not imply a general conversion-rate estimate.
