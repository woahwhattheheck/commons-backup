# Evidence-register transport: worked synthetic demonstration

**ZZ-HARBORGLASS-23R / GPT-6 Astra Pro — September 19, 2026.**

This readable result accompanies [source PR #16395](https://github.com/woahwhattheheck/commons/pull/16395).
The executable carrier, not this document's presence on main, determines which
code is integrated. The exercised source is preserved at commit
[`f559a1fa0f96ef7ef70b0ce2e9f618057ed3f16b`](https://github.com/woahwhattheheck/commons/commit/f559a1fa0f96ef7ef70b0ce2e9f618057ed3f16b).
A documentation merge does not grant executable-integration or provider-execution authority.

## What this demonstrates

A native document manifest and its evidence register can be carried into the
current common register and back **without losing their records or upgrading
what those records claim**. The native register has 22 common columns and three
native columns; the common validator now requires two additional custody fields.
The bridge maps the manifest's existing declared owner and SHA-256 into those
fields. It does not invent an owner, fetch a document, reinterpret confidence,
or treat two references to one source as independent corroboration.

The scenario is entirely fictional. Its document identities, declared owners,
dates, versions, observations and confidence labels are synthetic inputs, not
findings about the University, its staff, or its systems.

## Follow the actual packet

The executed packet contains **six manifest rows, eight evidence entries and
five populated group/area cells**. Each row below comes from the actual generated
common-register view. The abbreviated evidence ID preserves the distinct final
segment; full IDs are retained in the carrier's fixture and generated view.

| Evidence suffix | Source ID | Cell | Exact locator | Retained evidence state / confidence |
|---|---|---|---|---|
| ESS-SD-POL-001 | SRC-SYN-001 | ESS/SD | `section:Required checks` | SUPPORTING / LOW |
| ESS-SD-INT-002 | SRC-SYN-005 | ESS/SD | `lines:8-10` | SUPPORTING / LOW |
| ESS-DEP-CHG-003 | SRC-SYN-004 | ESS/DEP | `row:CHG-SYN-2044` | SUPPORTING / MODERATE |
| RIS-SEC-POL-004 | SRC-SYN-002 | RIS/SEC | `section:Annual review` | SUPPORTING / LOW |
| IAM-SEC-INV-005 | SRC-SYN-003 | IAM/SEC | `key:summary` | SUPPORTING / HIGH |
| ESS-SD-DOC-006 | SRC-SYN-006 | ESS/SD | `section:Change approval` | SUPPORTING / LOW |
| IAM-SEC-DOC-007 | SRC-SYN-006 | IAM/SEC | `section:Access to the deployment pipeline` | SUPPORTING / LOW |
| ESS-AI-INT-008 | SRC-SYN-005 | ESS/AI | `lines:16-17` | NO_EVIDENCE_OBSERVED / NOT_EVIDENCED |

`SRC-SYN-005` remains one interview-note manifest row used by ESS/SD and ESS/AI.
`SRC-SYN-006` remains one joint-controls-memo manifest row used by ESS/SD and
IAM/SEC. No extra document is invented for either second citation.

The ESS/AI entry is still `NO_EVIDENCE_OBSERVED / NOT_EVIDENCED` after transport.
Its narrative reports individual assisted-coding use and a lack of written
review guidance in the interview note; it is **not** transformed into a verified
organization-wide finding that guidance does not exist. The IAM/SEC inventory's
`HIGH` label is preserved as input metadata, not independently awarded by the
bridge. All native claims, scope limits and follow-up fields are unchanged.

For the first entry, `custodian_or_owner` is exactly the manifest's
`ESS delivery lead (role)`. `content_digest` is `sha256:` followed by that
manifest's declared 64-hex digest. The retained `source_ref` remains the display
label `ESS Branch Protection Standard v3`; it is not silently rewritten into a
path. Version, supplied date and document location remain in the manifest.

## Literal successful execution

A real command-line import, common export, common validation, manifest export
and native-register export all returned exit code zero. The common validator
printed:

```text
OK rows=8 observations=8 findings=7
```

The exported manifest and native register both compare byte-for-byte equal to
their original fixture files. That stronger result applies to this packet's CSV
dialect. The general transport promise is exact cells, column order and row
order; arbitrary original quoting and physical line endings are not promised.
Embedded CR, LF, CRLF, quotes, whitespace, Unicode and extension-cell strings
are preserved by the common transport.

## Seven controlled rejection cases

The following results were produced by the published functions on independent
copies of the source tables or generated bundle. Each case changed only its
named condition; none used a live document or external system.

| Input change | Actual outcome | Exact diagnostic |
|---|---|---|
| Original native register directly into the common validator | REJECTED | `missing required columns: ['content_digest', 'custodian_or_owner']` |
| Duplicate manifest source ID | REJECTED | `manifest source_id must be nonblank and unambiguous` |
| Unresolved source ID | REJECTED | `unresolved exact source_id 'not-in-manifest'` |
| Whitespace-altered source ID | REJECTED | `unresolved exact source_id 'SRC-SYN-001 '` |
| Changed derived digest without changed source table | REJECTED | `bridge metadata or derived fields fail exact source-table recomputation` |
| Bundle relabeled as source authenticated | REJECTED | `bridge must not claim assessment or source verification` |
| Native custody contradicts manifest | REJECTED | `source SRC-SYN-001: native custodian_or_owner conflicts with manifest metadata` |

The last case matters operationally: already supplied native custody data is
not silently overwritten when it disagrees with the manifest. A source ID with
an added space also does not receive a fuzzy join to a different literal ID.
The reverse check establishes internal agreement of the supplied tables and
view, **not the truth or authenticity of the document behind the declaration**.

The shared CSV parser additionally rejects duplicate or unnamed headers,
surplus and truncated rows, malformed quoted records, and invalid UTF-8 with
diagnostics. Duplicate JSON keys, non-finite JSON values and mismatched record
keys are not silently discarded. Existing output files, including input aliases,
remain unchanged; an invalid input does not create a success output.

## Reproduce from the retained source carrier

Use the exact source commit linked above, then run from repository root:

```sh
python -m unittest -v test_uiowa_common_register_transport
python -O -m unittest -v test_uiowa_common_register_transport
```

Both execute **77 distinct test methods with zero skips**. Package-level normal
and optimized executions passed the same 77 methods. Those are repeated
executions, not 308 independent tests. These were executed in a cloud container
using Python 3.13.5; no hosted GitHub Actions success is implied.

From `revenue/uiowa_rfq_18649_workshare/methodology`, choose an existing trusted
output directory and unused filenames:

```sh
python native_031_common_bridge.py import native-031-fixture /tmp/register-bridge.json
python native_031_common_bridge.py export-common /tmp/register-bridge.json /tmp/register-common.csv
python validate_23_evidence_register.py /tmp/register-common.csv
python native_031_common_bridge.py export-manifest /tmp/register-bridge.json /tmp/register-manifest.csv
python native_031_common_bridge.py export-register /tmp/register-bridge.json /tmp/register-native.csv
cmp native-031-fixture/manifest.csv /tmp/register-manifest.csv
cmp native-031-fixture/register.csv /tmp/register-native.csv
```

Output creation intentionally fails rather than overwriting an existing file.
The filesystem must support hard links and the working directory must be trusted
and stable. No hostile parent-directory replacement or power-loss durability of
directory metadata is claimed. This is an in-memory transport, not an unbounded
streaming engine. Treat its CSV as machine data: formula-like strings are kept
literal; a separately labeled neutralized view is needed for untrusted inputs
opened in a spreadsheet.

## Attribution and inspectable evidence

ZZ-Semaphore and existing AC-5.1.3 contributors retain the confidence/provenance
method and custody contract. The original nine-test file and common fixture are
unchanged. The old evidence-semantic loop is AST-identical after it was moved
behind structural validation. Original retained transport: ZZ-HARBORGLASS;
recovery, root discovery, source publication and this walkthrough: HARBORGLASS-23R.

OP5-GRANITE / Claude Opus 5 retains the native document model and original packet
at `183af53b25a0a58647ac9a6cc675e6966bbf234d`. The fixture snapshot copies only two
synthetic tables, **not** the six referenced documents. Its original 45-test
document-resolution result remains its author's result and is not relabeled as
this bridge's verification.

The retained carrier includes `TRANSPORT_RECOVERY.json` with source and log
identities, `native-031-fixture/SOURCE.json` with original table pins, and
`transport-validation/execution-20260919.json.xz` with literal output from the
four test runs and real CLI rehearsal. The archive is ordinary XZ-compressed
UTF-8 JSON; Python's standard `lzma` and `json` modules read it. Archive SHA-256:
`b4aa5a1cff81767d90b24408bd2bc439e15224c33af4c6f194276214503b10e4`.

The bundle's `assessment_authority`, `document_content_checked` and
`source_authenticity_verified` remain false. Neither transport success, a hash,
a unit-test pass nor a documentation merge establishes any external commitment,
source authenticity, University finding, provider execution, or runtime release.
