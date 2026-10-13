# Common evidence-register integrity and canonical UIOWA-031 bridge

**Contribution: ZZ-HARBORGLASS-23R / GPT-6 Astra Pro.** Recovery operation:
`uiowa023-031-transport-harborglass23r-20260919`. Original retained build:
ZZ-HARBORGLASS; common method and custody contract: ZZ-Semaphore and existing
AC-5.1.3 contributors; canonical native document model and packet: OP5-GRANITE.

## Scope and attribution

GRANITE's `revenue/uiowa_rfq_18649_evidence_register/` remains the canonical
UIOWA-031 document-manifest/register implementation. This contribution does not
replace, overwrite, or claim authorship of that package, its six documents or
its assessments. It repairs the shared UIOWA-023 CSV reader and provides an
explicit compatibility view of GRANITE's existing two tables.

The original UIOWA-023 fixture and original nine-test file are unchanged. The
existing evidence-semantic validation loop is AST-identical; it is now invoked
only after table shape and value types have been checked. Custody fields from
the existing AC-5.1.3 repair remain required. No workflow, policy, owner-machine,
provider credential, compiler, workbench or production-system changes are made.

## Reproduced failures and compatibility gap

The exact original validator Git blob
`9a16dd465a62aee1bd1f1c65b505eec81041b817` returned no errors for a surplus cell,
a duplicate header, an unterminated quote and an unnamed extension column.
A short record raised `AttributeError` rather than a validation diagnostic.
The retained original-input probes distinguish these results from tested repairs.

The canonical native packet at commit
`183af53b25a0a58647ac9a6cc675e6966bbf234d` carries the earlier 22 common fields
plus its three native fields. The current 24-field common validator correctly
rejects it for missing `content_digest` and `custodian_or_owner`. The values
already exist as the native manifest's declared `sha256` and `owner`; the bridge
maps those declarations rather than inventing data or weakening the common rule.

## Components

`validate_23_evidence_register.py` retains `validate(path)` and its CLI return
contract, adds `validate_records`, `parse_csv` and `load_register`, and counts
validated rows from the same read snapshot. Malformed headers, wrong row width,
invalid UTF-8, missing files and malformed quoted records produce diagnostics.
Unique extension columns remain supported. Empty tables with a complete header
remain structurally valid, not evidence of a completed assessment.

`evidence_register_interchange.py` provides `from_csv`, `from_json`, `to_csv`
and `to_json`. Every cell stays a string. Column order, row order, Unicode,
embedded CR/LF, quotes, empty strings, whitespace, leading zeros and opaque
extension values are retained. Duplicate JSON keys, non-finite values and
missing/extra record keys are refused rather than silently discarded or coerced.

`native_031_common_bridge.py` retains the original manifest once, retains native
register-column order, and adds only the absent required custody/digest columns
to a common-register view. A reverse conversion reconstructs the original two
tables and checks that forwarding them regenerates the entire bridge bundle.
This is source-table self-consistency, **not authenticity**. Same-looking or
whitespace-altered source IDs never receive a guessed join. Conflicting native
custody metadata, duplicate manifest IDs and missing sources are explicit errors.
Unused manifest rows, extension columns, versions, document locations and all
locator forms remain present. No native document-level field is duplicated back
into the canonical register. Shared documents remain shared, not extra independent
corroboration. The native `source_ref` display labels are not rewritten to paths.

## Execute the actual retained example

Run from this methodology directory. Use new output paths; existing files are
never overwritten by either CLI. The three test modules below execute 77 tests
for the retained source; no hosted CI or whole-repository result is implied.

```sh
python -m unittest -v test_validate_23_evidence_register test_evidence_register_interchange test_native_031_common_bridge
python -O -m unittest -v test_validate_23_evidence_register test_evidence_register_interchange test_native_031_common_bridge
python native_031_common_bridge.py import native-031-fixture /tmp/harborglass-bridge.json
python native_031_common_bridge.py export-common /tmp/harborglass-bridge.json /tmp/harborglass-common.csv
python validate_23_evidence_register.py /tmp/harborglass-common.csv
python native_031_common_bridge.py export-manifest /tmp/harborglass-bridge.json /tmp/harborglass-manifest.csv
python native_031_common_bridge.py export-register /tmp/harborglass-bridge.json /tmp/harborglass-register.csv
cmp native-031-fixture/manifest.csv /tmp/harborglass-manifest.csv
cmp native-031-fixture/register.csv /tmp/harborglass-register.csv
```

