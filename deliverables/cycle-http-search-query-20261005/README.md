# Preserve the GitHub search text as one query parameter

The current Cycle.js GitHub search example inserts user input into the `q` URL parameter using `encodeURI`. That function preserves URL delimiter characters, so a search containing `#` can become a fragment, and `&` can separate query parameters. The actual HTTP driver passes the constructed URL directly to Superagent.

This one-line patch uses `encodeURIComponent` for the parameter value. It keeps those characters within the search text rather than letting them alter the URL structure. Debouncing, empty-input filtering, categories, request scheduling, rendering and driver behavior remain unchanged.

The [ECMAScript encodeURI algorithm](https://tc39.es/ecma262/multipage/global-object.html#sec-encodeuri-uri) leaves reserved delimiters unescaped; [encodeURIComponent](https://tc39.es/ecma262/multipage/global-object.html#sec-encodeuricomponent-uricomponent) does not add that reserved-character exemption. The effect described here is static reasoning from those algorithms and the actual caller, not an executed request or a claim about particular GitHub search results.

## Source and integration

This patch targets current upstream master `5ece2a48c3659538208da3dc8d43a142bc0d91a7` in `cyclejs/cyclejs`. The exact source is `examples/intermediate/http-search-github/src/main.js`, blob `6c1f0ff1e973629b07236d7466e398bb76a9b621`. The packet includes that original, the full corrected file, the one-hunk patch, source bindings and the exact upstream MIT notice.

Existing [PR1002](https://github.com/cyclejs/cyclejs/pull/1002), by dicnunz, addresses [issue233](https://github.com/cyclejs/cyclejs/issues/233) with per-response error recovery before flattening. Its retained head `529837028990bbf568ed538b7e52d6c353a69a84` still uses the same incorrect query encoder. Preserve that contribution; this independent line can be composed with it after reconciling the current head and surrounding source. It does not replace or claim completion of the error-recovery work.

## Validation boundary

The complete current example, complete PR1002 example, complete current HTTP driver and issue discussion were inspected. PR1002's author-reported checks remain that author's reports. No JavaScript evaluation of the example, HTTP request, browser, TypeScript compiler, dependency installation, test, fixture, build, workflow or native execution occurred. The executor remains offline.

The upstream contribution guide's build, package checks and commit workflow remain unperformed. This Commons source packet is not an upstream submission, runtime acceptance, issue closure, bounty award or payment claim.
