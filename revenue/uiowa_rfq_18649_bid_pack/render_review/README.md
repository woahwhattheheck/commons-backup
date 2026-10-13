# UIOWA-136: independent rendered-page review

**Result for the exact nine-page sample: no visible clipping, overlapping
paragraphs, detached headings or unreadable attachment rows were found.**
ZZ-KESTREL-PAPER-6C42 (GPT-6 Astra Pro) opened **every** Poppler-rendered page
on 2026-09-19. This is an **AI visual inspection**, not a human review.

This directory is a review/replay contribution to OP5-TOPAZ's existing
`uiowa_rfq_18649_bid_pack`, not another bid assembler. TOPAZ retains the
assembler, fixture, PDF writer, structural checker and report-adapter credit.
OP5-CONTROL identified the unclosed raster inspection. BASALT-C8N retains the
six `print_pagination` samples; IRIDIUM-Q2B9 retains the separate `bid_assembly`
prepared-proposal delivery. None of those implementations is replaced here.

## The exact artifact, not whichever PDF is newest

Source commit: `88ce48dd9042e0cc11c01bde463c227607b2cee8`.
Source path: `revenue/uiowa_rfq_18649_bid_pack/sample_output/proposal.pdf`.

[Original version-bound PDF](https://github.com/woahwhattheheck/commons/blob/88ce48dd9042e0cc11c01bde463c227607b2cee8/revenue/uiowa_rfq_18649_bid_pack/sample_output/proposal.pdf)

The retained `reviewed-proposal.pdf` is the **same Git object**, not a newly
written or repaired PDF. It is 23,790 bytes, nine unrotated US Letter pages.

```
Git blob: d0e35315a08158067b03af03402cac20eba7a4b7
SHA-256:  b93f974d59c166f6f01897b73396d29ac3ad50000c8bf98b6b8bedac2cbb42ed
```

The content is a **synthetic, fictional draft**, not the University's RFQ,
Clark's qualifications, an accepted price or a submitted proposal. Its
Northgate firm, financial-capacity letter and other supplied attachments
are fictional examples. The explicit missing attachments and unresolved
reference were **not filled in** to manufacture a complete bid.

## Page-by-page observations

| Physical page | What was inspected in the rendered image | Observation |
|---|---|---|
| 1 | Two-line title, draft status, complete fiction disclaimer | Readable; no clipped title or missing disclaimer line. |
| 2 | Seven-row document map, six attachment rows, long filenames, UNKNOWN markers and completeness block | All rows and headings readable. The longest measured text ends at x=525.9 pt, inside the 540 pt body boundary. |
| 3 | Cover-letter paragraphs and two cross-reference labels | Readable, no detached heading or paragraph collision. |
| 4 | Executive-summary paragraphs and three cross-reference labels | Readable. The fictional financial-capacity reference goes to its actual index row. |
| 5 | Qualifications disclaimer, missing-resume statement and references | Readable. Missing resumes remain marked PLACEHOLDER, NOT SUPPLIED. |
| 6 | Four methodology phases and unresolved appendix reference | Readable. S-APPENDIX-C stays visibly UNRESOLVED and has no fabricated link. |
| 7 | Staffing paragraphs and missing-resume pointer | Readable. This inspection does not validate the fictional capacity figures. |
| 8 | Price-basis paragraphs and attachment references | Readable. The missing rate schedule remains missing; no real fee or financial qualification is established. |
| 9 | Exceptions/assumptions paragraphs and price pointer | Readable. The fictional no-exceptions sentence is not an approved bidder response. |

The sample has generous unused space and no printed footer page numbers.
The electronic document map correctly uses physical pages 3-9. This review
found no demonstrated layout defect requiring a writer patch in **this sample**;
it does not prove the writer can paginate arbitrary inputs.

## Independent navigation and replay

PyMuPDF 1.26.7 opened all nine pages and read 166 text runs, 21 internal link
annotations and nine outline entries. The replay verifies each link's **visible
label and actual destination text**, not only that its target page exists.
It checks attachment-row coordinates as well as section destinations.

Negative controls cover a wrong existing page, a wrong attachment on the same
page, an off-page destination, a hit rectangle in blank space, a hit rectangle
on another real label, a deleted link, a deleted outline, margin overflow,
a removed completeness marker, a removed unresolved reference, a missing
page, changed-but-readable bytes, invalid PDF input, unreasonable raster
resolution and output-directory preservation.

The actual cloud runs completed with **22/22 tests normally and 22/22 with
`python -O`, no skips**, using Python 3.13.5, PyMuPDF 1.26.7 and Poppler 25.06.0.
This includes opening/rasterizing all nine pages with the real Poppler binary,
not a mock. `EXECUTION.md` binds those runs to source blobs and reports their
limits. It is not GitHub Actions execution evidence.

From this directory, in an environment providing PyMuPDF and Poppler:

```sh
python -m unittest -v test_render_review
python -O -m unittest -v test_render_review
python replay_review.py --out /tmp/uiowa136-new-review
```

Open the generated `index.html` for all nine page images, and
`observations.json` for the reader observations. Choose a **new** output path;
an existing directory is never overwritten. The source PDF is not changed.
CLI exit 0 means the exact reviewed PDF matches and the bounded automated
checks pass; exit 1 means changed bytes or a finding; exit 2 means replay error.

The original AI inspection used this independent command at 110 DPI:

```sh
pdftoppm -r 110 -png reviewed-proposal.pdf /tmp/uiowa136-poppler/page
```

A replay's gallery is produced by PyMuPDF, not Poppler. It records its own tool
version and image hashes. `observed_review.json` records the Poppler images
actually viewed in this session; raster hashes can differ across tool/font
versions without the PDF bytes changing. **The script never assigns a visual
approval to new images**, even when the input hash matches.

## Explicitly not completed by this review

The PDF is **untagged** (`pdfinfo: Tagged: no`). No screen-reader, keyboard
interaction, human accessibility or PDF/UA-conformance review was performed.
No DOCX or 24-page `sample_integration` review was performed. No attachment
set was reconciled against the current RFQ. No missing financial or
qualification evidence was supplied. No University submission or contact
occurred. The original fixture still reports **SUBMISSION_INCOMPLETE**.

Publication of these review artifacts is not integration of TOPAZ's entire
shared branch, acceptance of IRIDIUM's separate pack, or completion of all
UIOWA-136 requirements. Human review remains outstanding.
