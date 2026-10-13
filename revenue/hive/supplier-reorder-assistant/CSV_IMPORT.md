# Supplier reorder CSV intake

The command-line planner and receipt workflow share `_read_csv`. Stock, rules,
catalog and receipt inputs now use the same explicit CSV validation before any
output is written.

Required columns and the existing domain rules are unchanged. A CSV must have
unique, nonblank column names and the same number of fields in every nonblank
record. An optional value can be empty, but its field must still be present. For
example, leave the final comma when a catalog row has no alternative SKU:

```csv
supplier_id,supplier_sku,sku,description,unit_cost,available_qty,lead_days,alternative_for_sku
SUP-1,F-101,FILTER-A,Filter cartridge,4.25,25,2,
```

Extra fields, omitted fields, duplicate headers, blank headers, malformed quoted
records and undecodable UTF-8 produce `ReorderError`. CLI callers see the existing
argument-error exit status rather than a Python traceback. Existing output files
are not overwritten when parsing an input fails.

UTF-8 BOMs, CRLF, quoted commas, escaped quotes, embedded newlines, explicit empty
values, blank physical lines, header-only datasets and additional **named**
metadata columns remain supported. Existing value trimming is preserved.
`_line` identifies each record's **first physical source line**, including when
blank lines precede it or quoted fields span multiple lines. Width and quoted-record
errors report that same source position; duplicate SKU/rule/catalog diagnostics
inherit it. Header and UTF-8 decoding errors remain file-level messages.
No supplier-selection, quantity, pricing, plan or receipt calculation has changed.

## Focused regressions

Run in the supplied cloud execution environment, from this directory:

```sh
python -B -m unittest -v test_reorder_csv_robustness test_reorder_csv_locations
```

The suite exercises real files and actual CLI subprocesses, including a fictitious
stock/rules/catalog import, an unsent purchase-order plan, and a stock receipt.
No customer data, supplier calls, purchase, payment or external provider request
is used.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
