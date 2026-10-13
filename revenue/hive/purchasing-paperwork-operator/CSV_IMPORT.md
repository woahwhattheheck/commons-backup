# Purchasing CSV intake

The existing `purchasing_operator.py` CLI and loaders use the same CSV reader. The landed strict reader does not alter invoice matching, decimal calculations, review states, or accounting exports.

## Accepted input

Use UTF-8, optionally with a byte-order mark, and the required column names shown in `examples/`. Header spelling is exact. Additional uniquely named columns remain available to the reader; values retain the existing surrounding-whitespace trimming. Quoted commas, escaped double quotes, Unicode, quoted multiline values, CRLF and LF records, and an absent final newline are supported. Explicit empty cells are distinct from a row missing a cell. A header-only file is a valid empty dataset; an empty file still lacks the required columns.

Blank physical lines between records are skipped. Source references now identify the first physical line of each CSV record, including after multiline values and blank lines. They are not logical-record ordinals. Existing single-line files retain their previous source locations.

## Input diagnostics

Duplicate headers (including optional columns), empty or whitespace-only headers, and the reserved `_line` metadata header produce `PurchasingError`. Each data record must contain exactly as many cells as the header. Width errors identify the path, the record's starting physical line, and expected/actual field counts. Malformed quoting, invalid UTF-8, and parser field-size errors also use `PurchasingError` rather than escaping as a traceback. The standard CSV field-size setting is unchanged.

The CLI reports these input errors with exit status 2. Validation occurs before output creation, so malformed input does not replace an existing output packet. Correct the source CSV and rerun the normal CLI; no vendor message or accounting post is sent.

## Focused regressions

```sh
PYTHONWARNINGS=error::ResourceWarning python -B -m unittest -v test_purchasing_csv_robustness.py
python -m py_compile purchasing_operator.py test_purchasing_csv_robustness.py
```

These eight additional consumer methods use real temporary files and actual CLI subprocesses against the landed strict reader. They cover all three loaders, LF/CRLF/CR source locations, clean CLI failures, physical-line provenance in records and unsent drafts, source hashes, and preservation of complete previous output packets. Low-level parser coverage remains in the existing `test_csv_intake.py`; that suite and the production reader are not duplicated by this addition. Synthetic end-to-end inputs produce one 50.00 review-only match and one unsent quantity exception; they do not represent a customer transaction.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
