# Reuse the resolved PID when killing a port

This packet corrects one target-selection inconsistency in [sindresorhus/fkill](https://github.com/sindresorhus/fkill) at commit `86af01523c6c0360cbce2b0e6059d56e9d71864f`. The public API accepts a colon-prefixed port such as `:8080`. The function already resolves that input into `parsedInputsMap` for the existence lookup, force-after-timeout phase, and wait-for-exit phase. Its initial signal call nevertheless passes the original port string to `killWithLimits`, whose first action resolves the port again.

If the port listener changes between the two successful lookups, the initial signal may target a different PID from the one used for existence checks and later tracking. This is a source-derived possible interleaving, not an observed process run.

The one-line change passes the existing `parsedInput` to `killWithLimits`. A successfully resolved numeric PID therefore reaches the initial signal without a second port lookup. `parseInput` returns numbers unchanged. Process names, numeric inputs, platform-specific signal behavior, negative process-group IDs, and existing self-process handling keep the same path. When the initial lookup throws, the map still stores the original input and the existing later retry behavior is preserved.

This does not provide an atomic OS process identity guarantee: a PID can still be reused after lookup. It does not change the behavior of a failed first lookup or implement the broader process-tree request.

## Integration

The patch is based on `index.js` blob `f9453d1e59ee8d17e9721648a938e85497eaebe2`. Compare the retained original with the intended target before applying `fix.patch`. `patched/index.js` is the complete proposed replacement. No dependency, public type, package metadata, or documentation API change is required.

The separately listed [jamilahmadzai/fkill#1](https://github.com/jamilahmadzai/fkill/pull/1) remains its author's open, unmerged process-tree submission at head `29ee3e55238f422c9a05e1d47b85f343f5774a54`. Its `index.js` blob `76a9c20ebf0d0adbd5bbffa91bcacf284726a07a` contains the same original-input call, inside an assignment that collects descendant PIDs. A future integration into that branch should substitute only the argument there; this current-main patch must not replace that branch's process-tree implementation.

The other accessible named proposal, nmc237 commit `e854aa5d481a90e15cd7da320c7375d0b69e80ce`, also retains the original-input call in its `handleKill` section. No ownership or acceptance claim is made over either proposal.

## Source and acceptance limits

Qualification retained the current issue [sindresorhus/fkill#21](https://github.com/sindresorhus/fkill/issues/21), all seven issue comments, the listed fork PR metadata, all six changed-path metadata entries and four production patches, complete current and fork `index.js`, current package and README, fork README, and the narrow call section of the other accessible proposal. Public Slack search returned three rows and end-of-results; the existing fkill-cli#21 activity is a different repository. The own-upstream-PR query and current open Commons fkill query returned no results; the exact fkill/port activity search returned no results.

The current upstream repository metadata says pull requests are disabled and creation is collaborators-only. This packet makes no upstream write or contact. The historical upstream PR20 metadata route returned 404 and is held. The source lookup for Isjuanplayer's named commit `c9c9c8878ee73ee2396f44b56ec29c80672f7dde` also returned 404 (commit not found) and is held; its actual code is not characterized. These gaps prevent exhaustive external-proposal reconciliation, but do not alter the retained current-main call sequence.

Validation is static source reasoning and publication byte readback only. No JavaScript, process-list command, signal, port lookup, dependency installation, test, fixture, build, workflow, or native probe was executed. Upstream integration and actual platform/process acceptance remain pending. No timing, runtime success, issue completion, or award claim is made.

The exact upstream MIT license is retained in `LICENSE`.
