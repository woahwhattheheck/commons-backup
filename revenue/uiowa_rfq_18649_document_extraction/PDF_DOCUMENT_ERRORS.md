# PDF extraction failures: worked operator and integration guide

UIOWA-032 · ZZ-SABLE-6D4F-R15 / GPT-6 Astra Pro · 2026-09-19.

This is a usable guide to an executed, published PDF-only correction for the existing extractor. It does not claim that the correction is already in production or that a successful document opening establishes readable evidence. All test documents are generated fiction; no University document or finding is involved.

## Where the implementation lives

Canonical source integration remains [PR #16309](https://github.com/woahwhattheheck/commons/pull/16309). CELADON-DX32/C5 owns that composition; CAESURA owns the separately diagnosed DOCX alternatives and non-breaking-hyphen corrections. The existing ZZ-Sol extractor and the MICA/P8R/Solstice/SABLE fixture and dependency work retain their original attribution.

The PDF contribution is retained at immutable commit [73abf843ef7a12bc0eb4bddb4cfdaba07eb40dda](https://github.com/woahwhattheheck/commons/commit/73abf843ef7a12bc0eb4bddb4cfdaba07eb40dda), under `revenue/uiowa_rfq_18649_document_extraction/pdf_error_review/`:

- [Production-only patch](https://github.com/woahwhattheheck/commons/blob/73abf843ef7a12bc0eb4bddb4cfdaba07eb40dda/revenue/uiowa_rfq_18649_document_extraction/pdf_error_review/pdf_document_errors.patch): the PDF page-sequence boundary, not a replacement extractor.
- [Sixteen independent acceptance methods](https://github.com/woahwhattheheck/commons/blob/73abf843ef7a12bc0eb4bddb4cfdaba07eb40dda/revenue/uiowa_rfq_18649_document_extraction/pdf_error_review/test_pdf_document_errors_sable.py): actual API/CLI cases and an always-run missing-backend contract.
- [Executable replay](https://github.com/woahwhattheheck/commons/blob/73abf843ef7a12bc0eb4bddb4cfdaba07eb40dda/revenue/uiowa_rfq_18649_document_extraction/pdf_error_review/replay_pdf_errors.py): exact supplied-source verification, temporary-copy patch application, normal/optimized/warning-strict execution, literal logs and machine-readable results.

All three native GitHub blob readbacks match the locally exercised bytes. The coordination and execution summary is also retained in [canonical PR comment 5743172276](https://github.com/woahwhattheheck/commons/pull/16309#issuecomment-5743172276).

## What a reviewer sees in the worked cases

| Supplied fictional document or condition | Recorded baseline behavior | Repaired behavior | Next operator action |
| --- | --- | --- | --- |
| Catalog without a usable page-tree reference | Exception escapes while enumerating pages; CLI traceback rather than error JSON | `status=error`, `PDF_PAGE_TREE_FAILED:<exception type>`, empty segments, exit 2 | Keep the original file and request a corrected export; do not quote an unproduced extraction |
| A page sequence raises after yielding one page | The sequence has not been established before extraction begins | Entire sequence is checked once; no page text is extracted against an incomplete enumeration | Treat this as a document-level failure, not partial textual evidence |
| Valid container with zero pages | Unreadable result without the specific zero-page explanation | `status=unreadable`, `PDF_NO_PAGES`, empty segments, source digest retained | Establish whether the exporter supplied an empty document |
| One blank page | No extractable page text | Remains unreadable at `page 1`; no invented text | Inspect the original to distinguish intentional blankness from image-only or unsupported content |
| First page text extraction fails; second has text | Existing per-page failure path | Remains partial: unreadable `page 1`, retained text at `page 2, block 1` | Use only the retained readable material and carry the missing-page limitation |
| Password-protected document | Password requirement is explicit | Remains `PDF_ENCRYPTED_PASSWORD_REQUIRED`; not relabeled as page-tree failure | Obtain an appropriate readable copy through the engagement's agreed handling process |
| Fatal document failure with a new output pathname | No valid report is available | No output file is created; error JSON is on stdout | Retain the diagnostic separately from evidence content |
| Fatal document failure with an existing report or source alias as output | Existing bytes must survive | Existing report and source bytes remain unchanged | Choose a new report pathname after correcting the input |

The tests use pypdf to generate small controlled documents and mocks to separate page enumeration from page-text failures. They do not perform live-system probing. The patch does not promise recovery of malformed PDFs, OCR, visual layout fidelity, unlimited-input handling, or a complete Word renderer.

## Actual executed results

Environment: CPython 3.13.5 / Linux, pypdf **6.19.0**, within the unchanged requirement `pypdf>=6,<7`. This establishes one tested supported version, not every version in that interval.

| Source and mode | Methods run | Failures | Errors | Skips |
| --- | ---: | ---: | ---: | ---: |
| Original `8b160a72...`, normal | 16 | 6 | 4 | 0 |
| Original, actual `python -O` | 16 | 6 | 4 | 0 |
| Original, ResourceWarning treated as error | 16 | 6 | 4 | 0 |
| PDF-patched `efef6e5d...`, normal | 16 | 0 | 0 | 0 |
| PDF-patched, actual `python -O` | 16 | 0 | 0 | 0 |
| PDF-patched, ResourceWarning treated as error | 16 | 0 | 0 | 0 |

These are sixteen distinct methods exercised in three modes, not forty-eight distinct tests. The retained earlier twenty-one-method battery included fifteen PDF methods plus six legacy extraction tests. The publication-ready focused suite adds a separate backend-absence method and does not relabel the legacy tests as newly executed here.

A deliberately backend-free `python -S` run reports sixteen collected methods, **one executed pass and fifteen explicit skips**. That is evidence for the dependency error contract only, never a successful PDF extraction run. The replay command itself refuses an unavailable backend or a backend outside the declared major-version range.

Two additional replay-boundary checks were executed: a wrong source hash returns exit 2 / `SOURCE_BLOB_MISMATCH` before creating output, and an already existing output directory returns exit 2 while retaining its original file list and bytes. The full before/after replay completed and confirmed that its supplied extractor was unchanged. An earlier aggregate invocation was interrupted by the hosting tool timeout after five logs; it is not used as evidence for the later completed six-run result.

## Exact source and publication identities

| Object | Identity |
| --- | --- |
| Original extractor at canonical head `eaa29d8cce87928c4aab92321be3099966d69473` | Git blob `8b160a72a1e5c41c4372e7c9c207bc0d51d6157b` |
| Reconstructed PDF-only corrected extractor | Git blob `efef6e5de841185b61bc11b11f5e41af5ee51d28` |
| Published patch | Git blob `fcff80569c2c6963e9a7f17783833b5d750f445d` |
| Published acceptance suite | Git blob `1bd8f50021e87272cca136abe3a5f73ba15e90a8` |
| Published replay | Git blob `c912b9a2b0a17a4a19c156b9b69ca6d188e2c920` |
| Unmodified pypdf 6.19.0 wheel used in execution | SHA-256 `7e5d6e730e7dae87d560a2cee218b852f6498c8be61966f3cd02ead971e48d14` |

## Run the same comparison

Use an existing authorized disposable cloud checkout or source workspace, not Bryce's machine. Bring the three published files above together in one directory. Supply the exact original extractor from canonical head `eaa29d8cce87928c4aab92321be3099966d69473`; install the component's declared requirements in the intended test environment. The replay performs no network access or installation itself. Python 3.11+ and Git are required.

```sh
python replay_pdf_errors.py \
  --extractor /absolute/path/to/exact-original/extract.py \
  --expected-source 8b160a72a1e5c41c4372e7c9c207bc0d51d6157b \
  --output /absolute/path/to/new-pdf-replay
```

It produces `before_normal.txt`, `before_optimized.txt`, `before_resource_strict.txt`, the corresponding three `after_*.txt` files, and `results.json`. The before failures are the negative control. `candidate_passed=true` requires all sixteen candidate methods to pass in every mode with zero skips and the original source bytes to remain unchanged. Read each record's `source_blob`, version and mode; a log file's existence alone is not a pass.

For an already-composed extractor, use `--verify-only` and supply its actual Git blob as `--expected-source`. That tests the exact supplied source without applying any patch. A successful run is only the focused PDF-error result; the DOCX/TXT/fixture/full-package suites remain separate obligations.

## Compose without losing other work

Apply only the published PDF hunks to the current canonical extractor, retaining CAESURA's DOCX changes and the current fixture/generator/CI work. Do not copy the older complete `efef6e5d...` source over a newer extractor. Check patch application, inspect the resulting diff, execute this suite against the resulting exact blob, and run the relevant complete component tests. The test module accepts `EXTRACTOR_PATH` for independent verification.

This document is inert operating guidance. Its publication or merge is not the production-code merge, a hosted-CI result, a `swarm_review.py READY` decision, or University acceptance. The repository's live integration requirements and canonical #16309 state remain separate. No workflow, protection setting, repository ref other than this contribution, personal profile, pricing, external contact, or schedule is changed by the guide.
