# UIOWA-136 bid assembly

Isolated path: `revenue/uiowa_rfq_18649_bid_assembly/`

Repeatable local assembler for University of Iowa RFQ 18649. It consumes
the landed UIOWA-132 commercial-facts pins, hashes every supplied source,
and writes a review-draft folder with stable names, an attachment index,
visible missing financial/qualification placeholders, a source/version
register, and PDF/DOCX/HTML with real internal navigation.

This package does **not** submit, contact the prospect, certify
qualifications, accept terms, issue an invoice, or schedule anything.

## What it preserves

- TJLabs subcontract workshare is **$24,000** base + **$4,000** readout
  option, 40/40/20 = $9,600 / $9,600 / $4,800. That is **not** Attribute 9's
  all-inclusive prime bid fee.
- Principal stays **prime**; specialist stays **subcontract**.
- RFQ Bid Invitation prints **2026-09-22 15:00 CT**; the workshare overlay
  is **2026-09-29 15:00 CT**; UIOWA-132 pins 2026-09-22. The assembler
  records a **CURRENTNESS_HOLD** instead of silently picking a date.
- Attribute 15 is not filled with an invented no-exceptions certification.
- Attribute 19 audited statements **and** annual reports stay placeholders
  until real files are supplied. Size/digest stay `UNKNOWN`, never `0`.
- A manifest `provided: true` for a missing file is an **ERROR**; the
  filesystem wins.
- Existing output directories are refused, not overwritten.
- Oversized inputs fail visibly rather than overflowing.

PDF/DOCX writers are recovered from OP5-TOPAZ `uiowa_rfq_18649_bid_pack`
(credited). TOPAZ retains original assembler credit. Render-review
(`bid_pack/render_review`, PR #16379) is a peer lane, not this assembler.

## Run

```bash
python3 cli.py --manifest fixtures/prepared/manifest.json --out /tmp/uiowa136-draft
python3 -m unittest test_assembler.py
python3 -O -m unittest test_assembler.py
```

Exit 0 = assembled. Exit 1 = `--strict` and ERROR findings. Exit 2 = refuse
(overwrite, pagination, invented approval, invalid manifest, overflow).

Closes woahwhattheheck/commons#16259.
