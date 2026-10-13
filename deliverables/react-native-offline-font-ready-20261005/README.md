# React Native Offline example: finish font startup on failure

This patch repairs one startup path in the SDK 54 example proposed by **younes-bkb** in [rgommezz/react-native-offline PR #392](https://github.com/rgommezz/react-native-offline/pull/392). The existing contribution remains the complete Expo upgrade; this packet adds only font-error handling to its `example/App.tsx`.

The candidate manually prevents splash auto-hide, reads only the loaded flag from `useFonts`, and returns no application content until that flag becomes true. If the font hook reports an error while loading remains false, both splash-hide paths stay inactive and the component continues returning `null`.

The correction retains the hook's error result, lets both hide paths run after either a successful load or a reported font error, and limits the `null` return to the still-loading state. Both hook dependency lists include the error so that a failure transition is observed.

| Font hook state | Root content | Existing splash-hide paths |
| --- | --- | --- |
| Not loaded, no error | Still waits | Still wait |
| Loaded | Renders | Run as before |
| Error reported | Renders instead of waiting indefinitely | Run |

This follows the lifecycle shown in the official [Expo SDK 54 Font documentation](https://docs.expo.dev/versions/v54.0.0/sdk/font/#usage). A font error is a completed loading outcome; it is not evidence that the missing font or icons became available.

## Source and integration

- Source PR author: `younes-bkb`.
- Source repository: [younes-bkb/react-native-offline](https://github.com/younes-bkb/react-native-offline).
- Pinned PR head: `6f115075aec83f47e7ee41ff159fec7670121cd3`.
- Original `example/App.tsx` Git blob: `aa9a36f5db8c451c5b5bd5fd1b8269e63624d1c6`.
- Original project MIT license is retained unchanged in `LICENSE`.

The packet contains the complete original file, complete repaired file and `font-startup.patch`. Apply the patch from the root of that exact PR checkout with `git apply /path/to/font-startup.patch`, or use `patched/example/App.tsx` as the postimage. The patch targets the pending SDK 54 candidate, not the older upstream master example. Reconcile any later source changes before integration.

SDK versions, dependency lockfiles, navigation, queue behavior and the contributor's wider upgrade are unchanged. The source author retains ownership of PR #392; this packet does not mutate that PR or submit a competing complete upgrade.

## Acceptance limits

This is a static source correction. The failure path is inferred from the retained source and the official hook contract; it was not reproduced on a device. No font failure was injected, and no application, native build, dependency installation, test, workflow, or alternate runtime was executed.

The existing [contribution guide](https://github.com/younes-bkb/react-native-offline/blob/6f115075aec83f47e7ee41ff159fec7670121cd3/CONTRIBUTING.md) requires issue discussion before a PR and successful project checks with relevant coverage. No issue discussion, upstream submission or completion of those requirements is claimed here. The required maintainer intake and executable acceptance remain pending.

PR #392 remains open and external. [Issue #339](https://github.com/rgommezz/react-native-offline/issues/339) asks for an example that launches in the applicable Expo Go version. This packet neither establishes current App Store SDK compatibility nor resolves the full issue, and makes no reward eligibility, approval or payment claim.