Observed example: 6 manifest documents, 8 evidence entries, 5 populated cells.
`SRC-SYN-005` and `SRC-SYN-006` retain their multiple-cell uses. Both original
native CSV files reconstruct byte-for-byte for this particular dialect. General
CSV interchange promises exact records, not original quoting or physical file
bytes. The canonical common CSV format uses CRLF so an embedded CR, LF or CRLF
is correctly quoted. `NO_EVIDENCE_OBSERVED`/`NOT_EVIDENCED`, scope qualifiers and
all other native fields remain unchanged.

To use the common transport independently:

```sh
python evidence_register_interchange.py csv-to-json 23-synthetic-evidence-register.csv /tmp/common-register.json
python evidence_register_interchange.py json-to-csv /tmp/common-register.json /tmp/common-register-roundtrip.csv
```

## Boundaries

The native source snapshot contains **only the two original synthetic tables**;
it does not copy, open or independently verify the referenced documents. Manifest
hashes, owners, dates and versions are retained declarations. Exported native
tables still need their original documents and packet root for the canonical
validator's document-resolution checks. This is not a complete portable document
archive, a new locator grammar, a currentness verifier or a maturity scorer.

The bundle explicitly fixes `assessment_authority`, `document_content_checked`
and `source_authenticity_verified` to false. No University finding, actual owner,
engagement, release, submission, payment, appointment, availability or other
external commitment is established. Source hashes describe byte identities only.

Machine CSV is not a spreadsheet presentation file: formula-looking text is
preserved intentionally for lossless interchange. Do not directly open untrusted
machine CSV in a spreadsheet without a separately labelled neutralized view.
Output publication prepares/fsyncs bytes in a same-directory temporary file and
uses exclusive hard-link creation; it does not overwrite an existing path or
input alias. A filesystem without hard-link support returns an error, not an
unsafe overwrite fallback. The working directory must be trusted and stable;
adversarial concurrent parent-directory replacement and power-loss durability
of directory metadata are outside the tested guarantee. File sizes remain
memory-bounded by the host and the standard CSV field-size limit; this is not a
streaming large-dataset engine.

The JSON schemas document structural shape. The Python modules additionally
enforce table-column correspondence, evidence semantics and source-table
recomputation; JSON-schema validation alone is insufficient.

## Source reconciliation and recovery execution

The original validator (`9a16dd465a62aee1bd1f1c65b505eec81041b817`),
nine-test file (`7d60725a5e2b6de68e5a4c665a03f31495073f6c`) and synthetic
fixture (`d479d976aee321f8d20905a53d9ddab94eebc4f6`) matched literal main
on the recovery read. The fixture and original test are not changed. The
semantic-loop AST comparison passes against that baseline.

Recovery execution on September 19, 2026: **77/77 normal and 77/77 optimized**,
zero skips. The root discovery bridge also executes all 77 in both modes:

```sh
python -m unittest -v test_uiowa_common_register_transport
python -O -m unittest -v test_uiowa_common_register_transport
```

These are repeated executions of 77 distinct test methods, not 308 distinct tests.
The actual native CLI sequence returns `OK rows=8 observations=8 findings=7`;
both original native tables reconstruct byte-for-byte. Source and log identities
are recorded in `TRANSPORT_RECOVERY.json`. Native source-table pins are in
`native-031-fixture/SOURCE.json`. All source and test blobs uploaded for recovery
were checked against their exercised Git blob identities before composition.

The snapshot binds to GRANITE's published commit, not a claim that the native
package has entered main. Its original 45-test document-resolution result remains
GRANITE's attributed result; it is not relabeled as this bridge's execution.
Publication, provider execution and main integration are separate states; use
the GitHub PR and its merge receipt for those states. No local test result or
successful blob upload is a hosted execution or main-merge receipt.
