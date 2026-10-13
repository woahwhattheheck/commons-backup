# Outreach Cohort Attribution

Offline, owner-review-only revenue control for turning outbound activity into **evidence-bound cohort learning** instead of send-count theater.

It keeps the commercial boundaries separate:

`MUSE_SELECTED → SENT → HUMAN_REPLY → QUALIFIED / PROPOSED → ACCEPTED → INVOICED → PAID`

Transport failures (`BOUNCE`) are not buyer rejection. Recent sends remain censored/pending until the configured observation window matures. `DNR` and unresolved bounce states hold the exact target × route × purpose lane; only an explicit `HUMAN_REPLY` or `ROUTE_RECOVERED` evidence event can clear that hold. Every send requires a fresh preceding Muse selection, and a repeat send additionally requires a human reply after the previous send.

## Money truth

`PROPOSED`, `ACCEPTED`, `INVOICED`, and `PAID` each carry their own amount/evidence. Amounts never auto-promote across stages. The compiler permits one native currency/decimal convention per campaign and performs no FX or token-to-USD conversion. Paid totals therefore mean only explicit `PAID` events with evidence; they are **not** booked/recognized revenue authority.

## Cohort decisions

Cohorts are keyed by `offer_id × segment` and report sent, mature, delivered-mature, pending, bounce, human-reply, qualified, proposed, accepted, invoiced, and paid counts plus native-currency amount totals.

The reply rate is `human_reply_targets / delivered_mature_targets`, in basis
points. A mature campaign belongs to the delivered denominator if it has no
bounce history or it has a retained human reply demonstrating delivery. Thus a
reply after a bounce appears in both numerator and denominator, and the rate
cannot exceed 100%. A bounce without a reply stays outside that denominator;
historical bounce counts and route-quality rates remain visible even when a
reply exists. This attribution does not clear a contact hold or authorize a send.

The deterministic owner-review disposition is one of:

- `UNDER_OBSERVED` — insufficient mature evidence;
- `EXPAND_CAUTIOUSLY` — enough mature evidence and reply-rate threshold met without route-quality failure;
- `PAUSE_ROUTE_QUALITY` — bounce rate breaches the configured ceiling;
- `PAUSE_CONVERSION` — enough mature delivered evidence but reply threshold is not met;
- `HOLD_COLLISION_OR_DNR` — every sent target in the cohort is currently route/DNR held.

These are analysis states only. The compiled packet hard-codes all external send, pricing-commitment, acceptance, invoice, payment, revenue-recognition, and automatic-scaling authority to `false`.

## CLI

```bash
python -m revenue.outreach_cohort_attribution.core compile input.json packet.json
python -m revenue.outreach_cohort_attribution.core verify input.json packet.json
```

Input schema: `outreach-cohort-attribution-input/v1`.

The parser rejects floats/non-finite values, duplicate JSON keys, boolean-as-integer aliases, unknown keys, missing evidence, chronology reversal, impossible predecessor transitions, duplicate target × route × purpose ledgers, unsupported money-state promotion, and reminted verification packets.
