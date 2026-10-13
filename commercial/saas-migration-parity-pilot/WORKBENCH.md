# Export workbench

One browser entrypoint for the existing SaaS Migration Parity Pilot engine, with explicit CSV/JSON intake, reusable plans, original-file provenance, exception browsing and private replay downloads. The comparison engine and CSV batch CLI remain unchanged.

## Start

From this directory, with Python 3.10 or newer:

```bash
python workbench.py --port 8767
```

Open the exact printed `http://127.0.0.1:8767/` address on the same machine. `--port 0` chooses an available port. Stop with Ctrl+C. This local operator tool listens only on IPv4 loopback; do not publish it behind a proxy or expose it as a customer endpoint. Host and Origin must match the printed address, and browser requests carry a per-launch token. Restarting the server requires reloading the page. These checks preserve the previous CSV frontend's local request boundary, not multi-user authentication.

No third-party packages, external assets, SaaS credentials, external API calls, upload directory or persistent job store are required. Missing assets or a bind failure produce `ERROR:` on stderr and exit code 2. Invalid requests produce a non-success HTTP status and a visible error, not a successful report. The duplicate `web_intake.py` / `web_intake.html` frontend has been removed; the command above is the browser launch path for both intake modes.

## Choose the intake contract

The mode is explicit because the existing adapters generate different manifests.

| Mode | Existing adapter | Mapping and retained values | Saved-plan schema |
| --- | --- | --- | --- |
| General CSV/JSON | `export_intake.build_manifest` | Original field names; all supplied fields stay in the private manifest, including unmapped fields. Only explicitly mapped fields are compared. CSV uses commas. | `saas-migration-workbench-plan/v1` |
| Reusable CSV plan | `csv_intake.compile_csv` | Only selected CSV columns enter the private manifest, as `key_1`…`key_4` and `field_1`…`field_32`. Original headers, alias mappings and excluded columns remain in the column map. Delimiters are explicit per source. | Existing `saas-migration-csv-intake/v1` |

Both modes call the same parity engine. Do not assume identical generated-manifest hashes or silently exchange their plans. Import recognizes the schema and selects its adapter; unknown formats are rejected. CSV plans remain compatible with the unchanged batch CLI. General plans are for this workbench, not the CSV batch parser. To move from one contract to another, explicitly choose the new mode and map its columns; no hidden translation is performed.

## Complete a comparison

1. Choose the mode, then load the sanitized source and target exports. Inspection shows field names, record counts, byte counts and SHA-256 of the original UTF-8 bytes, without displaying record values. In general mode, a recognized filename extension selects CSV or JSON, not field types or snapshot facts. CSV-plan mode exposes comma, semicolon and tab selectors.
2. Enter distinct snapshot IDs, schema revisions and actual capture instants in `YYYY-MM-DDTHH:MM:SSZ` form. Declare completeness only for the agreed scope. Replacing a file clears that side's capture time and completeness declaration.
3. Set cutover and maximum snapshot age in seconds. The current-UTC button changes only cutover; upload time and file modification time never stand in for capture time.
4. Explicitly select 1–4 key mappings and 1–32 compared-field mappings. Keys support string and integer; compared fields also support boolean. Choices start blank. Replacing an export resets mappings rather than silently applying old choices to different data.
5. Compare. Filter classifications, search by opaque key, original field name or reason, and inspect mismatch digests. CSV-plan aliases are shown alongside their original source/target headers. Rows remain paginated in groups of 50.
6. Download report-only JSON/Markdown/printable HTML, the format-labeled plan, column map/provenance, or explicitly labeled private input/ZIP. Editing inputs invalidates displayed results and download links. Responses for changed inputs are discarded.

Unchecked completeness, stale/future snapshots, duplicate keys, missing/unexpected records and mismatches retain the engine's classifications. No omitted record is inferred to be absent. Freshness remains evaluated at the declared cutover, not independently established present-time source authority.

## Save and reuse a plan

**Save current plan** stores mappings, formats/delimiters and declared snapshot metadata after normal input validation. It does not run a comparison or include export records. It requires loaded exports and complete form fields. After comparison, the corresponding exact plan is also a download.

**Load a saved plan** accepts a UTF-8 JSON file up to 100,000 bytes. The server uses the existing strict JSON parser before the browser applies the bounded metadata. Duplicate keys, unsupported schemas, unsafe numeric metadata and malformed plan fields are rejected. Selecting a plan changes the mode explicitly and reinspects any already selected exports through that adapter. Missing mapped columns remain blank and require repair; there is no guessed substitute.

A plan can be loaded before or after selecting exports. The plan picker resets after taking a file, so choosing that same saved plan again explicitly reloads it. Its mappings wait for both inspected inputs. Selecting a different file still clears that side's capture time and completeness, even when a plan supplied them; explicitly update those facts. Loading a saved plan after selecting files restores its recorded metadata, which the operator must review and reconfirm. Importing a plan never attests that an old capture time or completeness claim applies to new records.

General plans have the same top-level metadata, mapping and source/target snapshot structure as the CSV plan, but use their own schema and a `format` (`csv` or `json`) in each snapshot instead of `delimiter`. Neither plan embeds source text. The full legacy CSV plan and batch examples remain in [CSV_INTAKE.md](CSV_INTAKE.md).

## Native browser handoff

The retained fictional 500-source/500-target example has been exercised through the actual loopback workbench in Chromium 153. Both intake modes retain 505 union keys: 490 parity, five missing, five unexpected and five mismatched. Explicit saved-plan reuse after restarting the server reproduces the original report bytes; replacing source files still clears their capture and completeness declarations. The general and CSV plans retain their distinct schemas and original-name versus selected-alias manifests.

