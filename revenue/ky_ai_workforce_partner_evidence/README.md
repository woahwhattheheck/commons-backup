# Kentucky AI Workforce partner evidence gate

This package operationalizes the unresolved partner-qualification facts for Commons
issue `#13536` (`R-C08-KY-AI-WORKFORCE-2026`). It is a deterministic, network-free
evidence reducer: supplied evidence receipts become explicit `PASS`/`HOLD` gates and
one readiness decision, without turning a public web claim, a sent inquiry, or an
unverified statement into a teaming commitment.

The gate is intentionally separate from `revenue/ky_ai_workforce_delivery/**`.
That package proves a delivery-plan evidence contract. This one answers whether a
specific proposed teaming anchor has supplied enough attributable evidence to move
from `HOLD / partner needed` to `QUALIFIED_TEAMING`.

## What it checks

A passing bundle requires:

- a confirmed partner commitment and disclosed role;
- at least three years of evidenced relevant experience;
- at least three permission-confirmed, attributable references completed within
  five years of `evaluated_on`;
- named, availability-confirmed instructor coverage for manufacturing,
  construction, logistics, healthcare, business operations, and career readiness;
- both `live_remote` and `in_person` coverage for every required scope;
- confirmed evidence for Kentucky in-person dispatch, live remote delivery,
  curriculum rights, accessibility, records/reporting, data security,
  insurance/registration readiness, pricing, and travel assumptions.

Every positive fact is paired with a source receipt containing a source identifier,
SHA-256, capture timestamp, and evidence kind. The reducer validates the receipt
shape but does not claim to independently authenticate external bytes. Reviewers must
inspect the referenced source material before making legal/commercial
representations.

## Decision boundary

`QUALIFIED_TEAMING` means only that the supplied structured evidence clears this
owner-side readiness contract. Any missing/pending/unavailable condition yields
`HOLD_PARTNER_EVIDENCE`.

The report always keeps proposal authorization, submission, buyer acceptance,
contract award, payment, and recognized revenue `false`. This package therefore
cannot manufacture a bid, award, buyer acceptance, or cash state.

## Usage

```sh
python -m revenue.ky_ai_workforce_partner_evidence.cli \
  revenue/ky_ai_workforce_partner_evidence/example_bundle.json \
  --output /tmp/ky-partner-readiness.json
```

Exit codes: `0` qualified, `2` valid bundle but still on hold, `3` malformed or unsafe
input. Duplicate JSON keys, symlinked/non-regular input, input/output aliases, and
non-regular output targets fail closed; file output uses same-directory temporary
publication + `fsync` + atomic replacement.
