# Correct the window driver's Escape-key example

The existing `@cycle/window` proposal in [cyclejs/cyclejs PR1030](https://github.com/cyclejs/cyclejs/pull/1030), by jamilahmadzai, documents `preventDefault: event => event.key === 'Escape'`. Its actual `Predicate` declaration receives the base `Event`, which has no keyboard-specific `key` member. The `WindowEventMap` overload narrows the returned stream, but its options still use the same non-generic `WindowEventOptions`.

This follow-up replaces that example with `preventDefault: {key: 'Escape'}`. The existing `preventDefaultConditional` and `matchObject` implementation compare that property with strict equality and call `preventDefault()` only when it matches. The condition is therefore the same as the documented predicate, expressed through an already-supported API. The accompanying sentence makes the predicate typing boundary explicit. No driver code, runtime types, listener behavior, dependency or package configuration changes.

## Integration

The source is PR1030 head `b975a25cde29c791515e6eaa393706d35afcdff0`, repository `jamilahmadzai/cyclejs`, with `window/README.md` blob `d4e77eb76c2a8f52b921b81b348dbf6b75742c09`. Its base matches the observed upstream master `5ece2a48c3659538208da3dc8d43a142bc0d91a7`.

The packet retains the exact original README, full corrected README, a two-hunk patch against `window/README.md`, and the unchanged package MIT license. Reconcile the existing PR's current head before applying the patch; preserve all of the author's other work. This change belongs with that contribution rather than a duplicate driver implementation. Original PR883 remains separate historical competing work.

The full issue568 discussion supports a separate window driver instead of expanding DOM selectors. The issue was open/unassigned, and PR1030 was open/unmerged with no issue or inline review comments at the bounded source read. The own-account PR query returned zero. Those observations are source custody, not acceptance or exclusive ownership.

## Validation boundary

This is static source reasoning against the complete three production source files and the actual README/package metadata. No TypeScript compiler, browser, event dispatch, test, fixture, build, package installation, workflow or native execution was performed. The existing PR's reported checks remain its author's reports.

The upstream contribution guide requests builds, package checks and the prescribed commit workflow. Those steps remain unperformed under the executor's offline restriction. This Commons source packet is not an upstream submission, a package release, a claim that issue568 is complete, or a bounty award/payment claim.
