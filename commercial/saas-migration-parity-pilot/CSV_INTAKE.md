# CSV intake for the SaaS Migration Parity Pilot

Run a retained-export comparison without hand-authoring nested record JSON. The browser and CLI call the existing `parity.compile_bytes()` implementation; no parity rule, commercial offer, provider integration or report schema is changed.

## Browser workflow

The CSV-plan route now lives inside the single export workbench:

```sh
cd commercial/saas-migration-parity-pilot
python3 workbench.py --port 8767
```

Use Python 3.10+. Open the exact printed `http://127.0.0.1:8767/` address. Use `--port 0` for a free port and Ctrl-C to stop. The service binds only to IPv4 loopback; it is not a hosted or multi-user deployment. No third-party packages are required. Do not put it behind a public proxy. The former `web_intake.py` and `web_intake.html` files are removed rather than maintained as a second frontend.

Select **Reusable CSV plan · Batch-compatible aliases**. This explicitly calls the existing CSV adapter, not the general CSV/JSON adapter. Existing `saas-migration-csv-intake/v1` plans import unchanged; importing one selects the correct mode. General workbench plans use `saas-migration-workbench-plan/v1` and are not accepted by the CSV batch CLI. Their original-name/all-field manifests must not be confused with the selected-column alias manifests here.

1. Select retained source and target CSVs and declare each delimiter. Columns are inspected when a file or delimiter changes. UTF-8 with an optional BOM is supported; previews show headers, counts and original-byte hashes, not raw row values.
2. Add 1–4 composite identity columns and 1–32 compared fields. Choose each source/target header and type explicitly. Similar names do not imply a mapping. Duplicate-key records remain for the engine to classify.
3. Enter distinct snapshot IDs, schema revisions, capture times, intended cutover and maximum age. Times use exact UTC seconds, for example `2026-09-23T08:00:00Z`. Completeness checkboxes begin unchecked and remain operator declarations, not proof of live-record coverage.
4. Compare and inspect differences and holds. Filter classifications, search opaque keys/original field names/reasons, and open alias-aware mismatch details. Report-only JSON/Markdown/printable HTML are separate from the **Private replay ZIP**, which contains selected raw values.

Input changes invalidate results and downloads. **Save current plan** preserves the explicit mapping and metadata without source rows. **Load a saved plan** validates its format and reinspects already selected files; its mappings wait for both inspected inputs. Missing columns stay blank for explicit repair. A newly selected file clears its capture time and completeness, even after a plan supplied those facts. Reconfirm metadata whenever reusing a plan; import is not source attestation.

The app has no analytics, external assets, provider calls, cookies, local storage, background polling or persistent server upload directory. CSVs/results live in browser/process memory. This does not promise secure-memory erasure: swap, browser tooling and downloaded files are outside that claim. Clear-session removes working references/download URLs, not downloaded files. The unified server retains exact local Host/Origin checks and a per-launch request token; reload the page after restarting it.

## Exact conversion behavior

Each file is bounded to 4,000,000 bytes, 500 data records and 64 columns. Delimiters are comma, semicolon or tab, explicitly selected per file. Quoting uses Python's strict CSV reader. Duplicate/empty headers, headers over 256 characters, control characters, malformed quoting and inconsistent row widths are rejected. Blank records are not silently removed. Header-only exports are supported; declared-completeness and freshness rules still apply. Generated engine input retains its existing 4,000,000-byte bound.

Individual cells may use that file budget in both browser and batch modes, including long excluded text columns. Mapped values retain the limits below.

Strings are preserved after CSV decoding: no trimming, case folding, date guessing, numeric or Unicode normalization. Mapped strings must be nonempty, at most 2048 characters and contain no controls. Empty cells are not inferred as null. Integer conversion accepts only optional minus plus unpadded decimal digits in signed 64-bit range; it rejects fractions, exponents, spaces and padded identifiers. Use string for IDs such as `001234`. Boolean conversion accepts exactly lowercase `true` or `false`; booleans cannot be key columns. Unmapped values are not interpreted or compared. CSV formulas remain strings, never evaluated; no CSV result file is generated.

CSV headers need not fit the engine field-name grammar. The adapter maps selected names to `key_1`…`key_4` and `field_1`…`field_32` on both sides. Plan/column-map files preserve original headers and types and identify exclusions. Report hashes and mismatch aliases describe the mapped manifest, not original CSV representation. Original CSV byte hashes remain in the column map, including BOM and line endings. Unselected columns are absent from the replay manifest.

Freshness is evaluated at the **declared cutover** by the unchanged engine. Neither intake mode independently establishes present-time snapshots, live SaaS completeness or production-migration readiness.

## Batch CLI and replay

The unchanged adapter remains available independently of the browser:

```sh
python3 csv_intake.py --source source.csv --target target.csv \
  --plan intake-plan.json --output private-comparison.zip
```

The output path must be new. The CLI creates it with owner-only permissions where supported, does not overwrite it, and does not create missing parents. A failed write can leave a partial file; use a new path after resolving the error. Input reads reuse the existing bounded regular-file reader. Browser downloads instead use ordinary browser save behavior.

Plan shape below is illustrative metadata, not actual export facts:

```json
{
  "schema": "saas-migration-csv-intake/v1",
  "cutover_at_utc": "2026-09-23T08:00:00Z",
  "max_snapshot_age_seconds": 86400,
  "key_map": [{"source": "Record ID", "target": "External ID", "type": "string"}],
  "field_map": [{"source": "Status", "target": "Lifecycle", "type": "string"}],
  "source_snapshot": {
    "snapshot_id": "source-export", "schema_revision": "1",
    "captured_at_utc": "2026-09-23T07:00:00Z", "complete": false, "delimiter": ","
  },
  "target_snapshot": {
    "snapshot_id": "target-export", "schema_revision": "1",
    "captured_at_utc": "2026-09-23T07:05:00Z", "complete": false, "delimiter": ","
  }
}
```

Both browser and batch CSV routes use the same `compile_csv` and `bundle_bytes` functions. The five-file ZIP contains `manifest.json`, `report.json`, `report.md`, `intake-plan.json` and `column-map.json`. It does not contain original CSVs or source checkout; preserve those separately. Reports use exact canonical bytes. Browser column-map output adds an explicit mode, plan schema, original-byte counts/hashes and separate generated-manifest digest; those explanatory fields and ZIP container metadata are not a deterministic engine receipt or an identical-ZIP-byte claim.

The existing replay entrypoint accepts the extracted manifest and report:

```sh
python3 parity.py verify --input /private/extracted/manifest.json \
  --report-json /private/extracted/report.json
```

This is an operator capability, not a new development test runner. No suite, workflow, fixture or validation framework accompanies the frontend consolidation.

## Sharing and lineage

The private replay bundle includes selected raw identifiers and values. Do not publish it or attach it to a public issue. Report-only files omit raw row values but contain snapshot metadata, aliases and unsalted commitments, not guaranteed anonymization. The column map exposes original headers. Review every artifact for its intended recipient. Original-byte hashes establish correspondence, not source authenticity or completeness.

Original product: Z-GrothendieckAnvil-2144-H8C3 (ZGA-H8C3). Implementation recovery: Z-Sol-01A. CSV adapter, original browser, plans and private bundler: yZ-Quarry-47. General workbench/portable report: yZ-Kestrel. One-browser integration under #19307: yZ-Kestrel-V68. Existing #14205 commercial/outbound ownership, price and provider boundaries remain unchanged; no customer deployment, contract, payment or revenue is asserted.

See [WORKBENCH.md](WORKBENCH.md) for the unified interface, distinct general-plan format and printable-report route.
