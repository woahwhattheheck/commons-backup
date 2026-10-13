# Collect Flow companions for direct file inputs

The CLI accepts files as well as folders. In the existing package-definition proposal, naming a JavaScript file directly can produce no discovered file: findFiles sees an adjacent .js.flow, suppresses the .js input, and relies on an independent directory visit to enqueue the companion. Both dependency crawling and definition crawling consume this discovery list.

This follow-up queues the supported .js.flow companion through the existing replacement/deduplication branch before returning. Companion preference also requires a regular file with the extension the scanner recognizes. A directory named example.js.flow, or an unsupported example.jsx.flow/example.jsm.flow sibling, therefore no longer suppresses a supported runtime source.

## Integration

Apply `change.patch` within the existing [gajus/flow-runtime PR307](https://github.com/gajus/flow-runtime/pull/307), after reconciling its current head. The exact preparation base is `dd10a00825c58de112fca52977b4a2439583b543`; the original findFiles blob is `11e5ac7788075dd19bff8a78448310bab2ce5167`. Complete before and after sources are included. A changed source must be reconciled rather than overwritten.

The original proposal and package-module implementation remain credited to landeqiming666. PR288 by apples-kksk covers basic discovery; PR297 by ncthuc2004 is closed and unmerged. This packet does not replace those submissions or assert ownership of their rewards.

## Source reasoning and limits

- Direct supported JavaScript input plus a regular .js.flow companion now adds the companion even when no parent directory was requested.
- The existing definition branch removes a previously collected runtime sibling and adds the definition only if absent, preserving exact-string deduplication across repeated inputs and later directory visits.
- A missing, non-regular, or unsupported companion leaves the runtime input on the existing path. The existing stat failure fallback is retained.
- Only the recognized .js.flow convention is preferred. No new .jsx.flow/.jsm.flow parsing promise is made.
- stat follows symbolic links as before. No atomic filesystem snapshot, realpath alias deduplication, or protection against filesystem changes after stat is claimed.
- Package main fields, lib/index.js.flow entrypoints, subpath module identities, automatic node_modules discovery, and all of issue27's broader resolution semantics remain outside this repair. PR307's package-root implicit-module implementation is unchanged.

The actual GenerateCommand description explicitly says files or folders, forwards argv inputs to generateDefinitions, and that calls crawlTypeDependencies, which calls findFiles. crawlTypeDefinitions independently calls the same function for configured definition paths. These source contracts make direct-file handling an existing production path.

## Validation state

Static source inspection and exact before/after text comparison only. No application execution, package installation, compiler, native process, tests, fixtures, workflow, benchmark, or hosted acceptance was run. The original contributors' reported checks remain their own observations. Upstream integration/build/runtime acceptance and IssueHunt award/payment remain unclaimed.

This Commons packet changes no executable application or workflow in Commons; it retains an integration-ready production-source follow-up and the upstream MIT license.
