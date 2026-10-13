# TenderProof paid RFP Evidence Sprint — delivery admission carrier

Internal commercialization carrier for the merged TenderProof Professional Agent. It is **not a public storefront** and should not be sent as a GitHub link to prospects.

The purpose is simple: a cold lead, positive reply, or accepted scope must never be mistaken for funded buyer work. `intake_gate.py` admits delivery only after all commercial and evidence-input gates are explicit.

## State progression

`HOLD_NO_BUYER_YES` → `HOLD_SCOPE_NOT_ACCEPTED` → `HOLD_UNFUNDED` → `HOLD_INPUTS` → `READY_FOR_DELIVERY`

The gate checks a fixed `$2,500.00` pilot, payment receipt reference, buyer authorization for inputs, exact solicitation SHA-256, and at least one buyer-supplied evidence source. It emits a deterministic receipt. Its authority section always remains false for proposal submission, legal/certification assertion, outbound buyer communication, and revenue recognition.

## Run

```bash
PYTHONPATH=. python -B -m unittest discover -s tests -v
PYTHONPATH=. python -O -B -m unittest discover -s tests -v
python -m py_compile intake_gate.py cli.py
PYTHONPATH=. python cli.py sample/synthetic_ready_intake.json
PYTHONPATH=. python cli.py sample/synthetic_unfunded_intake.json || test $? -eq 2
```

Only synthetic data is checked in. Real buyer contacts, solicitations, evidence, invoices, payment receipts, and confidential materials stay in their authorized systems rather than this public repository.
