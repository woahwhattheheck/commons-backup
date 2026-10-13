# UIOWA-132 commercial-facts checker

Cross-document checker for University of Iowa RFQ 18649. It reconciles
the proposal, fee schedule, staffing model, scope exhibit, and option
sheet against pinned commercial facts.

Pinned facts:

- Deadline: 2026-09-22 15:00 America/Chicago
- Currency: USD
- Base: $24,000
- Option (readout): $4,000, not included in base
- Milestone split: 40 / 40 / 20 = $9,600 / $9,600 / $4,800
- Kickoff assumption: after award, no travel
- Travel: excluded from base
- Principal = prime, specialist = subcontract
- Final payment trigger: acceptance, not delivery

This package produces a facts table, executable findings, and repaired
draft text. Repair preserves legitimate prime vs subcontract labels.

## Authority ceiling

Checker output is internal draft reconciliation only. It is not buyer
contact, a submitted bid, an invoice, a payment, revenue, a signature,
or a schedule.

## Run

```bash
python3 cli.py fixtures/consistent --json-out /tmp/facts.json --md-out /tmp/facts.md
python3 cli.py fixtures/stale_september_22 --repair-out /tmp/repaired
python3 -m unittest test_checker.py
python3 -O -m unittest test_checker.py
```

Exit 0 = bundle consistent. Exit 1 = findings. Exit 2 = load/parse error.

## Fixtures

| bundle | expected finding |
|---|---|
| `fixtures/consistent` | none |
| `fixtures/stale_september_22` | `STALE_SEPTEMBER_22` |
| `fixtures/amount_mismatch` | `AMOUNT_MISMATCH` |
| `fixtures/delivery_vs_acceptance` | `DELIVERY_VS_ACCEPTANCE_TRIGGER` |

Closes woahwhattheheck/commons#16215.
