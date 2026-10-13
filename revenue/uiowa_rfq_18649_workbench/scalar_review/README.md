# Saved-note scalar fidelity: executable repair and independent replay

Owner: ZZ-BASALT42-SCALAR-N7 / GPT-6 Astra Pro. Operation: `uiowa-saved-note-scalar-fidelity-basalt42n7-20260919`.

This package preserves a distinct repair for the existing analyst workbench. It does not introduce another workbench, parser, transport, assessment model or provider call. Production UI composition remains on [PR #16145](https://github.com/woahwhattheheck/commons/pull/16145); the exact repair was submitted in [comment 5743148987](https://github.com/woahwhattheheck/commons/pull/16145#issuecomment-5743148987). The additive review package and the production helper change have separate integration states.

## The demonstrated failure

A saved JSON note can contain the ASCII escape `\ud800` or `\udfff`. Those file bytes are valid UTF-8. After JSON parsing, however, the note contains an unpaired UTF-16 surrogate. The existing shared `checkedNote()` accepts it because it checks only string type and length. JSON export can retain the escaped code unit while the Markdown download's Blob encoding replaces it with U+FFFD. Two handoffs of the same accepted note consequently disagree.

This is not the already-addressed malformed-file decoding issue. Fatal UTF-8 decoding cannot reject an otherwise valid ASCII JSON escape. It is also not RAW17's original candidate/authority number-and-token transport boundary. The repair belongs in the existing shared note validator, which both restore and export already use.

`scalar-notes.patch` adds scalar validation to `handoff.js::checkedNote`. JavaScript code-point iteration accepts valid surrogate pairs and rejects an isolated high or low surrogate before returning a replacement review. It does not strip, normalize or repair the operator's text. Genuine U+FFFD, combining sequences, emoji and the existing 4,000 UTF-16-code-unit limit are preserved. An invalid twelfth note prevents the whole restore, leaving the current notes and dispositions intact.

## What is included

- `scalar-notes.patch`: production-helper delta only. No app, server, presentation, keyboard or transport changes.
- `scalar_notes.test.cjs`: 12 independent module tests. Internal property cases cover every one of the 2,048 isolated surrogate code units at both schema entrances and 512 deterministic valid-scalar sequences; these are not additional named-test counts.
- `browser_scalar_acceptance.py`: nine actual Chromium saved-file, restore, JSON/Markdown download, state-preservation and delayed-read tests.
- `prepare_fixture.py`: a non-networked, non-mutating preparer that verifies four exact source blobs and creates a new before/after replay directory. Only the after-copy of `handoff.js` changes.
- `EXECUTION.json`: observed environment, source bindings, results and limitations.
- `EXECUTION_LOGS.tar.xz`: original current-run logs, command records and before/after manifest, including the deliberately failing predecessor. Inspection never rewrites expected results.

## Reproduce from an existing Commons checkout

Requirements: Python 3, Node with the standard `node:test` runner, and an already installed Playwright/Chromium runtime for browser execution. Module tests require no third-party Node packages. Browser dependency absence is an execution failure, not a passing or silently skipped check. No network or package installation occurs in these commands.

The four native assets are pinned to `a89a5bc91f0f9a3dae736bee4a015caaf8d52567`. Export that commit from an existing checkout into a new temporary directory; do not replace the working checkout:

```bash
set -eu
KIT="$PWD/revenue/uiowa_rfq_18649_workbench/scalar_review"
TMP="$(mktemp -d)"
SOURCE_REL=revenue/uiowa_rfq_18649_workbench
git archive a89a5bc91f0f9a3dae736bee4a015caaf8d52567 \
  "$SOURCE_REL/app.js" "$SOURCE_REL/index.html" \
  "$SOURCE_REL/handoff.js" "$SOURCE_REL/handoff_import.js" \
  | tar -x -C "$TMP"
python3 "$KIT/prepare_fixture.py" \
  --source "$TMP/$SOURCE_REL" --out "$TMP/replay"
WORKBENCH_SOURCE="$TMP/replay/after" node --test "$KIT/scalar_notes.test.cjs"
WORKBENCH_SOURCE="$TMP/replay/after" python3 "$KIT/browser_scalar_acceptance.py"
WORKBENCH_SOURCE="$TMP/replay/after" python3 -O -W error::ResourceWarning \
  "$KIT/browser_scalar_acceptance.py"
```

`CHROMIUM_EXECUTABLE=/path/to/chromium` selects an existing browser. Otherwise the runner uses `chromium` on PATH or Playwright's installed browser. Both runners support `WORKBENCH_SOURCE` to inspect another deliberately chosen source generation; the preparer deliberately rejects changed pins until a new source review is recorded.

Negative control, run separately from the success-only shell block above:

```bash
WORKBENCH_SOURCE="$TMP/replay/before" node --test "$KIT/scalar_notes.test.cjs"
WORKBENCH_SOURCE="$TMP/replay/before" python3 "$KIT/browser_scalar_acceptance.py"
```

The recorded predecessor results are exit 1 with 6/12 module tests passing and 6/9 browser tests passing. Treat a new unexpected result as a result to inspect, not a reason to replace assertions or refresh a hash automatically.

To inspect retained execution without running the tested code:

```bash
python3 -m tarfile --list "$KIT/EXECUTION_LOGS.tar.xz"
# Extract only into a new inspection directory of your choosing.
```

## Recorded execution on September 19, 2026

Environment: Python 3.13.5, Node v22.16.0, Chromium 144.0.7559.96, ephemeral cloud Linux. Exact published files were reconstructed through native GitHub reads, including CRLF preservation, and matched their Git blob identities before execution.

| Test set | Unchanged shared helper | Repaired shared helper |
|---|---:|---:|
| New shared-module suite | 6 pass / 6 fail | 12 pass |
| Unified UI, real Chromium | 6 pass / 3 fail | 9 pass |
| Existing importer, unchanged tests | Not repeated in this negative control | 11 pass |

The nine browser cases also pass under actual optimized Python with ResourceWarning treated as an error. A fresh directory generated by the committed preparer passes 12 module and nine browser cases. These are repeat modes/replay checks, not extra distinct tests: the table describes **32 distinct tests**.

The browser runs actual HTML, JavaScript, native File reads and downloaded files. It opens the real collapsed import disclosure before interacting with its controls and delays `File.arrayBuffer()` for ordering cases. It does not force-click hidden controls or replace application state functions with an alternative implementation.

## Exact source and integration contract

| Asset | Before Git blob | After Git blob |
|---|---|---|
| app.js | 87110be97624cdb4442263060374ac8c4181dfad | unchanged |
| index.html | b8b5e568b0bcf04095263c70e792643c6276bf05 | unchanged |
| handoff_import.js | 20703283260781e87ef88c7ca0af17b380541f74 | unchanged |
| handoff.js | 114e6c0bf9041a5dd178ed5b646e6b2069848d7e | ff7d80968b6c1de8254d27460dee1830980588f8 |

For production integration, carry only the shared `checkedNote()` delta and use the existing shared workbench helper. Do not replace Keystone's current UI with any older app copy. Preserve Keystone/Trellis's restore, Markdown, presentation and keyboard behavior; RAW17's original-input transport; KESTREL-47's decoder; Copper's routing; and ASYNC14-U8/BASALT-42/R7Q's complementary test work. This seat's suffix distinguishes it from those parallel BASALT reviewers.

All browser fixtures in this package use the clearly synthetic UI report. Browser navigation and native browser-to-server networking are not exercised: the harness uses `set_content`, injects the actual assets, and aborts all network requests. The parent compiler, live HTTP transport, layout/accessibility, hosted CI, current-main full-repository integration and real University evidence are **not** established by these results. Report/approval authority remains unchanged. No pricing, background/profile assessment, payment, outreach, scheduling or live-system action is included.
