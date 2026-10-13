# UIOWA-127 — provenance-preserving local evidence search

A deterministic, offline search component over **already-merged synthetic RFQ 18649 preparation records**. It indexes source metadata, traceability observations, findings, and locator-preserving extracted text without an external model or network service at runtime.

The retained component is Solstice's [PR #16212](https://github.com/woahwhattheheck/commons/pull/16212). The complementary [provenance and exact-ID repair](PROVENANCE.md) preserves its original nine tests and ranking formula, verifies supplied source bytes, and distinguishes delivered record citations from absent underlying documents.

## Provenance contract

Every normalized record carries:

- its stable record ID and record type;
- the exact upstream repository path and Git blob SHA used to prepare the fixture;
- its native source locator;
- the native source reference when one exists (`synthetic://…` for workshare authority records), otherwise the GitHub file URL;
- linked IDs for finding → evidence relationships.

The committed fixture manifest pins upstream blob SHAs and immutable revisions. Manifest loading verifies local bytes, and results add `record_url`, physical CSV row locations, original content, exact snippet offsets and explicit missing-source diagnostics. Integrity checks are not publisher authentication. Search never fills a missing record with an answer.

## Corpus used by the worked example

- 12 source-metadata records from `uiowa_rfq_18649_workshare/fixtures/synthetic_authority.json`;
- 8 observation/evidence records from `uiowa_rfq_18649_traceability_rehearsal/evidence.csv`;
- 3 findings from `uiowa_rfq_18649_traceability_rehearsal/findings.csv`;
- 4 retained extraction segments prepared from the merged document-extraction sample text. The replay suite separately executes the real extractor and checks its actual returned segments and locators.

Total: **27 records**. All are synthetic preparation artifacts, not University of Iowa findings.

## Ranking

The search is transparent lexical retrieval: Unicode case-folded word tokens; each matched term contributes `idf(term) × (1 + ln(tf))`; an exact normalized query phrase adds 1.0; ties break by stable record ID. No opaque embeddings, personalisation, model inference, or current clock enters ranking. Native extra fields and source warnings are also searchable after rebuilding.

Exact-ID `lookup` is separate from lexical `query`: it never tokenizes or aliases the requested identity and returns no relevance score.

## Run

```bash
python3 evidence_search.py build fixtures/manifest.json review-index.json
python3 evidence_search.py query review-index.json "vulnerability ownership"
python3 evidence_search.py query review-index.json "end to end propagation"
python3 evidence_search.py lookup review-index.json F-002
python3 evidence_search.py lookup review-index.json E-005
python3 evidence_search.py trace review-index.json F-002
python3 evidence_search.py query review-index.json "independent review before merge"
python3 -m unittest discover -v
python3 -O -m unittest discover -v
```

Choose a disposable output path; `build` writes that named file. See [PROVENANCE.md](PROVENANCE.md) for the exact-source reviewer flow, fields, migration rules and execution boundaries. `examples/question-walkthrough.md` remains the original worked flow; rebuild its legacy index to add the new provenance fields.

## Follow a finding's evidence in one operation

`trace` expands exact outgoing `linked_ids`, starting with the requested record.
For the published corpus, `trace review-index.json F-002` returns the finding and
E-004, E-005 and E-006 together. Each returned record has the same source locator,
original content, snippet, digest status and missing-underlying-document warnings
as an individual exact lookup. IDs are never tokenized for identity matching,
case-folded, aliased or replaced by a lexical search hit.

Expansion is breadth-first with sorted linked IDs. Shared references appear once;
cycles terminate without dropping their recorded edges. The default limit is 25
records including the root; use `--max-records` from 1 through 100. A bounded result
retains `unexpanded_record_ids` and `not_expanded` edges rather than claiming a
complete chain. Missing targets remain in `missing_linked_ids` and `missing` edges.
Only outgoing declared links are followed; an index cannot reveal absent or
undeclared relationships or fetch an underlying source document.

Exit 0 means the reachable declared record chain was returned completely within
the index. Exit 1 means a missing root, missing linked record or truncation; all
available data and diagnostics still go to stdout. Invalid input exits 2.
The reusable API is `trace(index, record_id, max_records=25)`; consumers should
inspect `complete_in_index`, both unresolved-ID lists and each record's provenance.
Completeness here describes navigation, not evidence sufficiency or authenticity.

## Scope boundary

This is navigation over supplied evidence, not an answer generator. A high-ranked hit is not a finding, a confidence score, or proof that an observed practice exists outside the referenced synthetic record. No result means only that the indexed packet did not match the query.
