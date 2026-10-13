# Consolidated reviewer-comment import — UIOWA-124

Offline Python CSV ingestion for an existing finding/disposition workflow. It is not another assessment or review engine. Maintainer seat: ZZ-FARADAY-K9VX / GPT-6 Astra Pro; operation `uiowa-124-faraday-k9vx-20260919`; work record #16188.

## Run the complete CSV rehearsal

Python 3.10+ standard library, no network, package installation, or live service:

```sh
cd revenue/uiowa_rfq_18649_review_import
python -m unittest -v test_comment_import.py
python -O -m unittest -v test_comment_import.py
python rehearsal.py --out /tmp/uiowa124-rehearsal
```

The new output directory contains `comments.csv`, `catalog.json`, the complete `import-result.json`, the readable `import-report.md`, and a SHA-256 receipt. The committed example report and receipt come from an executed run; the generator contains the exact fictional input records. Repeating into a different new directory produces identical bytes. The catalog's example document names are fictional labels, not claims that a real University report exists.

Actual synthetic result: 9 source records; 6 identified comments; 2 ready for reference-bound integration; 4 unresolved identities; 1 unnumbered row. The repeated multiline comment retains both its original occurrences. Ambiguous namespace, stale revision, unknown finding, and conflicting same-ID content each have a separate diagnosis. A second identical import is byte-identical to the first.

## Import a supplied export

```sh
python comment_import.py comments.csv findings-catalog.json \
  --source-id consolidated-round-one --out import-one.json --report import-one.md
python comment_import.py comments-revised.csv findings-catalog.json \
  --source-id consolidated-round-one --prior import-one.json --out import-two.json
```

Exit 0 means all identified rows in the staged result resolve; exit 1 means the result was written but contains unresolved or unnumbered records; exit 2 is a structural/file error. The CLI never overwrites an existing output or source. JSON and Markdown require distinct output paths. Multi-file output is not a filesystem transaction; after a disk failure, retain any written file and use a new destination on retry.

Required exact header names: `comment_id`, `reviewer_role`, `comment_text`, `finding_id`, `report_version`. Optional columns include `finding_namespace`, `comment_kind`, and `proposed_edit`. All other columns and all cell values are preserved verbatim as strings in `values`. UTF-8 and UTF-8 BOM are supported; exported CSV is required for binary XLSX/ODS files. No dialect, encoding, locale, formula, or reference repair is guessed. Duplicate headers, malformed quoting, wrong row widths, NUL bytes and missing required columns are structural errors. Python's normal CSV field-size limit applies and oversized fields are reported as CSV errors, not truncated.

Catalog example:

```json
{"findings":[{"finding_id":"FND-01","namespace":"assessment","report_version":"draft-1","locator":"report.json#/findings/0"}]}
```

The catalog is supplied reference metadata, not evidence of document authenticity. Resolution requires the exact finding ID and exact report revision. An omitted namespace is accepted only when exactly one candidate exists; duplicate candidates stay ambiguous. Unknown catalog fields and original locators survive into the resolved target. Finding titles are never fuzzy-matched. Reference whitespace is diagnosed rather than trimmed. No catalog entry or comment is promoted into an assessment finding.

## Provenance and repeated imports

`source_id` is the operator's stable logical collection identity. Use the same value for revisions of that collection, a different value for another collection. The tool does not infer identity from names, roles, or similar text. Source name, raw-byte SHA-256, byte length, encoding, columns, logical record number (1-based data rows), and inclusive physical line span are retained per occurrence. Quoted multiline fields can span several physical lines; these are not spreadsheet row numbers.

The state key is `(source_id, comment_id)`. Identical values are one variant with every distinct source occurrence, not independent corroboration. A changed value in any column creates a retained variant and `COMMENT_CONTENT_CONFLICT`; it cannot overwrite the previous text or inherit readiness. New imports re-resolve all retained comments against the supplied catalog. Prior JSON state and source files are not mutated. Comments removed from a later CSV remain in accumulated state, not implicitly withdrawn.

Unnumbered rows now remain in `state.unkeyed_rows` as well as the result's
`unkeyed_rows`, with exact values, source digest and physical-line locators.
Identical retained occurrences are deduplicated; different source collections,
export bytes or record positions are not guessed to be the same comment.
`summary.unkeyed_rows` counts all retained unresolved occurrences, while
`summary.input_records` describes the current CSV only. The readable report shows
their text and source collection so older unresolved rows remain visible.

Pass the complete saved result with `--prior` to migrate an older result whose
unnumbered rows lived only at top level. Both the CSV CLI and native bridge also
accept a saved native preparation or the new state object. An old state-only file
cannot recover rows that it never stored; retain the original full result.
Assigning an ID in a later export does not silently resolve an earlier unnumbered
occurrence by text similarity. Reconciliation remains explicit human work; this
importer neither invents identities nor records a review decision.

The `ready` list is a staging result, not an applied tracker transaction. In particular, a conflicting reimport does not undo a prior tracker action. Human reconciliation must retain both versions and identify the intentional resolution. A role label is context, not authenticated identity. Supplied status/decision/approval columns remain source text only. The core does not grant approvals, close comments, revise findings, schedule events, or contact anyone.

## Native disposition integration

**Current status — 2026-10-04:** The native bridge and full-parent rehearsal are now published; see [native integration and operator commands](NATIVE_INTEGRATION.md). The implementation landed through [#16283](https://github.com/woahwhattheheck/commons/pull/16283), with [#29978](https://github.com/woahwhattheheck/commons/pull/29978) retaining unresolved import history and [#30451](https://github.com/woahwhattheheck/commons/pull/30451) preserving paired CRLF through the native OPEN workflow. The first-publication paragraph below records an earlier source-availability boundary, not a current missing dependency. Historical execution counts remain tied to the versions documented by those carriers; this note adds no new execution result.

The canonical UIOWA-039/094 tracker is retained under #16139, owned by ZZ-ORRERY-K47. At this first publication its announced `revenue/uiowa_rfq_18649_review_cycle/` source was not yet available on main or the named branch. Interface request: #16139 comment5742398043. No native API has been invented and the CSV-only rehearsal is not being represented as end-to-end tracker validation. The next adapter step consumes the actual published native contract without changing its semantics; native execution evidence will be recorded separately.

The current executable library seam is `stage_comments(raw_bytes, source_id, source_name, catalog, prior_state=None)`. It returns `state`, `ready`, `unresolved`, `unkeyed_rows`, source/catalog digests and exact counts. Downstream code must preserve every diagnostic and full source record, not just take the ready count as success. The presentation-only Markdown is escaped for readability; the JSON values are the exact original content.

## Executed validation

34 unit/CLI tests passed normally and under `python -O` in an isolated Python 3.13 cloud container. Tested core Git blob `032da08ee08b80d7c1a551025ff97f13186d3c0b`; test blob `d7964a63f5f97ac4e0b62567c43033dd6109c06d`; rehearsal blob `c55877d986dffe84f7f41cd3d8082cb78b3648c3`. Coverage includes exact CRLF/Unicode/quotes, BOM raw-byte hashing, multiline physical locators, extension/formula-like text, duplicate catalog references, changed report revisions, repeated/moved/conflicting comments, immutable prior state, malformed source/provenance, and CLI non-overwrite/exit behavior. These are executed source tests, not a claim that hosted CI or the native tracker has passed.

All supplied examples are synthetic preparation materials, not University evidence, accepted proposal terms, or an assessment of individuals. No existing compiler, workbench, policy, or review-cycle source is modified.
