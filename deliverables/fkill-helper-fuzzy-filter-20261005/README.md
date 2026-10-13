# Keep hidden helper processes out of interactive fuzzy search

This source patch repairs an existing mismatch in `sindresorhus/fkill-cli` 9.0.0. Interactive search removes names ending in `-helper`, `Helper`, or `HelperApp` before the default list, port lookup, PID lookup and exact/prefix/substring name matching. Its fuzzy-search index currently receives the original unfiltered list, and its results are appended after removing only already matched PIDs. A helper excluded from those other paths can therefore reappear as a fuzzy result.

The one-line change builds that index from the same existing helper predicate. It leaves eligible process records, ordering rules, fuzzy-search case behavior, rendering, PID selection, kill/force-kill behavior and dependencies unchanged. It neither adds a broader process-hiding policy nor implements same-name grouping or multiple selection.

## Source and integration

The exact upstream preimage is `interactive.js` blob `4983d8dc975954afdacdbe91935528a6c5a39d48`, at main commit `2afe64c9110612ef377d0aa8fdcf8c0ba8d940a1`. `original/interactive.js` retains it; `patched/interactive.js` contains the proposed replacement; `helper-fuzzy-filter.patch` is the one-hunk integration diff. Compare the target's current source with that preimage before applying it. If the target has advanced, retain the current surrounding source and apply only the constructor-input correction. The exact upstream MIT license and notice are included.

Issue [#6](https://github.com/sindresorhus/fkill-cli/issues/6) remains broader: the maintainer's [latest scope clarification](https://github.com/sindresorhus/fkill-cli/issues/6#issuecomment-508548033) identifies same-name submenu/grouping as remaining work. Existing open [PR #91](https://github.com/sindresorhus/fkill-cli/pull/91), by MapleQiAN, adds related grouping and bulk choices. Its retained head `4f57fd061d3d9961a362d2d0c85a05fa98a5709e` contains the same index mismatch, but this packet is prepared against upstream main and does not replace that contribution. Separate multi-selection work for #21 is outside this patch.

## Acceptance boundary

Validation here is static source inspection: the filtered branches and unfiltered fuzzy constructor were traced through the actual interactive caller, and the proposed edit changes only the constructor's process input. No process listing, process termination, interactive session, dependency installation, syntax check, build, test or workflow execution was performed. The executor is offline. Native acceptance remains unperformed.

This Commons packet is a reusable source deliverable, not an upstream submission or an assertion that #6 is complete, accepted or payable. Upstream publication is restricted to collaborators in the retained coordination record; no upstream write was attempted.
