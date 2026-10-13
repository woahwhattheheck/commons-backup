# Invoke the DOM stream method in the Most migration example

The testing-usage example in nwinkelman2's [Cycle.js PR1033](https://github.com/cyclejs/cyclejs/pull/1033) passes `sources.DOM.select(':root').elements` to `tap`. The actual current `MainDOMSource` exposes `elements()` as a method. Calling it builds and adapts the root-element stream; reading it alone supplies a function instead.

The one-line patch adds the missing invocation. It preserves the existing operator selection, scheduler, application setup and disposal example. The runtime migration adapters and package configuration are unchanged.

## Integration and source

Apply `elements-invocation.patch` to `docs/content/api/most-run.md` in the existing contribution after reconciling its current head. The source is PR1033 head `982d20bdc9201d99251e5e708d58a2fa0c459595` in `nwinkelman2/cyclejs`, README blob `976f92f0e07493b0522f096f7c4851d7d01e53ea`. Its base is upstream master `5ece2a48c3659538208da3dc8d43a142bc0d91a7`.

The caller contract is `dom/src/MainDOMSource.ts` blob `0b90973d3634d3c1f445a073b5208fa31e80571a` at that base: `select(':root')` returns another MainDOMSource, and `elements()` calls the configured stream adapter. The complete migration source `most-run/src/index.ts` was also read; it installs the Most adapter through `setAdapt`.

The packet retains original and corrected documentation, the patch, source bindings and the exact upstream MIT notice. The existing author's full migration remains intact. Issue845 remains open; historical PR881 is closed/unmerged. This source correction does not establish acceptance of the broader migration.

## Validation boundary

Validation is static inspection of the complete actual documentation and caller source. No Most/xstream execution, TypeScript compiler, browser, test, fixture, build, dependency installation or workflow ran. The upstream guide's build and package-check workflow remains unperformed, and the PR author's reported checks were not replayed.

Two independent dependency-source qualification reads failed: the xstream tags collection was rejected by the connector's URL allowlist with HTTP400, and the Most core contents lookup at ref1.4.2 returned404 for an absent commit. Those exact routes remain held without retry or alternate retrieval. A separate disposal-lifecycle hypothesis was not promoted into a runtime change or a verified finding.

This Commons packet is not an upstream submission, migration completion, bounty award or payment claim.
