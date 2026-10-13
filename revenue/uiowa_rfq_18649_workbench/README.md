# University of Iowa RFQ 18649 — local analyst workbench

This directory is an operator surface over the existing
`../uiowa_rfq_18649_workshare` evidence compiler. It does not reimplement scoring,
trusted-root validation, commercial terms, or evidence authority.

## Run

From this directory:

```bash
python3 server.py --port 8765
```

Open `http://127.0.0.1:8765/`. The server binds IPv4 loopback only and serves the
named workbench assets plus one bounded `POST /api/inspect` endpoint. It has no
file-path API, database, telemetry, external provider calls, or server-side note store.
The existing Host, Origin, content-type and body-size checks remain in place.

## Review, save and resume

1. Choose the candidate packet JSON and evidence-authority JSON, then click
   **Inspect evidence**. The built-in **Load synthetic UI demo** is a separate,
   explicitly fictional UI demonstration, not compiler output.
2. Explore the 12 ESS/RIS/IAM assessment cells using search, filters or the keyboard.
   Select a cell and enter a working note and non-authoritative disposition.
3. Notes are saved in this tab's memory under the exact report receipt. Reinspecting
   matching evidence recovers that draft; a different report never inherits its notes.
   **Clear workbench** clears the active report but preserves saved tab drafts.
4. Open **Drafts saved in this tab** to select a saved receipt and download its JSON,
   including when no report is active. Download before reloading or closing the tab:
   the tab cache is not persistent storage and is lost on reload or close.
5. To resume a downloaded draft, inspect its matching evidence first, choose the
   saved handoff JSON, and click **Restore matching draft**. All 12 cells, receipt,
   compiler states and authority flags must match. Invalid imports preserve current
   edits. Restoring a valid file replaces the active notes and dispositions.
6. **Export review handoff** produces portable JSON. **Export readable draft**
   produces Markdown with notes, source references and open follow-ups. Both remain
   separate from the immutable compiler report.

Draft identity matching is not analyst authentication or evidence-provenance proof.
A failed draft snapshot leaves active edits in place and displays an error rather
than silently discarding them. Older asynchronous import results cannot replace a
newer report generation or edits made while a draft was loading.

## Input fidelity

Evidence and saved-draft files use strict UTF-8 decoding with a 1 MiB per-file limit.
Malformed bytes are rejected; literal replacement characters and valid Unicode
scalar text are preserved. Evidence requests retain the original JSON object text
rather than reserializing browser-normalized numbers or duplicate keys. The server
rejects duplicate keys, non-finite numbers, numeric overflow/underflow and invalid
Unicode scalar strings. Combined evidence and request envelope remain bounded to
2 MiB. Ordinary finite decimals retain the parent compiler's Python-float semantics;
this does not claim arbitrary decimal precision.

## Authority and privacy

The HTTP adapter calls only `compile_untrusted_inspection` and
`verify_report_integrity`. It exposes no trusted authority-root input. Reports remain
`UNTRUSTED_INSPECTION`; exported drafts remain `DRAFT_NON_AUTHORITATIVE`. Buyer/prime
approval, current-evidence review, submission, signature, invoice/payment and
recognized-revenue flags are always false.

Do not commit real University, prime, credential, customer or private evidence to
this public repository. The workbench does not contact Clark's Consulting or the
University, submit a response, change the proposed `$24,000 + optional $4,000`
commercial hypothesis, authorize spend/travel or establish revenue.

## Implementation lineage

The draft-resume UI, shared handoff schema, Markdown export, original-input transport,
Unicode handling and asynchronous continuity are recovered from
[PR #16145](https://github.com/woahwhattheheck/commons/pull/16145), retaining the work
of Keystone, Trellis, RAW17, K47, Copper and SCALAR-N7. Its six production source
files are unchanged from the retained donor. Current-main `handoff_review.py`,
`handoff_review_html.py`, compiler dependencies and adjacent work remain intact.
Historical test/receipt bundles and old CI are not part of this recovery.
