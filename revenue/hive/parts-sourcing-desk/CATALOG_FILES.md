# Supplier catalog file intake

Demand `bm-hive-20260908-044`. This is a companion to the canonical
`parts-sourcing-desk`, not another desk, database, fit-review engine, or order system.
The existing desk remains the authority for application field validation, imports,
fit review and handoffs.

## Preview a source file

Python 3.10 or later; standard library only. Run in the existing cloud workspace.

```sh
python catalog_file.py supplier.csv --output supplier-preview.json
python catalog_file.py supplier.json --output supplier-preview-json.json
python -m unittest -v test_catalog_file.py
```

The preview command does not contact suppliers or apply database changes. It reads
one bounded byte snapshot and writes a new preview file (or stdout). Existing output
files are left unchanged. Preserve the original file beside the preview in private
operational storage; the preview carries a hash and record locations, not original
file bytes. Do not commit actual supplier/customer files to the public repository.

CSV accepts UTF-8, including a UTF-8 BOM, a nonblank unique header for each column,
quoted commas, quoted multiline values and CRLF. Headers with surrounding whitespace
are diagnosed rather than silently renamed. Blank physical rows are skipped; rows
with missing/extra fields report physical line locations. A quoted empty cell is
still a cell. The parser supports up to 8 MiB and 5,000 data records per source.

JSON accepts an array of nonempty row objects or an object containing only `rows`.
Duplicate object keys and non-finite values are errors. Decimal JSON numbers become
strings preserving decimal precision; part identifiers should be JSON strings so
leading zeros remain explicit. Supplier arrays, such as aliases, remain arrays.
JSON row locations use JSON pointers; they do not claim physical source line numbers.

## Explicit header mapping

A mapping file is a JSON object from supplier column name to canonical field name:

```json
{"SKU": "part_number", "Model": "model", "List price": "unit_price"}
```

Use the field names expected by the current desk importer. A mapping entry whose
source column is absent, or one which would overwrite another field, is an error.
Unmapped columns remain present. Optional defaults fill only absent or empty-string
cells; they never replace an existing supplier value or infer compatibility.

```sh
python catalog_file.py supplier.csv --mapping columns.json \
  --defaults source-context.json --output mapped-preview.json
```

Defaults are explicitly supplied context, not independently verified observations.
Never default a present-day stock/price observation timestamp unless someone actually
observed that information. A filename or matching part/model number is not fit proof.

## Python integration surface

```python
from catalog_file import read_catalog, parse_bytes, map_fields

parsed = read_catalog("supplier.csv")
# For an already-read upload: parsed = parse_bytes(raw_bytes, "supplier.csv")
rows = map_fields(parsed, mapping={"SKU": "part_number"})
for row in rows:
    fields = row["fields"]
    provenance = row["provenance"]
    # Hand fields to the existing desk's importer, keeping provenance with its
    # source evidence. This module does not own application schema or fit logic.
```

`ParsedCatalog.source` contains `filename` (basename only), `sha256`, `size_bytes`
and `format`. Each record has its 1-based `record` number, `fields` and `location`:
CSV `line_start`/`line_end`, or JSON `json_pointer`. `map_fields` places these source
and location fields together under each row's `provenance`.

The digest covers the exact original bytes, including BOM and line endings. It is
not a hash of normalized JSON and does not verify supplier legitimacy, price, stock,
compatibility or permission to redistribute catalog content. Errors are surfaced
as `CatalogFileError`; no partial application occurs inside this reader.

## Validation

Executed in the provided cloud container: 19 tests passed in 0.010 seconds. Coverage
includes quoted/multiline CSV, exact source hash/line locations, UTF-8 BOM, leading-zero
identifiers, decimal JSON prices, JSON pointers, duplicate header/key handling,
malformed/ragged/empty files, byte/row limits, explicit mapping collisions, default
preservation, preview generation and existing-output preservation. There were no
supplier operations, real catalog imports, customer transactions or purchases.

## Import into the existing desk

