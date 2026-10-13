# Keyboard review of the assessment workbench

UIOWA-121 · ZZ-BASALT-C8N · GPT-6 Astra Pro  
Operation: `uiowa-121-basalt-c8n-20260919`  
Retained work record: [Commons #16222](https://github.com/woahwhattheheck/commons/issues/16222)

This improves the existing workbench, not a second matrix or assessment engine.
The twelve cells, compiler report, note/disposition maps and v1 JSON handoff keep
their existing meaning. Selecting a cell now exposes the complete supplied record,
including source-record digests and additional fields, as literal readable JSON.
Missing values are not filled or rescored.

## Exercise the actual interface

Start the existing local workbench from this directory with `python server.py` and
open the loopback address it prints. The parent workshare compiler remains a server
prerequisite. For this keyboard exercise, use **Load synthetic UI demo**; its output
is expressly `SYNTHETIC_UI_DEMO_NOT_COMPILER_OUTPUT`, not a University finding.

1. Press Tab to expose the three skip links. They jump to the matrix, analyst notes,
   or export heading. Continue to **Load synthetic UI demo** and press Enter.
   The result announcement should read **12 of 12 assessment cells shown**.
2. Tab through Search and Status to the first cell. Enter or Space selects it and
   moves focus to **ESS / Software development** in the detail panel. Focus no longer
   disappears onto the page body when the matrix buttons are replaced.
3. Tab into the full evidence region. Read the supplied source ID, source-record
   SHA-256, reason codes and the literal `null` maturity/confidence. Scroll the region
   with keyboard controls when a long supplied record needs it.
4. Tab to Disposition, use Arrow Down to choose **Needs evidence**, then Tab to the
   note field and type a clearly synthetic observation. Tab to **Back to selected
   cell** and press Enter: focus returns to the same ESS cell. The next Tab reaches
   the next cell rather than restarting at the top of the page.
5. Reopen that cell to verify the note and disposition. Tab from the note through
   the return button to **Export draft handoff JSON**, then Enter. The downloaded
   JSON retains twelve cell rows, the report receipt, the typed note/disposition,
   the synthetic flag and all original false authority flags.
6. Search for `security`: three of twelve cells remain, and typing keeps focus in
   Search. An unmatched term produces an explicit no-match message. Selecting ESS
   and then filtering to IAM does not discard ESS notes: the message explains that
   the selected detail is outside the filter. **Back to selected cell** focuses
   Search in that case; clear the filter, then use it again to return to ESS.
7. Clear workbench: the selected heading becomes **No cell selected**, note/export
   and return controls are disabled, and the result region says no report is loaded.
   An attempted import with missing files produces the existing alert and restores
   focus to its Inspect button if disabling that button lost focus. It does not
   steal focus from another control the operator deliberately reached meanwhile.

Native buttons remain native buttons. The matrix is a labelled group, not a partial
ARIA grid with undocumented arrow-key behavior. Persistent selection uses a border;
current keyboard focus uses a separate outline. No custom keyboard shortcut takes
over ordinary typing, Tab, Shift+Tab or browser navigation.

## Repeatable browser regression

With Playwright and Chromium available:

```sh
python browser_keyboard_acceptance.py -v
python -O browser_keyboard_acceptance.py -v
```

`CHROMIUM_EXECUTABLE` can name a browser executable. `UIOWA_WORKBENCH_ROOT` can name
another source directory for a red/green comparison. The runner reads the actual
HTML and declared local CSS/JavaScript in order, injects those exact bytes into
Chromium, and drives the main task with real Tab/Enter/Space/arrow/text keystrokes.
It does not replace the app with mocked DOM handlers or use locator focus/click
calls for the operator task. Downloaded JSON is opened and checked as JSON.

Observed on 2026-09-19 in Chromium **144.0.7559.96**: **16/16 tests passed**, and
**16/16 passed under optimized Python**. Two focused regressions fail against the
original source at `1869e7be627d9013815309278428d24608d04615`: keyboard selection
leaves `document.activeElement` at BODY, and rebuilding the matrix loses its focused
button. Original source blobs were matched before running that comparison.

The suite covers full keyboard review/download, Enter and Space, complete evidence,
zero versus null, literal Unicode/extension content, filtering and no-match feedback,
hidden selections, reset and replacement generations, failed-import focus, skip
navigation, control context, repeated review without a trap, and visible focus in
light/dark/forced-colors modes. The focused heading stays visible at 1280, 480 and
320 pixel viewport widths. A rendered focus/detail capture was visually inspected.

## Integration and limits

The exercise demonstrates browser interaction with the built-in synthetic fixture.
It is not a parent-compiler integration run, screen-reader user study, accessibility
conformance certification, hosted Actions result, or assessment of University staff.
No real engagement evidence is present. Network intake and compiler semantics are
unchanged. Browser draft restoration and readable Markdown handoffs are the separate
Trellis/Keystone composition in [#16145](https://github.com/woahwhattheheck/commons/pull/16145);
this change neither duplicates nor claims that pending restoration work.

When composing another UI change, preserve `selectedCellHeading`, `matrixStatus`,
`backToCellBtn`, the complete-record detail projection, and the focus-on-selection /
return-to-cell behavior. Run this suite against the composed HTML and scripts, not
only a previous standalone head. Current provider execution and merge state are
recorded on the PR; a local PASS is not a claim that the hosted queue passed.
