# Map a retailer export without changing the original

`import_mapper.py` is an onboarding adapter for this product's existing stock,
rule and supplier-catalog loaders. It does not replace the planner, browser,
receipt history, workspace CLI or inventory database. Python 3.10+ and the
existing `reorder_assistant.py` are sufficient; no extra packages are required.

A retailer's export need not already have the canonical column names. Inspect
its exact headers, approve a reusable JSON profile, preview the result, then
create a new canonical CSV for the existing browser or command-line workflow.
No SKU matching, thresholds, stock quantities, currency or unit conversions are
inferred. All target fields must have an explicitly named source column or an
explicit string constant. Missing data is an error, not an assumed zero.

## Runnable fictional onboarding example

Run from this product directory. Use a new private output location; the mapper
never replaces an existing file. The sample uses no customer data.

```sh
python3 import_mapper.py inspect \
  --source mapping_examples/stock-export.csv --delimiter ';'

# Preview only: validates every row but creates no persistent output.
python3 import_mapper.py map \
  --source mapping_examples/stock-export.csv \
  --profile mapping_examples/stock-profile.json

# Create an output only after reviewing the mapping and sample values.
python3 import_mapper.py map \
  --source mapping_examples/stock-export.csv \
  --profile mapping_examples/stock-profile.json \
  --out /tmp/retailer-stock-001.csv

python3 reorder_assistant.py plan \
  --stock /tmp/retailer-stock-001.csv \
  --rules examples/rules.csv --catalog examples/catalog.csv \
  --as-of 2026-09-08 --out /tmp/retailer-plan-001.json
```

This maps the fictional supplier assistant stock exactly: FILTER-A has 3 units
on hand, 0 incoming and 2 allocated. The plan requests 9 filter units, totaling
38.25, and leaves a 3-unit belt shortage with a separate review-only alternative.
It sends no orders. Existing `examples/receipts.csv` can then be applied through
the normal receive command; keep the updated stock and its complete receipt log
together as described in README.md.

The mapped stock CSV can instead be uploaded to the existing browser desk along
with `examples/rules.csv` and `examples/catalog.csv`. This adapter itself does not
open or mutate the browser's saved SQLite workspace.

## Mapping profiles

The provided profile explicitly maps five source headers and sets the sample's
`unit` to `"each"`. That is an approved example value, not a default for a real
retailer. Remove or replace it with a source mapping when units differ.

A rule-export profile might be:

```json
{
  "schema": "commons-reorder-mapping-v1",
  "kind": "rules",
  "columns": {
    "sku": "Item code",
    "reorder_at": "Reorder threshold",
    "target_stock": "Target quantity",
    "preferred_supplier": "Preferred vendor"
  }
}
```

A supplier-catalog profile might be:

```json
{
  "schema": "commons-reorder-mapping-v1",
  "kind": "catalog",
  "columns": {
    "supplier_id": "Vendor code",
    "supplier_sku": "Vendor item",
    "sku": "Our item",
    "description": "Item description",
    "unit_cost": "Net price",
    "available_qty": "Available units",
    "lead_days": "Lead days",
    "alternative_for_sku": "Alternative for"
  }
}
```

Each `columns` entry is **destination field: exact source header**. Headers are
case-sensitive and are not fuzzy-matched or trimmed. `constants` supplies fields
not present in `columns`; all constants, including numbers, must be JSON strings.
An explicit empty string is allowed when the corresponding canonical loader
allows it. A field cannot appear in both objects. Unknown fields, duplicate JSON
keys, non-string constants and missing target fields are rejected.

`delimiter` defaults to comma; explicitly choose `";"`, `"\t"` or `"|"` for those
exports. No delimiter, decimal-comma, currency-symbol or thousands-separator
conversion is guessed. The required destination fields are exactly:

- Stock: `sku,name,on_hand,on_order,allocated,unit`
- Rules: `sku,reorder_at,target_stock,preferred_supplier`
- Catalog: `supplier_id,supplier_sku,sku,description,unit_cost,available_qty,lead_days,alternative_for_sku`

Keep source profiles private when their headers or constants reveal business
information. Reuse an approved profile with later exports, then review each run's
preview. A renamed or missing source header fails rather than silently remapping.

## Validation, provenance and output behavior

Every row is validated with the existing `load_stock`, `load_rules` or
`load_catalog`, including rows beyond the five-row preview. Rule thresholds,
integer quantities, decimal costs and duplicate item checks therefore use the
same implementation as the planner. Cross-file rule/SKU relationships are still
checked when the actual planner combines the three files.

UTF-8 and UTF-8 BOM exports, Unicode, quoted separators, doubled quotes, multiline
values, CRLF and blank physical records are supported. Duplicate/blank headers,
ragged records, broken quoting and invalid UTF-8 are rejected. Field values are
trimmed, matching the existing canonical loaders; leading-zero IDs and numeric
text otherwise remain text. Output is UTF-8 comma-separated CSV with LF record
endings. Mapping does not preserve original CSV formatting; the source remains
unchanged and its exact-byte hash is reported separately.

The JSON response includes explicit field sources/constants, ignored source
columns, five preview rows, total row count, all source start/end line locations,
source/output SHA-256 values, a normalized profile hash, the canonical loader
used, and whether an output was actually created. `output_record` is a data-record
number, not a physical CSV line number. Hashes support comparison, not source
identity authentication. Preview reports can contain retailer data; retain them
privately. Inspection validates CSV structure but does not approve its business
values; mapping validates the selected canonical kind.

New output bytes are fully staged and validated before an atomic create-only
hard link makes them visible. Existing files, directories, symlinks (including
dangling links), hardlinks and another writer's completed output are not replaced.
The destination parent must already exist on a filesystem supporting hard links;
unsupported filesystems fail without a partial destination. Temporary staging
files are cleaned up. This is not a multi-file transaction, scheduled import,
cloud upload or guarantee of directory durability after power loss.

Limits are 2 MiB per source, 64 KiB per profile, 20,000 data records and 8 MiB per
mapped CSV. Only CSV-to-CSV mapping is supported: no Excel, OCR, provider access,
receipt mapping, joins, database updates or spreadsheet formula rewriting.
Treat business text as data when opening it in spreadsheet software. No order,
purchase, supplier message, customer contact or account change is performed.

## Test

```sh
PYTHONWARNINGS=error::ResourceWarning python3 -B -m unittest -v test_import_mapper
```

The suite uses real CSVs, the complete canonical engine, actual CLI processes,
source/output aliases, concurrent output writers and the plan/receipt/replay
workflow. Tests use synthetic records only. Passing these tests is not a customer
acceptance, hosted deployment, sale or repository-wide CI result.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