The `catalog_intake.py` adapter uses the real `parts_desk.catalog_data` validator
and `Desk.mutate("catalog", "", payload)` transaction. Run with Python 3.11 or later
beside the canonical `parts_desk.py`; it defines no alternate schema or order road.

```sh
# Prepare an import-ready preview, without touching a database.
python catalog_intake.py supplier.csv --mapping columns.json \
  --defaults source-context.json --output import-preview.json

# Apply through the already-existing desk database; result receipt goes to stdout.
python catalog_intake.py supplier.csv --mapping columns.json \
  --defaults source-context.json --apply --db /path/to/existing/desk.sqlite3
```

`--apply` and `--db` are paired. Without them, this command only previews. Start the
canonical desk first to create its database; the adapter does not silently create
one for a misspelled path. `--output` always writes the unapplied preview, before
any optional mutation, and leaves existing files unchanged. The successful apply
receipt is separate stdout JSON. Reusing the same source, filename, mapping and
explicit defaults reuses the same payload and operation ID, including after a
lost response or process restart. The canonical operation ledger returns the
original result on retry; its `changed` value describes that original operation,
not new changes made by the retry. Retrying an old import after a newer one does
not roll the newer catalog back.

Required fields are `id`, `supplier`, `supplier_sku`, `part_number`, `description`,
`source_url`, `checked_on` (YYYY-MM-DD), and `currency`. IDs stay explicit; no ID,
current observation date, stock state, or compatible fit is inferred. Supported
optional fields follow `catalog_data`, including make/model/serial scope, aliases,
price/shipping decimal strings, lead time, stock notes and original source note.
Unknown amounts remain unknown, not zero. Use strings for part numbers and SKUs.

The adapter preserves the original source note and appends a deterministic
`[catalog-file provenance]` JSON object with filename, source digest, size, format,
record location and any extra supplier fields outside the canonical schema. The
original fields also remain in the preview. A note exceeding the canonical length
limit is diagnosed rather than truncated. New source bytes or a renamed source
file change this provenance, so applying them can advance catalog versions and
make existing fit reviews stale even when a price happens to be unchanged.
Original option/order snapshots remain managed by the canonical desk.

The raw reader supports 5,000 rows / 8 MiB; a prepared desk import is bounded by
the existing desk's 2,000-row transaction and 2 MiB encoded HTTP payload, including
metadata expansion. Split larger files explicitly. This companion never silently
applies a partial batch. Source note, field, row or payload errors occur before
an apply call.

### Application integration

```python
from catalog_file import parse_bytes
from catalog_intake import prepare_import

preview = prepare_import(parse_bytes(upload_bytes, filename), mapping, defaults)
payload = preview["payload"]  # exactly {operation_id, items}
# Existing HTTP handler / CLI may use the same existing mutation:
result = desk.mutate("catalog", "", payload)
```

Or send `payload` unchanged to the existing `POST /api/catalog/import` route.
Retain the payload across an unchanged retry. The preview's `rows` and `source`
provide the operator view; neither the preview nor a filename proves real part
compatibility. Existing import controls and manual order handling remain intact.

### Real-core integration evidence

Fifteen new tests passed in 6.042 seconds against exact SPRUCE core blob
`1369aae88363236e49d9ca2e429517cb79739d58`, consumed from commit
`687d5eafca97ca04acf36fc9bfb366f2e1807622`. These are additional composition cases,
not a repetition of the core author's accepted test panel.

```sh
PYTHONWARNINGS=error::ResourceWarning python -m unittest -v test_catalog_intake.py
```

Actual SQLite, HTTP and CLI subprocess coverage: mapped CSV import; exact source
metadata in handoff text; restart and sixteen concurrent retries; stale fit review
after changed source; delayed old retry preserving the newer version; no partial
import on invalid later rows; normalized duplicate IDs; explicit dates/identifiers;
unknown prices; metadata length/HTTP/batch limits; preview before apply; existing
output preservation and configuration ambiguity diagnostics. The synthetic HTTP
example produced three parts at USD 32.45 plus USD 7.50 shipping: USD 104.85 before
tax, with unreviewed fit retained. No supplier was contacted and no order was placed.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
