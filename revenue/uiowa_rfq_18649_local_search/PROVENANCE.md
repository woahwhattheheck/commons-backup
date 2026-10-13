# Inspect the record, then follow the evidence

This extends Solstice's existing UIOWA-127 component and its original nine tests, not its ranking formula. The additional provenance and exact-ID work is tracked in [issue #16180](https://github.com/woahwhattheheck/commons/issues/16180). Every bundled record is synthetic preparation material, not a finding about the University.

## Reproduce the reviewer flow

From this directory, using Python 3.10 or later and the repository's sibling document-extraction component:

```bash
python evidence_search.py build fixtures/manifest.json review-index.json
python evidence_search.py query review-index.json "vulnerability ownership"
python evidence_search.py query review-index.json "end to end propagation"
python evidence_search.py lookup review-index.json F-002
python evidence_search.py lookup review-index.json E-005
python evidence_search.py query review-index.json "independent review before merge"
python -m unittest discover -v
python -O -m unittest discover -v
```

`build` writes the named output; choose a disposable index path, never an input document. Paths inside the manifest are relative to the manifest's directory, not the current working directory. Search makes no network or model calls. The real-extractor replay test invokes the sibling Python CLI on the supplied TXT fixture; it does not require PDF packages.

The retained corpus produces **27 records and 347 terms**. The executed examples are deliberately small:

| Reviewer question | Expected navigation | What is actually available |
|---|---|---|
| Who is described as handling vulnerability ownership? | `RIS-SEC-01` is the leading lexical hit. | The exact synthetic authority-register entry; not its fictional underlying interview. |
| What supports the propagation observation? | `F-002` leads the lexical results; exact lookup follows its `E-004`, `E-005`, `E-006` links. | Finding and evidence CSV rows with their native confidence, limitation and locations unchanged. |
| Where is independent review mentioned? | `EXTRACT:sample.txt:text-0002`. | The retained extracted passage and separately verified original TXT bytes. |
| Does the packet contain `F002`? | Exact lookup returns `not_found`, exit 1. | No alias is invented for the distinct native ID `F-002`. |

A lexical query such as `F-002` matches word tokens, not an identity: other records can contain `F` or `002`. Use `lookup` to follow links. It preserves spelling, punctuation, whitespace and case exactly. Its result has `retrieval_mode: exact_id` and `score: null`, not a fabricated relevance/confidence number. Missing records return `None` in Python and structured `not_found` JSON from the CLI. Invalid input returns exit 2 with a diagnostic.

## Read the provenance correctly

`record_url` identifies the immutable repository revision of the actual delivered record. CSV links include physical line anchors, including a range when a quoted field spans multiple lines. `record_locator` describes that delivered record; `locator` remains the native location reported for the original evidence. They are not interchangeable.

For example, `E-005` is supported here by line 6 of the delivered evidence CSV, while its native locator remains `row reporting-contract-04`. That fictional original test file is not delivered, so `underlying_source_url` is `null` and `provenance.underlying_status` is `not_included`. The register row is not relabeled as proof that its underlying document was inspected.

Native `synthetic://` references remain in `source_url` for compatibility. Use `record_url` for the actual repository navigation. All supplied samples explicitly retain `synthetic: true`.

The manifest now requires a 40-hex immutable `upstream_ref` and an explicit boolean `synthetic`. Direct CSV/authority snapshots must match `upstream_blob_sha`. Extraction is different: `local_blob_sha` binds the extracted JSON, while `source_local_file` and `upstream_blob_sha` bind the original document. Its reported SHA-256 and byte count must agree with that document for non-error extractions. The checked-in source companion is byte-identical to the upstream TXT fixture.

These are integrity checks, **not publisher authentication or proof that an extraction is semantically correct**. A person supplying a manifest can also supply its digests. The revision field is reported as `declared_immutable_ref`; runtime search does not contact GitHub to authenticate it. The independent replay test executes the real sibling extractor and compares its actual original segments and locators to returned results, rather than assuming the retained JSON is byte-identical to a fresh extraction.

## Consume text without silently changing it

`original` retains the full native CSV/JSON record, including unrecognized extra columns, confidence and limitations. `snippet` remains the compact whitespace-normalized preview for existing consumers. `snippet_exact` adds the matched field, unchanged text slice, start/end offsets, relative highlight ranges and truncation flags. Offsets are Python Unicode code-point indices, not UTF-8 byte or JavaScript UTF-16 offsets. Render stored content as text, not trusted HTML.

If only metadata matches, the exact snippet names `metadata` or `original`; it does not pretend that the term occurred in the observation. Empty/unreadable extraction segments remain `extraction_diagnostic` records with warnings and unchanged empty original text. A missing linked record stays visible in `link_diagnostics` rather than disappearing from a finding.

## Compatibility and limits

Existing search functions, compact previews, stable record IDs, original fixtures and ranking formula are retained. Extra native fields and warnings become searchable, so document frequencies and numerical relevance scores can change after rebuilding. This is not evidence re-scoring. The corpus and its original nine tests are unchanged.

Rebuild old indexes from the updated manifest to obtain provenance fields. An old index is explicitly labeled `legacy_unbound`; it is not retroactively called verified. New indexes include a SHA-256 content digest and detect unintended changes before search or exact lookup. That digest is likewise not a signature.

Malformed CSV width/headers, duplicate JSON keys, nonfinite JSON, incompatible extraction shape, missing provenance, source-byte mismatch and paths escaping the manifest directory are rejected. The implementation bounds files to 50 MiB, a manifest to 100 sources, an index to 10,000 records, queries to 2,000 characters and result limits to 1–100. These are local processing limits, not a production-scale performance claim.

The receipt records **47 passing tests normally and under `python -O`**: nine retained tests, twenty provenance regressions, ten real-parent/CLI regressions and eight exact-ID regressions. Local execution is not a hosted-CI, external audit or live-University validation claim. No match means only no match in the indexed packet; missing evidence never becomes proof of absence.
