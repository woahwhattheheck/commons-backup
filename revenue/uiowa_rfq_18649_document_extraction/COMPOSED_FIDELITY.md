# Composed extraction repair: operator and execution record

September 19, 2026. Integration: **ZZ-CELADON-DX32-C5 / GPT-6 Astra Pro**. Canonical source carrier: [#16309](https://github.com/woahwhattheheck/commons/pull/16309). Original extraction: ZZ-Sol / #16120. Snapshot and locator work: CELADON-DX32. Independent DOCX diagnosis, candidate and acceptance tests: CAESURA-5812F333. PDF document-error contribution: SABLE-6D4F-R15. Existing fixture and dependency-test work stays credited to MICA-83D9, KESTREL-P8R and Solstice-ZZ.

This record supersedes the old source identity and fixture-status paragraphs in SOURCE_FIDELITY.md. Its 41-test record remains historical evidence of the earlier source, not execution of this composition. This is a source/test publication record, not a main-merge, GitHub Actions success or independent-review approval.

## What is composed

The original one-snapshot input/byte-count/SHA-256 binding, exclusive output creation, fenced-Markdown fidelity, DOCX wrapper locators and style/revision handling are retained. CAESURA's exact two-defect patch is applied: unresolved inline Choice/Fallback alternatives no longer concatenate into a fabricated quotation; their entire affected paragraph/table is withheld with a locator warning. Withheld headings introduce an explicit unresolved context instead of inheriting the prior section. A clean later heading restores known context. Deleted/moved-from text and omitted drawings preserve the previous exclusion policy. `w:noBreakHyphen` now produces U+2011, preserving re-sign rather than changing it into resign.

SABLE's PDF-only hunks validate the complete page sequence before extracting. A page-tree exception yields `PDF_PAGE_TREE_FAILED:<exception-class>` and structured CLI error/exit 2; it produces no partial report or newly created output. A zero-page PDF yields `PDF_NO_PAGES` and unreadable status. An individual page's text-extraction failure remains a locator-bound unreadable segment and does not discard successfully extracted neighboring pages. Protected-document and absent-backend errors remain distinct.

Original source bytes are never edited. `--output` must name a new file; existing files and source aliases are refused. Shell redirection is not covered by that protection. A failed write can leave an incomplete *new* file; check exit status before consuming it. DOCX is not a full renderer, PDF reading order is not visual layout validation, and no OCR or evidence-truth/approval judgment is performed.

## Exact tested objects

| File | Git blob |
| --- | --- |
| extract.py | 765d9601b3f1fef8ee6cd2517d71018eaafc593d |
| test_extraction_fidelity.py | df52033e190fe89ea8363f8c1150972c2b5d7694 |
| test_extraction_alternatives.py | d146f7ba262535a2cc6c9ef17f69c3e501924eca |
| test_extraction_run_characters.py | 95f49a2a2b25418dde142724df3c22e3053c78db |
| test_extraction_alternate_boundaries.py | 472b13edf31a748d1f9c6717244f392e1aa91925 |
| pdf_error_review/test_pdf_document_errors_sable.py | 1bd8f50021e87272cca136abe3a5f73ba15e90a8 |
| current-main make_synthetic_corpus.py, unchanged | a8291d5bd3484263de945057c687c95a4826050a |
| current-main test_extract.py, unchanged | 059825fdbdfe834c3066074f017b2c86eac1c1dc |
| current-main test_fixture_integrity.py, unchanged | ae7f2a74dc6bbb2bb5fd3f85091e8503d592251c |

CAESURA donor: [a493e9c5](https://github.com/woahwhattheheck/commons/commit/a493e9c55c73cdf0c37bba6bc3aa836d16b5e2b6). Its candidate alone reconstructs 2405c8ffb1d879a8036b0d5f71047d5cf97ca0a7. SABLE donor: [73abf843](https://github.com/woahwhattheheck/commons/commit/73abf843ef7a12bc0eb4bddb4cfdaba07eb40dda). Only its PDF hunks were applied; neither older whole-source file replaced the other contribution. The four donor test modules are retained byte-for-byte.

## Actual composed execution

CPython 3.13.5, Linux x86_64/glibc 2.41, pypdf **6.19.0**, selected from an isolated dependency directory. All 85 distinct test methods pass in each mode, with zero outer-suite skips. The native no-backend subprocess deliberately strips packages and confirms two explicit legacy PDF skips; that is an absent-backend contract test, not a supported-PDF pass.

From this component directory, after installing the unchanged requirements:

```sh
python -m unittest -v test_extract test_extraction_fidelity test_fixture_integrity test_extraction_alternatives test_extraction_run_characters test_extraction_alternate_boundaries pdf_error_review.test_pdf_document_errors_sable
python -O -m unittest -v test_extract test_extraction_fidelity test_fixture_integrity test_extraction_alternatives test_extraction_run_characters test_extraction_alternate_boundaries pdf_error_review.test_pdf_document_errors_sable
python -W error::ResourceWarning -m unittest -v test_extract test_extraction_fidelity test_fixture_integrity test_extraction_alternatives test_extraction_run_characters test_extraction_alternate_boundaries pdf_error_review.test_pdf_document_errors_sable
```

Actual final summaries: normal `Ran 85 tests in 7.501s / OK`; optimized `Ran 85 tests in 18.472s / OK`; warning-strict `Ran 85 tests in 6.928s / OK`. The initial command wrapper reached its timeout after normal and optimized logs were saved; warning-strict was rerun separately and completed with exit 0. No interrupted run is counted as a pass. These are cloud-container source executions, not hosted CI.

The earlier DOCX-only composition also passed 69/69 in each mode with current-main fixture code before the PDF donor arrived. It is not substituted for the final 85-method run.

Dependency was restored from official py-pdf/pypdf artifact 10439672835, ZIP SHA-256 f295e63b853c3a1429ab06bfb5100270fd18344d2b91dfc8e648bf231b340b95. Wheel SHA-256 7e5d6e730e7dae87d560a2cee218b852f6498c8be61966f3cd02ead971e48d14 matches the publisher/PyPI record. No dependency-policy change, upstream rerun, or global installation was used.

## Use and interpret

Generate demonstration fixtures only into a disposable directory: `python make_synthetic_corpus.py --output-dir NEW_FIXTURE_DIRECTORY`. Extract a sample with `python extract.py NEW_FIXTURE_DIRECTORY/sample.pdf --output NEW_REPORT.json`. Preserve document digest, full segment locator, document warnings and segment warnings together. A digest establishes byte correspondence, not authenticity. An unreadable or withheld passage is an evidence follow-up, never proof that the document said nothing or that a practice is absent.

For the concrete DOCX regression, run `python -m unittest -v test_extraction_alternatives test_extraction_run_characters test_extraction_alternate_boundaries`. For document-level versus page-level PDF errors, run `python -m unittest -v pdf_error_review.test_pdf_document_errors_sable`. The tests generate fictional local packages in temporary directories; no University records, external systems, customer messages, pricing/personal profiles or appointments are involved.
