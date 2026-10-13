# Prize / Research / Competition Claim Readiness Ledger

Operation: `PRIZE-CLAIM-READINESS-LEDGER-20260916-ZMF`  
Recovery/source/finalization: **Z-HelixLedger / GPT-5.6 Sol**

This carrier prevents a recurring revenue-accounting error: **work is not a submission; a submission is not an award; an advertised prize is not payment.** It compiles a bounded evidence packet into one deterministic state and never authorizes registration, external contact, submission, payout requests, or payment mutation.

## State ladder

Planning / build states:

- `HOLD_SOURCE_INCOMPLETE` — controlling first-party terms are incomplete.
- `HOLD_SOURCE_STALE` / `HOLD_SOURCE_TIME` — controlling capture is too old or future-dated relative to trusted execution time.
- `HOLD_OWNERSHIP_CONFLICT` — duplicate/ownership state is unresolved.
- `HOLD_REVIEW_RED` — independent review is RED.
- `RESEARCH_IN_PROGRESS` — useful work may exist, but no independently reviewed qualifying result exists.
- `QUALIFYING_RESULT_REVIEW_REQUIRED` — the source claims a qualifying result but independent review has not passed.
- `OWNER_SUBMISSION_REQUIRED` — a reviewed qualifying result exists, but required registration and/or submission evidence is absent.
- `QUALIFYING_RESULT_READY` — a reviewed qualifying result exists and the opportunity requires no separate submission action.
- `EXPIRED_NOT_SUBMITTED` — deadline passed without a retained submission receipt.

Provider-evidence states:

- `SUBMITTED_AWAITING_DECISION` — distinct submission evidence + timestamp are retained and chronologically valid.
- `AWARDED_UNPAID` — provider award evidence is retained; payment evidence is absent.
- `PAID` — distinct award and payment evidence are both retained, currency-consistent, and payment does not exceed the award.

Provider evidence outranks later planning/currentness gates for historical fact states. A stale source cannot erase a real retained settlement receipt, but it can block a new submission-readiness claim.

## Evidence contract

Production inputs require `source_type=FIRST_PARTY`. `source_sha256` binds the captured source bytes and `capture_receipt_sha256` is a distinct external capture root; this tool does **not** fetch the URL or prove provider authenticity itself. That responsibility stays with the upstream capture/ingest layer.

All evidence roots across source capture, work, registration, submission, award, and payment must be distinct. Submission requires its timestamp in the same input generation. An award cannot precede a required submission. Payment cannot exist without award evidence, cannot change currency, and cannot exceed the awarded amount.

`verify_readiness()` does two checks:

1. validate the packet's content-addressed receipt; and
2. recompile the complete packet from the retained input at the trusted current time.

Therefore changing `state`, authority booleans, source facts, evidence roots, or money fields and merely recomputing `receipt_sha256` does **not** create authority.

## Current-truth fixtures

`fixtures/` contains **synthetic, fixture-derived** state examples based on current swarm situations (Ridgway rigorous-partial research, Learn2Design build-without-submission, CUHK-X expired/unsubmitted, and a settled paid unit). They intentionally use `source_type=FIXTURE_DERIVE``+ `synthetic_fixture=true`; they are regression inputs, **not** first-party prize/award/payment evidence and must never be promoted into production receipts.

## Commands

```bash
python -m py_compile readiness.py test_readiness.py
python -m unittest -v test_readiness.py
python -O -m unittest -v test_readiness.py
```

Production CLI compilation uses the process UTC clock; there is no caller-provided `--now` escape hatch:

```bash
python readiness.py compile input.json packet.json
python readiness.py verify input.json packet.json
```

Output creation is exclusive (`xb`) so the CLI refuses to overwrite an existing packet.

## Authority ceiling

Every packet hard-codes these false:

- `outbound_contact_authorized`
- `registration_mutation_authorized`
- `submission_mutation_authorized`
- `payout_request_authorized`

Only retained evidence can make `can_claim_submitted`, `can_claim_awarded`, or `can_claim_paid` true.
