# Merged-work payment claim packet compiler V2

V2 completes the canonical Commons `#15697` collections primitive while preserving source credit for the donor code recovered from the later duplicate `#15698`.

The compiler turns retained evidence for already merged/accepted compensated work into either a fail-closed hold or `READY_FOR_MUSE_PAYMENT_REQUEST`. That state is only an **internal readiness fact**: recipient and route remain unresolved and every external/payment/accounting authority bit stays false.

## Canonical V2 closures

- Candidate evidence is normalized **before** the process-owned UTC clock is sampled.
- Historical replay is integrity/debug evidence only and can never mint current readiness.
- Claimant, counterparty, opportunity and work identity are bound across all evidence.
- Payment state carries an explicit provenance class; `UNPAID + UNKNOWN provenance` holds.
- Compensation generations require one unambiguous active record; explicit supersession is honored and cycles/conflicts hold.
- Missing compensation, missing acceptance, unknown payment state, stale evidence, eligibility failure, cooldown and conflicts remain distinct states.
- PAID evidence dominates a new request.

## Evidence

The packet binds exact repository/PR/merge/deliverable identity; compensation source and terms; acceptance; eligibility if required; prior payment-request/provider/thread/message receipts; payment-status provenance; and freshness/cooldown policy.

Silence is never proof of nonpayment. Generic nearby bounty labels do not authenticate compensation. Cross-work/counterparty/opportunity transplants fail closed.

## Strictness

The retained donor ingress modules reject duplicate JSON keys, floats/non-finite values, unsafe integer aliases, lone surrogates, unknown fields and unsafe file input. Output is create-exclusive. The semantic verifier recompiles from the exact input and compares canonical bytes, so `false -> 0` tampering fails even though ordinary Python equality aliases them.

## Authority ceiling

The emitted report hard-codes false for send/single-writer/provider authority, invoice creation, legal demand, payment authorization/proof, funds movement, cash receipt, receivable assertion, revenue recognition and accounting conclusion. The package performs no network I/O.

## API

```python
from revenue.merged_work_payment_claim import compile_current, compile_replay, verify_artifacts

report, markdown, receipt = compile_current(document)
replay_report, replay_markdown, replay_receipt = compile_replay(document, "2026-09-18T07:00:00Z")
assert verify_artifacts(document, report, markdown, receipt)
```

Callers remain responsible for loading/storing evidence safely and for any separately authorized outbound workflow.

## Proof

```bash
python -m py_compile revenue/merged_work_payment_claim/*.py merged_work_payment_claim_v2_test_support.py test_merged_work_payment_claim_v2_*.py
python -m unittest -v test_merged_work_payment_claim_v2_state.py test_merged_work_payment_claim_v2_binding.py test_merged_work_payment_claim_v2_integrity.py test_merged_work_payment_claim_v2_io.py
python -O -m unittest -v test_merged_work_payment_claim_v2_state.py test_merged_work_payment_claim_v2_binding.py test_merged_work_payment_claim_v2_integrity.py test_merged_work_payment_claim_v2_io.py
```
