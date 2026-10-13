# Lawrence Youth AI Training Core

Bounded technical-training evidence package for the City of Lawrence / MassHire Merrimack Valley Workforce Board Youth AI Workforce Training opportunity (`BD-27-1412-LAW26-LAW85-132652`).

This is a **technical subcontract component**, not a prime-bid claim, buyer submission, award, workforce-provider credential, or authority to operate participant services. A qualified local/workforce prime remains responsible for recruitment, eligibility, case management, work-based-learning placement, employer commitments, stipends/incentives, job placement, follow-up, proposal compliance, contracting, and buyer communications.

## What this package does

`training_evidence.py` compiles approved training evidence into a deterministic receipt for one opaque participant token. The contract binds:

- curriculum modules, topics, required labs, assessments, and minimum integer scores;
- external credential-track evidence such as an agreed AI/cloud credential path;
- employer-defined project acceptance criteria and artifact hashes;
- exact program identity/version and trusted evaluation time;
- strict event identity, module binding, and future-event rejection;
- deterministic plan/evidence/receipt SHA-256 commitments;
- explicit authority flags that remain false for participant eligibility, case management, stipends/incentives, credential issuance, employment placement, buyer acceptance, contracts, and revenue.

The strongest output is `TECHNICAL_TRAINING_EVIDENCE_READY`. That state means only that the supplied technical evidence satisfies this package's declared technical contract. It cannot promote evidence into eligibility, credential issuance, employment, payment, buyer acceptance, or recognized revenue.

## Fail-closed boundaries

The compiler rejects unknown schema fields, duplicate JSON keys, NaN/floats, duplicate event IDs, cross-module assessment/lab evidence, future events, caller-replayed evaluation clocks, self-reported credential claims, employer-project check drift, malformed hashes, PII-shaped participant identifiers, and receipt tampering.

Participant identifiers are deliberately opaque tokens; do not place names, email addresses, phone numbers, SSNs, case notes, or other participant PII in this package.

## Validation

From this directory:

```bash
python -m unittest -v test_training_evidence.py
python -O -m unittest -v test_training_evidence.py
```

The checked-in hostile suite contains 29 tests and is expected to pass in both normal and optimized Python so correctness does not depend on `assert` statements.

## RFP workstream fit

This package supports the technical side of an AI-training model: fundamentals and responsible use, applied generative AI/prompting, data/cyber/workplace AI, hands-on labs, assessment thresholds, credential preparation, and employer-defined project evidence. It intentionally leaves the workforce-program obligations that require local delivery infrastructure and prime authority outside this code boundary.

See `TEAMING_SCOPE.md` for the recommended responsibility split.