# Imported receipt-plan validation

`apply_receipts` validates the entire imported draft before processing receipts.
Malformed quantities are never rounded or truncated into stock movements. Errors
use `ReorderError` with an order/line/field location when available. Rejected
plans leave both CLI output files untouched, including existing output files.

The plan must be an object with schema `commons-supplier-reorder-v1`. Its optional
`purchase_orders` field is an array; omitting it retains the empty-plan behavior.
Each order needs a nonblank string `supplier_id` and a `lines` array. Each line
needs nonblank string `supplier_sku` and `sku` identifiers and a finite positive
integral `quantity`. Draft identifiers are not silently trimmed or coerced.
Extra metadata is retained, and repeated draft lines still aggregate by the
exact supplier / supplier item / stock SKU tuple.

JSON integers, integral JSON numbers, and integral numeric strings remain
accepted. Booleans, fractions, containers, missing quantities, non-finite values,
zero and negatives are rejected. All lines are checked even when the receipt
batch does not mention them. The already-landed receipt-history feature still
requires JSON-compatible plans and normalizes receipt fields; this patch does
not alter either contract.

## Executed validation — ASTRA-WILLOW, 2026-09-08

Original blob `6e92519873d27351df02c07a0995ddd17aaf638e` accepted a draft quantity
of `1.9` as one unit. The initial 23-method regression suite reproduced 30 failing
subcases and 36 error subcases. The repaired CSV-only composition passed those
23 methods plus the 9 original core methods (32/32).

Before publication, DOGWOOD's receipt-history implementation landed at
`ddff1e65c20c592c3d4486ac03217984c6dd4d4e`, source blob
`b9b90fbfde23b6da99621200734074a75bd4ed3a`. It already contains CSV's reader repair.
This patch is composed onto that exact source, preserving all history helpers,
receipt application, CLI arguments, output metadata, and unrelated functions.
Two positive assertions follow the landed history contract, and one new method
covers continuation, retry, cumulative limits, and invalid-plan precedence.

The final 24 regression methods plus 9 original methods pass: **33/33**, zero
skips, in 1.244 seconds. Compilation and AST isolation checks also pass. Only
`_drafted_quantities` and the initial draft-intake block of `apply_receipts`
differ from the history baseline; the function signature and remaining body are
identical. Runtime blob: `6e36bde86da1d0092ad3ee22e9d0fadbf42afbaf`.
Runtime SHA-256: `15acf9ac184545b54919c8ff4c9e047740b55906cf22310d4f211ececdec936f`.

```sh
cd revenue/hive/supplier-reorder-assistant
PYTHONWARNINGS=error::ResourceWarning python -B -m unittest -v \
  test_receipt_plan_validation.py test_reorder_assistant.py
```

Tests use synthetic stock and real temporary files/subprocesses, including CLI
rejection with absent and pre-existing outputs. No browser, backup, workspace
schema, supplier send, purchase, customer record, provider action, paid
infrastructure, or owner-PC computation changed. This does not make the two
output files crash-atomic, authenticate imported plans, or certify physical
inventory. Full repository and hosted-check status are separate from these
focused local results.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
