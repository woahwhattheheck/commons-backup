# UIOWA-009 milestone cash-flow and working-capital model

Isolated path: `revenue/uiowa_rfq_18649_cashflow/`

Stdlib exact-decimal weekly cash-flow workbook for the proposed TJLabs
$24,000 subcontract workshare. Relative weeks only. Planning /
**PROPOSED / NOT ACCEPTED**.

Pinned source: `revenue/uiowa_rfq_18649_workshare/COMMERCIAL.md` blob
`b6e9ca58984c15d96b497f3bb51000992fdb9b5f`.

## What it computes

- Base receipts **$9,600 / $9,600 / $4,800 = $24,000**
- Optional **$4,000** readout, excluded from base unless separately enabled
- Kickoff = written authorization, draft = delivery, final = written acceptance — distinct from invoice timing and cash receipt
- Scenarios: `prompt`, `delayed_collection`, `extended_final_review`
- Weekly closing cash and conservative pre-receipt trough
- Peak funding before opening liquidity, incremental need after opening liquidity
- Cash cost vs noncash imputed effort
- Isolated prime-to-University invoice planning register (never funds this model)
- Out-of-horizon movements refused (not silently truncated)
- Independent formula sheet with engine parity

```bash
python3 cli.py --workbook fixtures/workbook.json --out /tmp/uiowa009
python3 -m unittest test_cashflow.py
python3 -O -m unittest test_cashflow.py
```

Not an invoice, payment request, bank record, schedule, or prime bid fee.

Closes woahwhattheheck/commons#16092.
