# UIOWA-128 — linked reviewer navigation

Work record: Commons #16200. Original implementation: `uiowa-128-rivet-20260919`; integration recovery: `yz-cairn57-uiowa128-delivery-20260923`. This extends the existing analyst workbench, not its assessment engine or authority model.

## Use the linked view

From this directory in a full checkout, run `python3 server.py --port 8765` and open `http://127.0.0.1:8765/` in an authorized browser.

1. Load the synthetic UI demo, then **Load synthetic linked review queue**. Open `COMMENT-SYN-128/é + #1` and follow recommendation → finding → source. The reference chain selects the existing ESS/software-development cell. A source identifier is not the source document.
2. Copy the exact-link field. After reload the locator remains, but the view says **WAITING_FOR_REPORT**. Inspect the matching evidence, then import its review-navigation JSON to reopen the same record. Source references need only the matching report. A temporary sample parks the prior locator; to reopen a sample record after reload, start the sample, load its review queue, then open the copied link.
3. Export the linked HTML guide for a script-free, read-only snapshot with internal record links. Export review-navigation JSON to retain the imported review records. Analyst notes/dispositions remain in the separate draft-handoff format; these exports do not merge the two formats.
4. Change a revision in a link to see **MISSING_RECORD** without substituting an alternative. Duplicate exact identities show **AMBIGUOUS_RECORD**, not the first match.

Every bundled example is fictional: none is a University finding, recommendation, source document, or actual reviewer comment. Evidence replacement clears imported review records even for the same receipt. A temporary sample parks the current records and locator and restores them when you leave. The workbench's existing same-receipt saved-draft recovery is preserved: working notes can return from this tab's draft cache, but review packets must be loaded again after evidence replacement. Reload or closing the tab discards both in-memory caches; export the relevant JSON files to keep them.

## Record contract

Schema: `uiowa-rfq18649-review-navigation/v1`, with `report_receipt_sha256` and `records`. Obtain an editable example from **Export review-navigation JSON**, or use:

```sh
node -e 'console.log(JSON.stringify(require("./review_navigation.js").syntheticPacket(), null, 2))' > synthetic-review-navigation.json
```

A record contains `kind`, `origin`, `id`, `revision`, `title`, `text`, explicit boolean `synthetic`, `cell_keys`, and `references`. Reference identity is the exact tuple `kind/origin/id/revision`; kinds are `source`, `finding`, `recommendation`, and `review-comment`. Case, spaces, Unicode composition, plus signs, and hash characters are not normalized. The tuple is a navigation locator, not the separate UIOWA-103 equivalence map.

`compiler-report` is reserved for source references actually present in the installed report. Their revision is the report receipt; their cell memberships come from the matrix. Repeated source IDs can belong to multiple cells. Missing or ambiguous references and cycles remain visible without inventing cell relationships.

Unknown extension fields, null, empty strings, and literal `NA` remain distinct in the owned JSON-semantic snapshot. This is not byte-preserving archival: whitespace, key order, numeric spelling, and duplicate-key spelling are not retained. Non-finite numbers, negative zero, and unsafe integers are rejected; exact large numbers and identifiers must be strings. Do not replace original evidence bytes with review JSON.

Intake is limited to 1 MiB per file, 2,000 records, 2,000 references per record, 512-character IDs/origins, 128-character revisions, 2,000-character titles, and 50,000-character text. Files must contain valid UTF-8; malformed bytes are rejected instead of silently becoming replacement characters. Malformed Unicode in every string or object key, including extension fields, is rejected without normalizing valid text. Invalid route fields and nonexistent explicit cell keys are also diagnosed. Receipt matching does not authenticate an imported statement or authorize its use.

## Navigation and privacy

**WAITING_FOR_REPORT** needs the matching report; **REPORT_MISMATCH** shows expected and actual receipts; **WAITING_FOR_RECORDS** needs its review packet; **MISSING_RECORD** identifies the missing version; **AMBIGUOUS_RECORD** refuses first-match selection. An unresolved route clears the old selected evidence cards, heading, and visible note controls so they cannot masquerade as the target. Navigation does not erase stored draft notes.

Links put receipt and record identity in the URL fragment, not evidence text. IDs may nevertheless be sensitive. Exported guides contain review text and must be handled like the source material. There is no new telemetry, external storage, scoring, approval, or payment operation.

## Integration boundary

`review_navigation.js` owns record validation, exact routes, and guide exports. Its file reader rejects malformed UTF-8, and its JSON-semantic snapshot rejects unpaired Unicode surrogates in strings and keys. `review_navigation_workbench.js` loads after `app.js`, attaches the pane, and wraps the existing `installReport` and `resetWorkbench` functions without changing their return or error behavior. It synchronizes review records only when `state.generation` changes. A listener after the app's already-registered reset listener covers the original click callback; programmatic resets use the wrapper. Failed draft preservation leaves the generation, report, and review packet intact. Selection uses the current app's renderer without stealing focus during passive route resolution.

The shared app, handoff modules, and stylesheet are not modified. The server only allowlists the navigation engine, adapter, and stylesheet; the HTML loads them in order. Existing strict intake, compiler, request, and CSP behavior remain unchanged. Changes to the app's generation/function contract must be composed with this adapter.

## Browser delivery

The earlier recovery exercised exact local asset bytes in Chromium, including saved-draft recovery, failed-reset preservation, and every exported guide target. On 2026-10-03 the remaining delivery journey completed in Chrome Headless Shell 154.0.8037.92 against the ordinary `server.py` HTTP endpoint: the document and all nine script/style assets returned 200 under the server's existing CSP. No assets were substituted and no browser policy or CSP was relaxed for this journey.

The actual pane opened `COMMENT-SYN-128/é + #1`, followed recommendation → finding → source, and selected ESS/software-development. After composition with the temporary-sample restoration in #30502, the same journey used the existing synthetic evidence files through the real compiler HTTP endpoint. Native browser downloads produced a 2,570-byte review JSON and 28,657-byte linked HTML guide without download errors; the JSON retained all imported record semantics. Reload and reinspection retained the exact locator through **WAITING_FOR_REPORT** and **WAITING_FOR_RECORDS**; importing that downloaded JSON restored **FOUND** and the same Unicode identity. The downloaded script-free HTML opened with its styles and exact comment anchor. Malformed UTF-8 and escaped unpaired surrogates in a title and extension key each produced the documented intake error and cleared the record queue; reimporting the native JSON restored the exact record without page errors.

The three old standalone test suites are not imported into main by this recovery. Their historical implementation and results remain in PR #16304's original commit history; they must not be treated as current-head evidence. No new test framework or receipt files are introduced.
