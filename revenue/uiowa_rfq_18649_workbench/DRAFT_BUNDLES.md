# Back up several working drafts

Use **Back up or restore several report drafts** below the tab-draft panel. **Download tab drafts in one bundle** saves every draft currently in that panel into one `.tjdrafts` file. Notes for the active report are saved first. Leave a temporary synthetic sample before backing up the real reviews parked behind it.

The file is not encrypted. Keep it with the same care as the notes it contains. A bundle contains original working-note handoffs only: it does not include candidate/authority evidence files, complete reports, the separate reviewer queue, credentials or approval authority. Nothing is sent to a server, stored in localStorage or written to a database.

## Restore after reopening the workbench

1. Choose the bundle and select **Read bundle without changing notes**. This creates a separate preview; existing notes, tab drafts and the active report are unchanged. Select an entry by its full report receipt and inspect its original JSON text. Download that individual JSON when needed by the existing single-draft workflow.
2. Inspect the original candidate and authority evidence files for the desired report. The bundle restore button becomes available only when the selected receipt matches the active report.
3. Select **Replace active notes with selected draft**. The existing strict handoff validator checks the whole entry against the active report before all twelve notes and dispositions are replaced. Download the current draft first when both versions should be retained. Imported text is never a substitute for evidence or report validation.

The loaded bundle remains available while switching reports; only an explicit restore installs an entry in the active note/cache state. **Forget loaded bundle** removes that preview, not current notes, tab drafts or downloaded files. A rejected file leaves the last successfully loaded bundle and review unchanged. Choosing another file or forgetting the preview invalidates an older file read still in progress.

## Limits and portable format

A bundle is UTF-8 text, at most 16 MiB and 256 entries. Each original handoff remains subject to the existing 1 MiB draft limit. Duplicate receipt entries are rejected instead of silently overwriting one version. Unsupported headers, invalid UTF-8 and malformed transport rows are rejected. Bundle limits do not delete or trim the active tab cache; individual draft downloads remain available.

The first line is exactly `TJLABS_DRAFT_BUNDLE_V1`. Each following line is a JSON array containing exactly two strings: `[reportReceipt, originalDraftJsonText]`. Newlines inside the original JSON are escaped in the transport line and restored when read. The last line may end with a newline; CRLF transport is accepted. There are no object keys or numeric amounts in the transport envelope, and no draft parse/re-serialization during bundling or individual extraction. Semantic validation is intentionally deferred to the existing report-bound parser at explicit restore.

Implementation: `draft_bundle.js`, loaded after the normal application and sample adapter. It observes existing report/cache UI updates without replacing report-install, sample-session or reviewer-navigation functions. No new scoring logic, review authority, parser for handoff contents, dependencies, tests or receipt archives.
