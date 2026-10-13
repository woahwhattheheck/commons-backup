# Release the export lock after temporary cleanup errors

This packet is a narrow continuation of AIVensk's open [code-settings-sync#1483](https://github.com/shanalikhan/code-settings-sync/pull/1483), at head `6f0f63610135e4dace26733af7e4a78d80d0dd8b`. It changes only `FileSystemStore.write` in `src/service/filesystem/store.ts`, original blob `e0731a932ba48f418af803ae1a9792fa70954e20`.

The existing exporter acquires `.settings-sync.lock` exclusively, checks that the previous snapshot still matches, writes a temporary snapshot, and renames it into place. Its cleanup then awaits removal of the temporary directory before closing the lock descriptor and unlinking the lock path. A rejected temporary-directory removal exits that cleanup block immediately. Both lock-release operations are skipped, even if the snapshot rename succeeded. A rejected close similarly skips the unlink. The remaining lock file causes a later exclusive lock acquisition to fail.

The replacement nests the cleanup steps in `finally` blocks. It attempts temporary-directory removal first, attempts descriptor close even if removal rejects, and attempts lock-path unlink even if close rejects. This changes only failure control flow. Normal operation keeps the same cleanup order; exclusive acquisition, snapshot comparison, staging, rename, filesystem selection, import behavior, and credentials are unchanged. Cleanup errors continue to reject the operation. As with ordinary nested finally semantics, a later cleanup error can replace an earlier error; the patch does not add error aggregation.

This is an inspection of the actual production source, not an injected failure or observed filesystem run. It does not guarantee successful cleanup after an operating-system failure or process crash. If unlink itself fails, stale-lock recovery may still be necessary. If the snapshot rename already succeeded, a later cleanup error may still mean the export promise rejects after publication.

## Integration and custody

Compare the retained original with the intended target before applying `fix.patch`. `patched/src/service/filesystem/store.ts` is the complete proposed file. This packet targets the existing PR's filesystem implementation, which is not present in its base `v3.4.4` commit `cd93cdeacab7c010b2445cb78e6422b18c872df0`; it must be integrated with that implementation, not copied into an otherwise unchanged base as a complete feature.

AIVensk retains the complete filesystem feature, original PR, and reported acceptance work. The older [PR1469](https://github.com/shanalikhan/code-settings-sync/pull/1469) remains landeqiming666's open foundation at `c61fe6a79e05ba2fd0a3f293cae860526c4eab6b`. The canonical [issue256](https://github.com/shanalikhan/code-settings-sync/issues/256) remains open and assigned to maintainer shanalikhan. Its thirteen comments include the maintainer's invitation to contribute; the assignment and sponsor acceptance are not changed by this packet.

The retained contribution guide `5f04c34639985acbc3ba87798ff436182ca1baeb` asks for version-branch contributions and executable checks. The candidate uses `v3.4.4`. This Commons deliverable performs no upstream submission; native execution and tests remain unperformed under the executor hold.

## Evidence and limits

Qualification retained the full issue and all thirteen comments; both named PR metadata records; all eighteen changed-path metadata entries for PR1483; the production patches used for routing context; and complete `filesystem.service.ts`, `store.ts`, `syncSettings.ts`, and `webview.service.ts` from its pinned head. PR1483 general and inline comment lists were both empty. The exact upstream MIT license is included.

The issue-specific public project search returned three results and end-of-results, without a current source-edit claim. Delivery confirmed no in-flight source overlap. A broader numeric PR search covered only its newest ten rows and is not treated as exhaustive. The current open Commons query returned no matching packet. The previously failed repository-wide own-PR query remains held after a secondary limit; it was not retried or replaced with an alternate route, and no universal clearance is claimed.

Validation consists of static control-flow reasoning and full publication byte readback. No filesystem operation, target TypeScript/JavaScript, test, fixture, fault injection, dependency installation, build, workflow, or native probe was run. The existing author's test reports are not our results. Runtime and upstream acceptance remain pending. This packet claims neither complete issue delivery nor an award or payment.
