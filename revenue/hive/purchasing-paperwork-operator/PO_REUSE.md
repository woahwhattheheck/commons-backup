# Repeated purchase-order lines in one reconciliation batch

The operator performs exact full-line invoice-to-PO matching. A single existing
PO line referenced more than once in the same imported invoice batch now sends
every corresponding invoice line to review. It does not choose the first row as
an automatic winner.

The report and each unsent exception draft contain
`po_line_reused_in_batch:count=N`. Those rows are absent from
`accounting_import.csv`; unrelated uniquely referenced lines remain eligible for
review-ready export. The source CSV files are unchanged, and drafts retain
original file hashes and physical CSV line references.

For example, two distinct invoices each asking for all four units on a single
four-unit PO line both require review. Correct the source batch, then rerun; one
remaining valid reference exports normally. Existing vendor, quantity, currency,
and price discrepancies remain visible. Repeated missing PO references retain
the existing `po_line_not_found` behavior.

This is batch-level reconciliation, not a cross-run payment ledger. It does not
record payments, post accounting entries, send drafts, silently allocate partial
invoices, or determine which invoice is genuine. Partial invoices already fail
the exact full-line quantity check; this change does not add allocation support.

## Focused acceptance

From this product directory:

```sh
python3 -m unittest -v test_purchasing_operator test_purchasing_po_reuse test_desk_po_reuse
```

The retained local run contains 47 tests: nine existing engine tests, 29 added
engine regressions, and nine added desk-consumer regressions. It covers the
separately landed Unicode vendor-key normalization and input/output path-alias
protection, plus real SQLite persistence and loopback HTTP/CSV/ZIP output. This
is not a claim of all-product, repository-wide, hosted CI, or browser coverage.
All test fixtures are synthetic.

## Existing saved desk packets after an engine upgrade

The desk intentionally stores immutable historical results. Reopening an old
packet, exporting an old revision, or retrying its original request ID does not
rerun matching. To apply the new engine, save a new revision with the current
`expected_revision` and a new `request_id`; then review/export that revision.
Retain old revisions as history, not as evidence that the new engine approved
them. Correct the imported source when appropriate rather than discarding
invoices without review.

A retained two-process upgrade check uses the actual prior and repaired engine
versions with one synthetic SQLite database: revision 1 retains its original
two export rows; explicit recomputation creates revision 2 with zero export
rows and two unsent drafts. No historical payload is rewritten.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
