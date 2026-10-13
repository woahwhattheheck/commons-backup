# University of Iowa RFQ 18649 — locator-preserving document extraction

Operation: **UIOWA-032**

This additive tool turns representative PDF, DOCX, and plain-text evidence artifacts into
searchable JSON while preserving a source locator that a report writer can follow back to
the original artifact. It is designed for assessment-production support, not for scoring,
authority, OCR, or University submission.

## What it preserves

- **PDF:** one-based page number plus block number.
- **DOCX:** heading path plus paragraph/table index. DOCX files do not contain reliable
  rendered page numbers, so the adapter does not invent them.
- **TXT/Markdown:** heading path plus one-based line range.
- **Tables:** DOCX tables are emitted separately and linearized row-major with ` | `
  separators, with an explicit warning.
- **Unreadable passages:** empty/image-only PDF pages produce an `unreadable` segment
  and an OCR-required warning instead of silent omission or fabricated text.

Every result also carries the input byte count and SHA-256 so the locator can be tied to
the exact source bytes.

## Install

Python 3.11+ and `pypdf` are required for PDF extraction:

```bash
python -m pip install -r requirements.txt
```

DOCX and plain-text extraction use the standard library.

## Run

```bash
python make_synthetic_corpus.py
python extract.py fixtures/sample.pdf > /tmp/sample-pdf.json
python extract.py fixtures/sample.docx > /tmp/sample-docx.json
python extract.py fixtures/sample.txt > /tmp/sample-text.json
```

The generated corpus is deliberately synthetic and safe for the public repository.

### Extract a whole evidence folder

```bash
python batch.py /path/to/evidence /tmp/evidence-extraction-new
```

The batch command recursively discovers PDF, DOCX, TXT and Markdown files and
calls the existing extractor for each source. It makes no network calls and
installs no dependencies. PDF support uses the same optional installed `pypdf`
package as the single-document command; a failed document does not stop the
remaining sources from being processed.

Reports retain source-relative paths: `notes/team.md` becomes
`reports/notes/team.md/extraction.json`. Keeping the original filename, including
its extension, prevents same-stem documents from replacing each other. Every
report retains the native segment locators and source byte digest. A parser
failure produces that source's structured error report, with its source digest
left unknown rather than fabricated.

`index.json` is written last. It records per-source status, source byte count
and SHA-256 when available, output paths and SHA-256, segment/warning counts,
the extractor identity, and discovery coverage. Treat a missing index as an
interrupted or failed output operation; already written reports are retained.
A completed index may still describe an incomplete extraction.

| Batch status | Meaning | Exit |
| --- | --- | ---: |
| `ok` | All discovered supported documents extracted without warnings | 0 |
| `partial` | Reports contain native extraction warnings; all documents remain readable | 0 |
| `incomplete` | At least one unreadable/error document, scan error, untraversed directory link, or no supported documents | 2 |

Unsupported extensions are counted and omitted; no source contents are guessed
from an extension. Directory symlinks are listed but never traversed. File
symlinks use the existing extractor's resolution behavior and are marked in the
index; hashes bind the actual source bytes read. Directory scan errors remain
visible while other readable branches continue.

The output directory must be new. Existing outputs and all source files remain
unchanged. Discovery finishes before output creation, so an output folder inside
the source cannot join the same run. Directory enumeration is not an atomic
snapshot: files added after discovery are for a later run, and the native reader
reports ordinary edits observed while reading each document.

The real restored roadmap documentation folder was run through this command:
three Markdown documents, including its nested generated roadmap, produced
three readable extraction reports and the final index. No assessment ratings
or evidence-authority claims are derived by the batch command.

## Output contract

```json
{
  "schema": "uiowa.document-extraction.v1",
  "document": {
    "name": "sample.pdf",
    "type": "pdf",
    "bytes": 0,
    "sha256": "..."
  },
  "status": "ok",
  "warnings": [],
  "segments": [
    {
      "segment_id": "pdf-0001",
      "kind": "page_text",
      "locator": "page 1, block 1",
      "text": "...",
      "heading_path": [],
      "warnings": []
    }
  ]
}
```

`status` is `ok`, `partial`, `unreadable`, or `error`. A caller should retain both the
document SHA-256 and the segment locator when quoting or synthesizing findings.

## Acceptance

```bash
python make_synthetic_corpus.py
python -m unittest -v test_extract.py
python extract.py fixtures/sample.pdf
python extract.py fixtures/sample.docx
python extract.py fixtures/sample.txt
```

Acceptance requires:

1. PDF quotations can be traced to the correct one-based page.
2. DOCX quotations can be traced to a heading path and paragraph/table index.
3. plain text quotations can be traced to exact line ranges.
4. tables are explicit segments rather than flattened invisibly into adjacent prose.
5. image-only/empty PDF pages are flagged as unreadable and OCR-required.
6. the exact source bytes are bound by SHA-256.

## Scope and limits

This adapter performs **text extraction, not OCR**. Scanned/image-only PDFs are therefore
reported as requiring OCR. Complex PDFs can have reading-order limitations in their text
layer; page locators remain valid even when layout reconstruction is imperfect. DOCX page
numbers depend on a rendering engine and are not stable in the OOXML package, so the
portable locator is the document heading path plus paragraph/table index.

The tool does not determine evidence truth, maturity, compliance, acceptance, or
recommendations. It does not contact the University, Clark's Consulting, or any external
provider and does not write private assessment evidence to the repository.
