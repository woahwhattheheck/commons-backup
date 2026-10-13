# S139 method PDF validation

Generated from the exact frozen source at commit `6feb9c0566b8f203c5d1a2ffdfbf1cb6d11be055` for candidate `S139-fleet-20260908-75897709`.

## Exact binding

- `S139-method.md`: 6,072 bytes, SHA-256 `75e774c94af52fe339f6cfbbe3fcbb5cd50209d25a93cbab211a586ad76671fa`
- `build_method_pdf.py`: 4,489 bytes, SHA-256 `c68467d1a3fe2d8d60237ea081a3a45dd807fe505862b333de1323ec34a39453`
- generated `method.pdf`: 7,596 bytes, SHA-256 `4ece1ee204ef33b93b76cdeb009733dabc67c69783fb6dc5bbe845ab62c90502`
- frozen candidate source result: SHA-256 `758977095f8f34263bbcd9ed043ac4ab7943f04f65fae530c78ee64787c34f8f`
- frozen manifest: `FROZEN-CANDIDATE-20260908.json`, Git blob `d07109f76cd50b7befaa720356a9cb686fd7f6ce`

## Validation executed

The frozen generator produced exactly two A4 pages. Both pages were rendered at 200 dpi and visually inspected. The title, body, sources, footers, and page numbers are readable; there is no clipped text, overlap, black square, or broken glyph. A second parity check rendered both pages with `pdftoppm` and PDFium; the approximately 0.10% differing pixels are text antialiasing, not missing content.

Normalized extracted PDF text matches the reviewed Markdown exactly: 5,726 visible characters. The document contains 769 words and no word box extends outside either page. Both HTTPS source annotations are present. Structural preflight reports an openable, unencrypted, nonscanned PDF with no XFA, form, or attachment. Metadata identifies the title, author, and ROADEF method-description subject.

## Held evidence

- PDF: Library `ROADEF-S139-method-held-20260908.pdf`, file `file_00000000d61881f5aa1a5aff234ce8af`
- complete source/render/preflight package: Library `ROADEF-S139-method-held-20260908.zip`, file `file_00000000e8b881f58fad397e108a7512`, 998,363 bytes, SHA-256 `a75a75a29f2234c6456f1e17edf84433019f87cc47f9216ab52da312260e7c5f`

The package contains the exact reviewed source and generator, final PDF, both 200-dpi renders, extracted text, structural and renderer-parity records, source binding, and a complete per-file SHA-256 manifest. An independent unzip/readback verified every manifest row, the two-page count, and byte-identical rerenders.

## Scope

This is documentation generation and validation only. The existing S139 Gmail draft and attachment were not opened, changed, replaced, or sent. No solver, checker, benchmark, Docker runtime, organizer contact, or qualification submission occurred. The PDF remains held until a later explicit release.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
