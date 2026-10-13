# Commercial Lifecycle Ledger

`commercial_lifecycle_ledger` is a deterministic, side-effect-free evidence reconciler for the commercial path that sits **after opportunity selection** and spans offer, acceptance, funding, delivery, settlement, and finance-recognition evidence.

The repository already has strong primitives for opportunity selection and commercial-offer authority. This package does not replace either. It consumes immutable deal/evidence commitments and answers a narrower question:

> Given the exact evidence we have, what lifecycle facts are currently supported, and do the money/reversal records reconcile without skipping authority boundaries?

It never sends outreach, signs or accepts a contract, starts fulfillment, moves/refunds money, or recognizes revenue by itself.

## Contract

Each ledger binds one immutable commercial subject:

- `opportunity_sha256`
- `offer_sha256`
- `scope_sha256`
- opaque `buyer_ref_sha256`
- one exact three-letter currency
- integer `contract_amount_minor`
- offer expiry

`subject_commitment()` hashes those immutable terms. Every event must carry that digest, preventing an acceptance/payment/finance event from being replayed onto another buyer, offer, scope, amount, or currency.

Events use exact schemas and named evidence-authority classes supplied by the upstream verifier:

| Event | Required evidence authority |
|---|---|
| `OPPORTUNITY_QUALIFIED` | `owner` |
| `OFFER_OWNER_APPROVED` | `owner` |
| `OFFER_SENT` | `transport` |
| `BUYER_ACCEPTED` | `buyer` |
| `FUNDING_VERIFIED` | `funding` |
| `EXECUTION_STARTED` | `owner` |
| `FULFILLMENT_ACCEPTED` | `buyer` |
| `PAYMENT_SETTLED` | `payment` |
| `REVENUE_RECOGNIZED` | `finance` |
| `CANCELLED` | `owner` |
| `REFUND_SETTLED` | `payment` |
| `REVENUE_REVERSED` | `finance` |

This package validates the event contract and bound evidence digests; it is not an identity/signature verifier. The upstream integration remains responsible for authenticating the evidence source before assigning an authority class.

Forward lifecycle stages cannot be skipped or repeated. Offer approval/send/acceptance must occur before the bound offer expiry. Evaluation time is supplied out of band as `trusted_as_of`; payloads cannot choose their own current time.

All timestamps are canonical whole-second UTC strings in exact `YYYY-MM-DDTHH:MM:SSZ` form. Equivalent alternate ISO spellings are rejected because raw timestamp strings participate in subject/event commitments.

## Money and reversals

Money is integer minor units only; booleans, floats, decimal strings, coercion, and cross-currency events are rejected.

- funding evidence must equal the exact contract amount;
- settled cash may arrive after buyer acceptance + funding, including legitimate prepayment before fulfillment;
- installment settlement is supported but total settlement cannot exceed the contract amount;
- finance-recognition evidence requires fulfillment and cannot exceed the then-current net settled cash evidence;
- refunds must reference a specific prior settlement event and cannot exceed its residual;
- recognition reversals must reference a specific refund and cannot exceed either that refund or recognized amount;
- if a refund settles after revenue was already recognized, the ledger preserves both facts and emits `RECOGNITION_REVERSAL_REQUIRED_EVIDENCE_ONLY` with `recognition_reversal_pending_minor` until matching finance evidence arrives.

The receipt exposes gross/net evidence totals. It does **not** convert those totals into authority.

## Idempotency and tamper evidence

Event IDs are idempotency keys. An identical duplicate event is safely collapsed even when a retry appears after newer unique evidence; a conflicting reuse of the same event ID fails closed. Chronology is enforced across the first-seen unique events after exact duplicate collapse.

`evidence_sha256` is also a single-use proof identity across distinct unique events. After exact duplicate retries are collapsed, a second event ID cannot reuse an evidence digest already committed to another lifecycle fact. This prevents one payment receipt, buyer acceptance artifact, finance record, or other proof from being relabeled into multiple ledger facts. If one underlying document legitimately supports more than one semantic event, the upstream verifier must issue separate event-specific evidence records whose digests bind the intended role/subject/amount as applicable.

The output binds:

- normalized-input SHA-256;
- immutable subject SHA-256;
- chained event SHA-256;
- exact trusted evaluation time;
- gross/net cash and reported-recognition evidence;
- pending recognition-reversal amount when applicable;
- unique/input event counts;
- canonical receipt SHA-256.

`verify_receipt()` recomputes the entire ledger and compares exact receipt bytes.

All action-authority fields remain `false`, including outreach/send, contract execution, fulfillment, payment/refund, and revenue recognition.

## Validation

From repository root:

```bash
python -m unittest -v revenue.commercial_lifecycle_ledger.test_lifecycle
python -m unittest -v revenue.commercial_lifecycle_ledger.test_lifecycle_financial_edges
python -m unittest -v revenue.commercial_lifecycle_ledger.test_ingestion_hardening
python -m unittest -v revenue.commercial_lifecycle_ledger.test_evidence_identity
python -O -m unittest -v revenue.commercial_lifecycle_ledger.test_lifecycle
python -O -m unittest -v revenue.commercial_lifecycle_ledger.test_lifecycle_financial_edges
python -O -m unittest -v revenue.commercial_lifecycle_ledger.test_ingestion_hardening
python -O -m unittest -v revenue.commercial_lifecycle_ledger.test_evidence_identity
python -m py_compile \
  revenue/commercial_lifecycle_ledger/lifecycle.py \
  revenue/commercial_lifecycle_ledger/test_lifecycle.py \
  revenue/commercial_lifecycle_ledger/test_lifecycle_financial_edges.py \
  revenue/commercial_lifecycle_ledger/test_ingestion_hardening.py \
  revenue/commercial_lifecycle_ledger/test_evidence_identity.py
```

The hostile suites cover lifecycle skips/repeats, cross-deal replay, wrong authority, future/out-of-order unique events, delayed idempotent retries, canonical timestamp aliases, offer expiry, exact funding binding, legitimate prepayment, money coercion, overpayment, premature recognition, refund-before-finance-reversal handling, refund/reversal reference integrity, duplicate IDs, cross-event evidence-digest replay, schema drift, duplicate JSON keys, non-finite JSON, receipt tampering, and trusted-time replay.
