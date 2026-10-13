# Erdős 708: finite interval product-cover index

This package finds and navigates minimum-cardinality subsets of a positive consecutive interval whose product is divisible by the product of a supplied finite set.

For the retained set
\[
A=\{9,14,24,35,41,53,57,60\}
\]
and interval \(\{10^{12}+1,\ldots,10^{12}+60\}\), the exact minimum is **6**, with **44 minimum subsets**. Offsets **23, 37 and 50** occur in every minimum subset. The first lexicographic witness is \([2,8,23,34,37,50]\); the last is \([23,37,41,44,48,50]\).

## Files

| File | Purpose |
|---|---|
| [interval_product_cover.cjs](interval_product_cover.cjs) | Pure CommonJS/BigInt compiler and saved-reader API |
| [INTERVAL_PRODUCT_COVER_API.md](INTERVAL_PRODUCT_COVER_API.md) | Complete derivation, source conventions, API, bounds and execution account |
| [retained_set_interval60_cover.json](retained_set_interval60_cover.json) | Complete 3024-state suffix/prefix tables, all 44 witnesses, every participation count and saved-reader query |

The data file is **586,661 bytes**. Its unformatted snapshot is 395,683 characters. Source identity: `c4c9fa37b0e08d5caa676ce33a37ab714da0a800`. Data identity: `3f2cfd8bf2794b96cce0bfef224c7747cd7feee5`.

## Use the saved result

With the source and data texts already supplied to a connected V8 context:

```js
const moduleObject = { exports: {} };
new Function("module", "exports", sourceText)(
  moduleObject, moduleObject.exports
);
const artifact = JSON.parse(datasetText);
const index = moduleObject.exports.openRetainedIntervalProductCover(
  artifact.snapshot
);

index.summary();                    // minimum 6, count "44"
index.page(0, 44);                   // every minimum witness
index.participationPage(0, 60);      // all interval positions
index.budget(16);                    // exact and at-most semantics
index.padToSize(16, 22);             // one explicit larger cover

const x2 = 1000000000000n + 786566894400n * 10n ** 50n;
index.viewAtOffset(x2).select(43);
```

The period is \(P=\prod A=786566894400\); it is valid because all relevant capped prime valuations are unchanged by translation through \(P\). It is not asserted to be the least period. The actual fresh reader made 12 queries, including this larger translated interval, with zero new target factorization, candidate valuation or dynamic-programming construction. It still performs exact arithmetic for requested product witnesses.

## Scope and attribution

[Erdős’s 1992 author paper](https://hrj.episciences.org/125/pdf), pages 34–35, gives the distinct-set and positive-interval question and credits Erdős–Surányi. This API explicitly minimizes cardinality. An at-most budget \(h\) succeeds iff \(h\ge6\) for this input; an exact-size query succeeds iff \(6\le h\le60\). The source’s literal wording is not silently replaced, and no general \(g(n)\) bound or mathematical novelty is claimed.

The input set comes from accepted Commons [#31157](https://github.com/woahwhattheheck/commons/pull/31157); the prime/least-factor premise comes from [#31426](https://github.com/woahwhattheheck/commons/pull/31426). Their searches and sieve were not repeated. Full paths, fields, merge identities and blob identities are retained in the guide and data.

The compiler supports at most 64 interval elements and 4096 prime-deficit states. The loader checks structure and queried path identities; it does not independently authenticate the supplied prime premise or every stored recurrence. See the guide for the exact encoding and assurance boundary.
