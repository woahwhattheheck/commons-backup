# Kap GIF estimate: retire stale responses

The GIF-size estimate proposed in [Kap PR1291](https://github.com/wulkano/Kap/pull/1291) can accept an obsolete asynchronous response after editor settings change, after leaving GIF format, or after the component unmounts. This packet repairs the existing hook by retiring the request identity before asking the main process to cancel it, and clearing the old displayed result when a new GIF estimate enters its debounce period.

This is a source-level race finding, not an observed native reproduction. The original hook checks `estimationIdRef.current === estimationId` before applying both successful responses and errors, but cleanup leaves the reference unchanged. Cancellation is an asynchronous IPC request and cannot invalidate a response that has already completed. The caller in `renderer/components/editor/options/right.tsx` renders from the hook result and has no separate format guard. As a result, a late success can restore a GIF label after the non-GIF effect resets the state.

The correction changes only `renderer/hooks/editor/use-gif-size-estimate.tsx`:

- Clear the previous result when a new GIF effect starts, so the prior settings' estimate is hidden during the 500ms debounce.
- Capture the retiring request ID, set the shared reference to `undefined` synchronously, then send the existing cancellation request using the captured ID.
- Keep the current request's success/error handling, timer, effect dependencies, estimation options, and IPC endpoints intact.

React's [useEffect reference](https://react.dev/reference/react/useEffect) specifies cleanup before the next setup when dependencies change and on unmount. The patch uses that existing lifecycle. Static reasoning covers late success and late failure after cleanup: both existing identity comparisons fail. A subsequent request gets its own existing counter-generated identity and can update the result normally.

## Integration

The original contribution belongs to BaptismofFiber. Apply `stale-response.patch` from the repository root at PR1291 head `fe6ba8935e71a41ea07aad62d4e797da301993e3`:

```sh
git apply /path/to/stale-response.patch
```

The exact hook preimage is blob `4d743a60516c90634d92ea41facb291fcb79f5ee`. Full original and corrected files are retained under `original/` and `patched/`. Reconcile a newer contributor head before applying. Current upstream main is `c42692fa63ac71ed192e01684beb78a1b864aa88`; it does not contain this candidate hook. Other existing estimate proposals remain intact, as does separate SSR work for issue515.

## Acceptance limits

The executor is offline. No Electron application, IPC session, recording, FFmpeg process, build, package installation, test, or fixture was run or added. Native timing behavior, UI rendering, and upstream integration remain unverified. This patch does not establish estimate accuracy, resolve every candidate limitation, close issue172, or claim its reward.

The current `contributing.md` describes installing dependencies, starting the application, and optionally packaging it; those steps remain unperformed. `SOURCE.json` records source pins and the inspected caller. No upstream branch, pull request, comment, dependency, workflow, conversion algorithm, or account was modified. The upstream MIT license and Wulkano attribution are retained.
