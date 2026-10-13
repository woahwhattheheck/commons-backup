# Preserve unsaved settings when a download cannot close them

This packet adds a narrow check to apples-kksk's open [code-settings-sync#1459](https://github.com/shanalikhan/code-settings-sync/pull/1459), head `af45726a15a6e2e4484a66bc044d2e4e120a7cc5`. Its existing `CloseOpenFile` method closes visible editors before the download caller writes each settings file. The caller awaits that method and then queues `FileService.WriteFile`.

A resolved close command does not establish that the user permitted closing the document. In VS Code 1.35.1, the command delegates to `group.closeEditors`; a dirty-document Cancel result becomes a veto, and `closeEditors` returns normally without closing. The existing method performs no post-close document check, so the caller can overwrite the on-disk file while the dirty editor remains open. A dirty matching document in a hidden tab is also outside the original visible-editor loop.

The proposed check runs after the existing close loop. It examines the currently known text documents and refuses to continue when a matching file document remains open and dirty. It uses the existing path normalization and Windows case handling. The error tells the user to save or discard their changes before downloading. Clean files and documents successfully saved or discarded by the existing close flow continue to the existing writer. The patch adds no forced save, discard, close command, network behavior, or version-control policy.

This check protects the pending write to that matching file. It is not a transaction for the entire download: the existing caller may already have written earlier files or changed extensions. It does not resolve symlink aliases, implement conflict merging, or provide an atomic guarantee against a new edit after the check. The original visible-editor closure and its focus behavior remain unchanged.

## Exact source and primary API evidence

The source file `src/service/file.service.ts` is retained in full, with original blob `b9a0c1da35c1324f4458161e521bea18610c08de`. The actual download call section is in `src/sync.ts` blob `c4fa7f4a66a1f3b09daa9c900e67550ed7dc307d`. The candidate package, blob `6c870bc50002be4640284871da92cabff9f4d07e`, supports VS Code `^1.35.1`.

Primary source was read at the matching VS Code version:

- [editorCommands.ts](https://github.com/microsoft/vscode/blob/1.35.1/src/vs/workbench/browser/parts/editor/editorCommands.ts), blob `ae8928e6b49df76725a427a990ff5d91e33b4f1a`: the close-active-editor command returns the promises from `group.closeEditors`.
- [editorGroupView.ts](https://github.com/microsoft/vscode/blob/1.35.1/src/vs/workbench/browser/parts/editor/editorGroupView.ts), blob `c8c88be592d918e9c568eda66d8dfc740e8ace9f`: cancellation produces a dirty-close veto; `closeEditors` returns on that veto.
- [vscode.d.ts](https://github.com/microsoft/vscode/blob/1.35.1/src/vs/vscode.d.ts), blob `de5a43cf497e357246af92bdf83c0ee73fd637f6`: the public `textDocuments`, `isDirty`, and `isClosed` properties already exist in the supported version.
- [Current public API reference](https://code.visualstudio.com/api/references/vscode-api#TextDocument) also documents these properties. The version-pinned source above supplies the compatibility evidence.

The cancellation-to-write conclusion is static reasoning over those retained sources. No editor, dialog, filesystem write, target source, or substitute simulation was executed.

## Integration and custody

Compare the original before applying `fix.patch`. `patched/src/service/file.service.ts` is the complete proposed file, preserving the original CRLF line endings. The packet targets PR1459's existing closure implementation and must be integrated with its caller change; it does not replace that feature or claim it as ours.

The canonical [issue396](https://github.com/shanalikhan/code-settings-sync/issues/396) remains open and unassigned. All fifteen comments were read, including the maintainer's request to close affected files and the explicit exclusion of polling/new bidirectional synchronization. PR1459 remains apples-kksk's open submission; PR1472 is closed and unmerged. General and inline comments on PR1459 were empty.

The issue-specific public activity search returned three rows and end-of-results. Delivery confirmed no current source overlap. The open Commons packet query returned no match. The earlier repository-wide own-PR query is still held after its secondary-limit failure; it was not retried or replaced with another route. This is bounded coordination, not exhaustive clearance.

The retained contribution guide `5f04c34639985acbc3ba87798ff436182ca1baeb` and MIT license `3c0206dfac7a006db1957bba0c8dd8cad42d4e17` match this candidate's tree. The guide asks for a version branch; the existing PR currently targets master at `eb332ba5e8180680e613e94be89119119c5638d1`, so a future upstream integration must reconcile that branch choice as well. Its executable checks are not claimed complete. The exact MIT license is included.

Validation is source inspection and full publication byte readback only. No tests, fixtures, dependency installation, build, workflow, native probe, actual cancellation, or upstream contact occurred. Native editor acceptance and upstream integration remain pending. No complete issue resolution, award, or payout is claimed.
