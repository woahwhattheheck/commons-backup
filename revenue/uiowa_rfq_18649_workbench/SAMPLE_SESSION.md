# Reversible synthetic demonstration

Open the existing workbench and choose **Start temporary synthetic sample** in the evidence package panel. The application parks the active report, notes, dispositions, selected cell, filters, existing receipt-keyed tab drafts, imported linked review records and exact review locator. No upload, download or local file is modified.

The sample controls stay visible outside the collapsed intake panel. **Reset sample only** creates the original twelve clean demo cells and clears the sample's notes, dispositions, selection, filters, linked review queue, locator and temporary draft cache. It does not recover an earlier edited sample just because the built-in receipt is constant. Starting or resetting a sample uses the existing generation counters to invalidate older asynchronous imports.

**Leave sample and restore review** restores the parked report, tab drafts, linked review packet and exact locator. Following another sample link or resetting the sample does not replace the parked review. Its restored link reopens the same review record while retaining the parked cell selection and filters. Clear workbench has the same restore behavior while a sample is active. Inspecting replacement evidence requires leaving the sample first. An ordinary evidence import still clears imported review records, even when the report receipt is unchanged. Export sample notes before leaving when they should be retained; the temporary sample cache is discarded on exit. Previously downloaded JSON or Markdown stays unchanged.

Opening the workbench with `?demo=1` starts an isolated sample without treating the initial demo as a parked user report. Leaving returns to an empty workbench.

Everything remains in tab memory. Download important drafts before reloading or closing the page. This is a fictional UI demonstration, not compiler output, a University finding, or review/payment authority.

Implementation: `sample_session.js`, loaded after the existing application. It uses the current report installer, strict handoff parser, renderer and monotonic generation counters, and does not replace `app.js`. Design lineage: Orthoclase's UIOWA-125 / #16275, composed with the Keystone/Trellis draft-continuity work landed by #19241. Presentation from #19257 remains intact.
