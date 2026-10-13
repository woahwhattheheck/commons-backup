# Purchasing paperwork operator

A dependency-free, review-first operator for small businesses reconciling normalized supplier invoices against purchase orders. It deterministically matches vendor aliases and exact PO lines, compares currency, SKU, quantity, and unit price with decimal arithmetic, exports only clean rows for a customer accounting workflow, and turns every discrepancy into an unsent actionable draft.

Original CSVs remain linked by path, SHA-256, and source line in the reconciliation. Unknown or ambiguous vendors are held for review. The operator does not perform OCR, send messages, post to accounting software, approve discrepancies, purchase anything, or move money.

## Run

```bash
python3 purchasing_operator.py \
  --vendors examples/vendors.csv \
  --purchase-orders examples/purchase_orders.csv \
  --invoices examples/invoices.csv \
  --out-dir out
```

Outputs:

- `reconciliation.json`: every invoice line, match state, exact issues, and source references.
- `accounting_import.csv`: clean lines marked `REVIEW_READY_NOT_POSTED` for downstream customer review/import.
- `exception_drafts.json`: discrepancy follow-up drafts marked `DRAFT_NOT_SENT` with recommended next action.

Inputs are normalized CSV rather than claimed OCR output. Required columns are visible in `examples/`. Vendor aliases use `|` separators. `po_number + po_line` and `invoice_number + line_number` must each be unique.

## Verify

```bash
python3 -m unittest -v test_purchasing_operator.py
python3 -m py_compile purchasing_operator.py test_purchasing_operator.py
```

Offer reference: Hive original-build demand `bm-hive-20260908-040`, advertised at $299/month. This repository artifact is a runnable delivery checkpoint; it does not claim a subscription sale, customer acceptance, or payment.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
