# Procurement Win/Loss Evidence Loop

This package turns **redacted procurement outcome evidence** into deterministic internal learning packets. It exists to stop a common revenue failure mode: converting a buyer's bounded outcome notice into invented explanations, scores, winner identities, or authority.

## Contract

`engine.py` accepts one opportunity plus zero or more source-bound evidence records. Each source record carries the redacted text itself and its SHA-256. Any promoted status quote, winner, reason, or score must be an exact substring of that redacted text. Status promotion is deliberately narrow:

- `LOST` requires explicit non-selection / another-vendor language.
- `WON` requires explicit selection-for-award / awarded-to-you language.
- `NO_DECISION` requires explicit cancellation / withdrawal / no-award language.
- otherwise the outcome remains `UNKNOWN`.

Winner, reason, and score are independently `known=false` unless each is present as an exact source quote. A `LOST` packet therefore does **not** imply why the loss happened.

Evidence from the wrong opportunity, before proposal submission, after the packet `as_of`, with a mismatched source digest, contradictory terminal statuses, duplicate/reminted source evidence, duplicate semantic claims, or private contact/locator material fails closed.

`internal_hypotheses` are allowed only as planning prompts. They are emitted with the immutable classification `INTERNAL_HYPOTHESIS_NOT_BUYER_FACT` and never promote `outcome.reason`.

## Privacy boundary

Public artifacts must contain only redacted source text. The compiler rejects email addresses, ordinary phone-number forms, and HTTP/WWW locators in evidence and hypothesis text. Do not paste private buyer correspondence into this repository.

## Authority

Compiled packets and portfolio views are `INTERNAL_REVENUE_PLANNING_ONLY`. They never authorize buyer contact or establish award, contract, receivable, payment, or revenue.

## CLI

```bash
python -m revenue.procurement_outcome_learning.engine compile --input outcome-input.json --output outcome-packet.json
python -m revenue.procurement_outcome_learning.engine verify --input outcome-input.json --packet outcome-packet.json
python -m revenue.procurement_outcome_learning.engine portfolio --output portfolio.json packet-a.json packet-b.json
```

The retained root bridge executes the hostile suite under both normal Python and `python -O`.
