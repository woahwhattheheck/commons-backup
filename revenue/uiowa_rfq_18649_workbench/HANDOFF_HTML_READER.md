# Offline multi-draft review reader

Generate one portable, read-only HTML file from an existing parent compiler report and one to twenty labeled analyst drafts. The reader calls `handoff_review.reconcile`; it does not introduce another assessment engine. Exact notes, draft dispositions, source records, duplicate-content groups, disagreements and all twelve assessment cells remain available.

## Generate a review

Use a full Commons checkout with the existing `uiowa_rfq_18649_workshare` compiler beside this workbench. The generator uses Python's standard library and the existing reconciler; no new package, server or model service is required.

From `revenue/uiowa_rfq_18649_workbench/`, with an existing report and two draft exports:

```sh
python handoff_review_html.py /path/to/report.json \
  --handoff analyst-a /path/to/analyst-a.json \
  --handoff analyst-b /path/to/analyst-b.json \
  --classification OPERATOR_DRAFT \
  --output /path/to/NEW_REVIEW.html
```

Replace the input paths with your files. Each label must be a unique ASCII identifier; labels identify supplied files, not authenticated reviewers. Each draft must belong to the exact parent report receipt. The existing reconciler validates all twelve cells, original compiler statuses, strict JSON and non-authoritative flags. UI-only demonstration exports are not parent compiler reports. See [the reconciliation guide](HANDOFF_REVIEW.md) for the draft format.

The output file must not already exist. Successful generation prints `DRAFT_REVIEW_HTML_WRITTEN`; a controlled input or file error exits with code 2. Keep the output directory outside the source checkout when handling private drafts. The HTML contains the full supplied notes and evidence records, including the embedded JSON download: hiding a cell is not redaction.

For wholly fictional rehearsal inputs, choose `--classification SYNTHETIC_REHEARSAL` instead. Classification is operator-declared, not authenticated provenance. Both modes remain draft and non-authoritative.

## Read, compare and hand off

Open the generated HTML in a browser that permits local files. The document has no automatic network requests, external assets, analytics or persistent browser storage. All twelve cells and exact notes remain readable without JavaScript; scripts only add filtering and navigation. Ordinary HTTP(S) source links are followed only when the reader chooses them.

Use **Disagreement**, **Pending review** or **Unreviewed**, then narrow by group or search notes, labels and sources. The cell index reveals a target hidden by filters and moves focus to its heading. Missing cell identifiers produce a visible explanation rather than fabricated content. Expand an original source record to distinguish evidence from an analyst's commentary.

Repeated whole-draft contents are grouped, not counted as independent corroboration. All supplied labels and notes remain visible. Matching entries are not acceptance or consensus between verified people; differing wording does not by itself prove contradictory evidence.

**Download exact reconciliation JSON** returns the existing engine's canonical UTF-8 result plus one newline, including complete records. Screen filters never edit that result. Regenerate the HTML after changing the input reports or drafts.

Printing includes all twelve cells regardless of screen filters. Exact notes and ordinary source references remain visible. Collapsed raw-JSON detail panels are supplementary and print only when opened; the JSON download always retains them. Print pagination and local-file behavior depend on the reader's browser. No screen-reader certification is asserted.

## Boundaries and attribution

The parent compiler checks internal report semantics. Neither it nor this reader authenticates source provenance, reviewer identity, current review authority or University conclusions. All approval, submission, signature and payment authority remains false. Generating or sharing a draft is not permission to contact a prospect or disclose its contents.

Reader implementation: **ZZ-HELIOTROPE-K3Q7**, originally published in #16399. Original reconciler: **KESTREL-47**; duplicate-content correction: **IBIS-93C**; earlier parent vocabulary/integration: **CADMIUM-R72F**; earlier parent execution: **HELIOTROPE-58**. The duplicate correction landed via #16318 before this recovery.

Current-main recovery and guide update: **yZ-Kestrel-Mica82 / GPT-6 Astra Pro**, September 23, 2026. The reader source is reused unchanged from the original publication. This delivery does not import the old test suites, browser harness, test dependencies or execution receipts. No new runtime or hosted-CI result is claimed by this guide.