Native downloads of each five-file private replay bundle match the separate manifest, JSON/Markdown report, plan and column-map downloads. The unchanged `parity.py verify` accepts both downloaded manifest/report pairs. The portable HTML returns the exact report JSON, keeps all 505 rows available without JavaScript, and prints all rows while screen filters show only the five mismatches. Workbench and offline pages fit a 390 px viewport; wide tables remain within their existing scroll containers. These are fictional local operator observations, not live-source, production-cutover, hosted-deployment or customer acceptance.

## Export formats

Both modes bound each export to 500 records and 4,000,000 bytes, with at most 64 columns. UTF-8 CSV may have a BOM. Invalid UTF-8 is rejected, not replaced. The browser preserves BOM and line endings, allowing the server's UTF-8 encoding to hash the exact original bytes. The generated combined engine manifest retains its existing 4,000,000-byte bound.

**General CSV/JSON:** CSV uses a header and comma delimiter. Column names follow the existing engine grammar: start with a letter, then letters, digits, `.`, `_` or `-`, up to 64 characters. JSON is an array of flat objects, not a prebuilt engine manifest. Duplicate JSON keys, floats/non-finite numbers, nested values, nulls, blank strings and unsupported controls are rejected, not silently discarded. Duplicate CSV headers and inconsistent widths are errors; data is not truncated.

CSV type conversion is explicit: integers use unpadded decimal digits with an optional minus sign; booleans are exactly `true` or `false`; strings are not trimmed, case-folded or guessed. Use string for leading-zero identifiers. Unmapped general CSV cells remain strings. Conflicting types for the same original key/compared field are an error. JSON values keep their existing types; a JSON string is not silently changed into an integer because a mapping requests one.

**Reusable CSV plans:** the existing adapter permits headers up to 256 characters, including spaces, because it maps selected columns to engine-compatible aliases. It rejects duplicate/empty headers, controls, ragged records and malformed quoting. Unmapped values are not interpreted or compared. Exact limits and conversion semantics, including selected-field-only replay, remain in [CSV_INTAKE.md](CSV_INTAKE.md).

Integer record values never pass through JavaScript's number parser. The browser sends original text, Python parses it, and manifest/report/plan downloads preserve returned canonical strings. The browser parses only bounded plan/provenance data and digest-only report metadata for presentation.

## Download fidelity and privacy

Report-only JSON, Markdown and printable HTML omit raw row values but contain metadata, field names and unsalted commitments; hashes do not guarantee anonymization. The column map additionally exposes original headers and source-file hashes. Review each artifact for its intended recipient.

The **private input JSON** is a generated normalized engine manifest, not either original export. The **private replay ZIP** uses the existing five-file bundler: `manifest.json`, exact `report.json`, `report.md`, `intake-plan.json` and `column-map.json`. In general mode, `intake-plan.json` inside the ZIP still carries the distinct general-plan schema. The ZIP contains all retained raw values for that mode: selected CSV columns for CSV plans, all supplied fields for general intake. Original exports, printable HTML and source checkout are not bundled. Preserve the original export files separately.

`original_file_sha256` and byte counts describe original selected UTF-8 files. `generated_manifest_sha256` and the report's `raw_input_sha256` bind the generated engine input. These are separate identities, not source authenticity/completeness proofs. CSV mode also retains its existing `csv_sha256`, aliases and exclusions. Browser provenance adds explanatory fields; ZIP container metadata is not deterministic, and no identical ZIP-byte claim is made between browser and batch runs.

The existing verifier can consume the exact manifest/report downloads or extracted ZIP files:

```bash
python parity.py verify --input parity-input.json --report-json parity-report.json
```

The server retains no files between requests. The page holds text/download blobs in memory; clear-session drops working references and revokes URLs, but does not delete downloads or promise secure memory erasure. Browser extensions/tooling, operating-system memory/swap and downloaded files are outside that claim. No cookies, local storage, analytics or background polling are introduced. Browser downloads use ordinary browser save behavior, not the CLI's descriptor-relative filesystem guarantees.

## Portable browser report

Choose **Printable HTML** for a self-contained report that opens without Python, a server or network access. The existing `offline_report.py` implementation is preserved. It includes snapshot metadata, mappings, counts, classification/search controls, all reasons and mismatch digests, and an exact JSON download. All result rows remain readable without JavaScript; only interactive controls need it.

Printing includes **every report row**, even when screen filters hide some. Embedded JSON is base64-encoded from canonical report bytes and decoded directly for download, not parsed and reserialized through JavaScript. Content-hashed inline scripts/styles and a restrictive Content Security Policy request no external resources.

The HTML presents a compiled report; it is not a signature, independent verification run or production-cutover certification. Editing HTML can change its presentation. It embeds report metadata/digests, not input record values, but still needs appropriate privacy handling.

The same portable output is available without starting the workbench:

```bash
python offline_report.py \
  --input parity-input.json \
  --report-json new-report.json \
  --report-html new-report.html
```

Both output paths must be new. This route reuses the bounded input reader, comparison engine and paired create-exclusive writer. No new verifier or receipt schema is introduced by the browser consolidation.

## Lineage and boundaries

Original product/recovery lineage remains in `README.md`. General workbench and portable report: yZ-Kestrel. CSV adapter, plans and private bundler: yZ-Quarry-47. One-browser integration: yZ-Kestrel-V68, issue #19307. The original engine, CSV batch CLI, general export adapter and printable renderer are not reimplemented.

No hosted deployment, SaaS/provider access, customer contact, production migration, contract, payment, new price or revenue-recognition action is performed. Existing #14205 commercial/outbound ownership remains unchanged.
