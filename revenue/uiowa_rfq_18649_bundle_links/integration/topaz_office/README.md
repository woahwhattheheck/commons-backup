# Published office-file replay (UIOWA-119 supporting UIOWA-136)

`proposal.docx` is the **unchanged published synthetic fixture** from OP5-TOPAZ's
UIOWA-136 bid assembler, not a new proposal or competing assembler. Its exact
original Git blob is `c018316991cb99d5692f2659f7e07ecbc1c70147` (6,261 bytes).
Original path: `revenue/uiowa_rfq_18649_bid_pack/sample_output/proposal.docx`;
observed on `claude/multi-agent-slack-demo-4ikzfs`. The byte identity, not that
moving branch, binds this review. No original assembler files are edited.

## Executed result

The actual file opened with LibreOffice 25.2.3.2 and rendered into **nine pages**.
All nine page images were visually inspected: no clipping, overlap or missing
glyphs was observed; long monospace attachment names wrap and remain readable.
Its **16 bookmarks / 21 internal links** survive the office-to-PDF path. For all
21 annotations, the source label matches and the destination lands at the
intended heading or attachment-index row (maximum vertical difference 0.017998
points). The replay passed normally and under real `python -O`.

Four deliberate changes were rejected in both modes: changed source bytes,
a link pointing to a wrong existing page, a removed link, and a removed page.
The wrong-destination case produces 20/21 rather than accepting a valid-but-wrong
page. Source bytes are never rewritten. `receipt.json` records actual scope.

## Reproduce in an existing office-capable environment

The core bundle verifier remains stdlib-only. This optional, separate replay
requires existing LibreOffice and PyMuPDF installations; it does not install
anything, fetch a URL, launch a service, or schedule execution.

```sh
mkdir rendered
libreoffice --headless --convert-to pdf --outdir rendered proposal.docx
python replay.py proposal.docx rendered/proposal.pdf
python -O replay.py proposal.docx rendered/proposal.pdf
```

For visual acceptance, render the resulting PDF pages to images and inspect all
nine pages; the Python replay does not substitute for that inspection. The
executed cloud run used the local DOCX render helper with an isolated writable
LibreOffice profile and inspected `page-1.png` through `page-9.png`.

`replay.py` deliberately binds this one exact fixture and its single-column
reading order. PDF annotation-array order is not assumed: annotations are sorted
by source geometry. Source labels use word centers inside link rectangles to
avoid accidentally including neighboring lines. Destination text is taken from
the line nearest the destination's vertical position, with a one-point tolerance.
Changed fixture bytes require a fresh source review rather than silently updating
an expected hash. This is **not** a general DOCX/PDF compatibility validator.

## Still incomplete as proposal content

Page 2 visibly marks three required attachments as not supplied. Page 6 retains
an unresolved `S-APPENDIX-C` reference, not a fake active hyperlink. These are
intentional visible gaps in a fictional demonstration packet, not evidence that
real qualifications or attachments exist. The file is not submission-ready.

This office-render receipt is distinct from native Microsoft Word GUI interaction
and from the UIOWA-119 HTML browser click/reload test, which remains unverified
after the separate runtime administrator navigation block.
