# SaaS Migration Parity Pilot

A dependency-free, export-only diagnostic for answering one concrete cutover question: **does the sanitized target export preserve the explicitly mapped source records and fields at a declared point in time?**

## Browser workbench

Load sanitized exports, choose an explicit intake contract, enter snapshot metadata, map keys and compared fields, browse classifications, and download reports or private replay material. The single workbench uses the existing comparison engine and both retained adapters rather than maintaining a second parity implementation.

```bash
cd commercial/saas-migration-parity-pilot
python workbench.py --port 8767
```

Open the exact printed loopback address on the same machine. Python 3.10+ and the standard library are sufficient. No external services or persistent upload store are used. The local Host/Origin/per-launch-token boundary is retained; this is not a hosted customer endpoint. The former CSV-only `web_intake.py` / `web_intake.html` frontend has been removed. Full format, privacy and download contracts: [WORKBENCH.md](WORKBENCH.md).

**General CSV/JSON** preserves original field names and all supplied fields in its private manifest. **Reusable CSV plan** preserves the existing batch adapter's explicit selected-column `key_*/field_*` aliases, delimiters and excluded-column map. Plan import selects its format explicitly; no silent translation or identical-manifest-hash claim is made between adapters. JSON integer identifiers stay exact, including values outside JavaScript's safe-integer range. CSV types are selected, never inferred.

Both modes support saved plans, original-file hashes distinct from generated-manifest hashes, searchable exceptions, exact report JSON/Markdown, standalone printable HTML and an explicitly private replay ZIP. Editing inputs invalidates previous results/download links. Raw input values belong to private replay material; report hashes are not guaranteed anonymization.

## CSV batch and private replay route

The unchanged `csv_intake.py` CLI accepts two CSV files plus an existing `saas-migration-csv-intake/v1` plan and writes a new private five-file ZIP. The workbench's **Reusable CSV plan** mode imports/exports that same plan contract and reuses the same adapter/bundler. See [CSV_INTAKE.md](CSV_INTAKE.md).

General workbench plans are separately labeled `saas-migration-workbench-plan/v1` and are not CSV batch plans. The ZIP contains the generated manifest, exact report JSON/Markdown, format-labeled plan and column map, not original export files. Retain original files separately. CSV-plan replay includes selected raw values; general replay includes all supplied fields, including unmapped values. Keep both private.

## Commercial offer

- **$5,000 fixed diagnostic** for one sanitized source export + one sanitized target export, each capped at 500 records.
- Buyer supplies the explicit record-key map and compared-field map.
- Output is a deterministic JSON evidence packet plus a concise buyer-facing Markdown report.
- **No free custom API adapter** is included.
- A **$10,000 optional integration sprint** is a separate later scope only if the paid export diagnostic establishes value and the actual adapter surface is known.

## What it does

The engine accepts a strict JSON manifest containing:

- source/target snapshot IDs, schema revisions, capture times and explicit completeness declarations;
- one to four source→target record-key mappings;
- one to 32 source→target compared-field mappings with explicit `string`, `integer`, or `boolean` types;
- a declared cutover instant and maximum snapshot age;
- at most 500 normalized records per snapshot.

Every union key receives exactly one classification:

- `PARITY`
- `MISSING_TARGET`
- `UNEXPECTED_TARGET`
- `FIELD_MISMATCH`
- `STALE_EVIDENCE`
- `DUPLICATE_KEY`
- `INVALID_EVIDENCE`

Raw record keys and mismatched values are not copied into the report. Row-level evidence uses SHA-256 commitments; mismatch rows expose only mapped field names plus source/target value digests.

## Truth boundary

`PARITY_CONFIRMED` is a point-in-time statement about **the exact supplied sanitized export bytes, declared completeness, mapping and freshness policy**. It is not a production cutover certification and cannot prove records omitted from an incomplete export do not exist.

The comparison engine performs no external network calls. The optional browser workbench sends export text only to its loopback process. Neither route has authority to:

- log in to or mutate a SaaS provider;
- migrate production records;
- contact a buyer or vendor;
- accept/sign a contract;
- charge or collect payment;
- recognize revenue.

## Determinism and custody

The receipt binds both:

1. `raw_input_sha256` — the exact input JSON bytes; and
2. `semantic_manifest_sha256` — the normalized order-invariant manifest semantics.

Thus whitespace-only byte changes produce a new exact-byte digest while retaining the same semantic digest/report classifications. Snapshot record digests and union-key commitments are order-invariant. For workbench intake, the input digest binds the generated engine manifest. The separate original-file hashes bind the pre-conversion CSV/JSON bytes, including BOM and line endings; retain the original files because the replay ZIP does not include them. Neither digest authenticates a source or proves completeness.

Strict JSON rejects duplicate keys, floats/non-finite values, unknown critical keys, bool/int aliases through exact declared types, malformed timestamps/IDs, oversized inputs and unsupported field values. CLI input descriptors open nonblocking before the regular-file check, so a named pipe without a writer is rejected instead of waiting for one. Ordinary file reads retain the same byte limits, exact bytes and identity checks. CLI file ingress and paired report publication use retained descriptor-relative directory custody: every ancestor and final component is opened without following symlinks and parent-generation replacement fails closed when observed. After directory persistence, both visible output leaves and their parent generations are revalidated immediately before descriptor close and success; substitution observed through that final check fails closed. A same-UID actor that retains directory rename/write authority can still mutate paths after the final check or after return, so preventing post-publication mutation requires ownership and permission controls outside this process.

On failed CLI paired publication, rollback **never pathname-deletes** a reserved output: it truncates only the retained owned file descriptor best-effort and closes it. A surviving owned directory entry is therefore a fail-visible zero-byte tombstone requiring explicit operator cleanup; this is intentional because portable pathname `stat`→`unlink` cannot atomically guarantee that a same-directory foreign successor has not replaced the owned inode. Platforms that lack the required no-follow/`dir_fd` primitives fail closed rather than silently falling back to pathname-only I/O. Browser downloads use the browser's ordinary save mechanism instead and do not claim these CLI filesystem guarantees.

## Command-line example

```bash
cd commercial/saas-migration-parity-pilot
python synthetic_fixture.py > /tmp/saas-parity-input.json
python parity.py compile \
  --input /tmp/saas-parity-input.json \
  --report-json /tmp/saas-parity.json \
  --report-md /tmp/saas-parity.md
```

The retained `synthetic_fixture.py` emits **500 source records and 500 target records**. Its expected union is 505 keys: 490 parity, 5 field mismatch, 5 missing target and 5 unexpected target. The compile command requires new output paths; it does not overwrite existing files.

To check a delivered report against its supplied manifest, the product's offline verifier remains available:

```bash
python parity.py verify --input parity-input.json --report-json parity-report.json
```

The CLI verifier retains the 4,000,000-byte manifest limit. A valid report can be larger because every mismatched field includes two value digests and mapped field names. Verification compiles the supplied manifest once, then allows the greater of 4,000,000 bytes and that exact expected report length for the report read. The report must still match deterministic recompilation byte for byte; extra bytes, altered findings and malformed JSON remain failures. The `verify_bytes()` API uses the same comparison.

Current repository [swarm rules](../../RULES.md) govern development execution. This guide does not prescribe a test battery, optimized-Python rerun or new workflow. CSV adapter/plan/bundler credit remains yZ-Quarry-47; general browser and portable report credit remains yZ-Kestrel. One-browser consolidation is yZ-Kestrel-V68 under #19307; existing product lineage, commercial offer and outbound ownership remain unchanged.
