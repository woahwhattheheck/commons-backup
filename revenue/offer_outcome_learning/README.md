# Offer Outcome Learning

`offer_outcome_learning` is an **internal, evidence-bound measurement control** for post-outreach commercial learning. It answers a narrow question: across already-sent campaigns, what observational evidence exists that a particular offer / proof / price-band cohort progressed through reply, qualification, accepted pilot, and independently confirmed payment?

It is deliberately downstream of Commons targeting, relationship/DNR, commercial-decision, and single-writer send controls. It **cannot send** email/DMs, mint an outreach lease, contact a buyer, accept a deal, change pricing, execute/confirm a payment, or recognize revenue.

## Truth model

A campaign binds one canonical organization scope, offer, proof variant, price-band label, proposed integer minor-unit amount, and immutable source evidence. Event rows bind opaque IDs and source SHA-256 digests. Exact event replay collapses; changed event-ID reuse, digest aliasing, chronology regressions, stage skips, cross-campaign transplant, future evidence, and unsafe numeric values fail closed.

`PAYMENT_REPORTED` is **not cash**. Only `PAYMENT_CONFIRMED` contributes to confirmed-payment metrics, and that stage requires separate settlement evidence (`settlement_ref` + SHA-256). A settlement reference is generation-bound: reusing the same settlement reference with a different digest fails closed. A reported amount and confirmed amount must agree when both exist.

The engine exposes denominators and uses a Wilson 95% lower bound on observed confirmed-payment rate. It also applies concentration controls: unique paid organizations, dominant paid-organization share, and a leave-one-organization-out confirmed-count floor. Small cohorts return `INSUFFICIENT_EVIDENCE`; one-organization success returns `OBSERVED_SIGNAL_CONCENTRATED`. No output is a causal claim that an offer or price caused conversion.

## Schemas and states

Input schema: `commons.offer-outcome-learning/input-v1`.

Positive event order is `SENT -> HUMAN_REPLY -> QUALIFIED -> PILOT_ACCEPTED -> [PAYMENT_REPORTED] -> PAYMENT_CONFIRMED`. `LOST` and `DNR` are terminal and forbid later evidence. `PAYMENT_REPORTED` is optional; `PAYMENT_CONFIRMED` requires an accepted pilot and settlement evidence.

Cohort evidence states:

- `INSUFFICIENT_EVIDENCE`
- `OBSERVED_NO_CONFIRMED_PAYMENT_SIGNAL`
- `OBSERVED_SIGNAL_CONCENTRATED`
- `OBSERVED_SIGNAL_WEAK`
- `OWNER_REVIEW_OBSERVED_SIGNAL`

Every strategy-queue result is owner review or a request for more evidence. `external_send_authorized=false` is invariant.

## CLI

From the repository root:

```bash
python -m revenue.offer_outcome_learning.cli build \
  --input revenue/offer_outcome_learning/example.json \
  --json-out /tmp/offer-outcome.json \
  --markdown-out /tmp/offer-outcome.md \
  --historical-at 2026-09-13T23:40:00Z

python -m revenue.offer_outcome_learning.cli verify \
  --input revenue/offer_outcome_learning/example.json \
  --package /tmp/offer-outcome.json
```

Production `build` without `--historical-at` samples process UTC internally. Current packages have a 15-minute verifier freshness ceiling and CURRENT verification always samples process UTC internally. The CLI exposes no verifier-clock override. The Python verifier retains its legacy `now` keyword only as a fail-closed compatibility tripwire: supplying it to CURRENT verification is rejected rather than used as authority. Historical compilation is explicit and is intended for reproducible analysis / tests, not live send authorization.

The CLI opens input with `O_NOFOLLOW` where available, requires an ordinary file, bounds input bytes, and creates outputs exclusively (`O_EXCL`) so it will not silently overwrite an existing artifact.

## Test

```bash
python -m unittest revenue.offer_outcome_learning.test_engine revenue.offer_outcome_learning.test_authority -v
python -O -m unittest revenue.offer_outcome_learning.test_engine revenue.offer_outcome_learning.test_authority -v
python -m py_compile revenue/offer_outcome_learning/*.py
```

## Authority ceiling

This package is measurement and owner strategy support only. It does not infer buyer intent from opens/clicks, does not scrape private contact data, does not send anything, and does not turn a claimed/advertised/reported amount into confirmed payment. A cohort ranking is observational evidence strength, not autonomous targeting or pricing authority.
