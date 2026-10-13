# AP-free families on finite integer intervals

This package stores every subset of an interval that avoids an arithmetic progression of a specified length, together with exact counts by cardinality and navigation by rank. Earlier interval roots remain intact when the family is extended.

The recorded three-term case contains **140,840 admissible subsets of [1,25]**. The maximum cardinality is **10**, attained by **33 sets**. The complete list of those 33 sets is retained in reader session 2, event 3 of the evidence record.

| File | Contents |
|---|---|
| [ap_free_families.cjs](ap_free_families.cjs) | Dependency-free CommonJS family compiler and saved reader |
| [AP_FREE_FAMILIES_API.md](AP_FREE_FAMILIES_API.md) | Completeness argument, API, storage semantics, execution evidence and boundaries |
| [three_term_families.json](three_term_families.json) | Complete final record, all actual receipts and literal custody comparisons |

## Use the saved family

```js
const { openAPFamily } = require("./ap_free_families.cjs");
const evidence = require("./three_term_families.json");
const family = openAPFamily(evidence.record);

const counts = family.histogram({ n: 25 });
const maxima = family.pageSets({ n: 25, size: 10, offset: 0, limit: 64 });
const witness = family.findProgression({ n: 25, values: [1, 13, 25] });
```

This example describes a future reader session. The delivered record already contains the 20 actual reader calls documented in the guide; publication did not run them again. Opening copies and checks the saved structure. It does not rebuild the family or independently authenticate an imported record's completeness.

The cardinality histogram at 25, indexed from size 0 through size 10, is:

```json
[1,25,300,2156,9706,26996,44290,39332,16061,1940,33]
```

The first maximum set in the implementation's descending-element, low-before-high order is `[1,2,5,7,11,16,18,19,23,24]`. All earlier members retain their whole-family and fixed-cardinality ranks after extension. Reflection and nonzero integer affine maps are available without constructing another interval family.

## Actual construction and resource boundary

The source was frozen before execution. One constructor created the empty-interval family; the first advance completed 18 points. A new session opened that saved record and requested ten more points. It completed seven, ending at 25.

Point 26 reached the fixed 50,000-coefficient storage limit. The next polynomial needed seven entries when only four slots remained. The entire incomplete point was rolled back, including its 3,131 temporary nodes, 1,595 polynomial rows, 11,527 coefficients and 11 completed filters. The completed family through 25 was preserved. No complete family for 26, 27 or 28 is reported, and that attempted point was not retried.

The saved final core contains 10,630 nodes, 5,618 polynomial rows, 38,469 coefficients and all 144 three-term progression constraints through 25. Construction uses persistent decision diagrams and cardinality polynomials; it does not enumerate all candidate subsets.

A fresh saved reader answered 20 queries, including all 33 maxima, cross-interval rank preservation, a reflection, a large exact affine image, a rejected member with its progression witness, and pages of the stored structure. Its receipts record zero family constructions, constraint-filter replays and polynomial-recurrence replays. Import checks and the actual selected-set traversal costs are reported separately in the guide.

## Scope and provenance

This is a complete finite family and reusable navigation interface. It does not establish an asymptotic counting formula, a new extremal record, or a prize result. Generic lengths 4 through 8 are implemented but were not executed in this contribution. The final export containing all 20 query receipts was not reopened again.

Primary mathematical context comes from [Leng, Sah and Sawhney](https://www.mit.edu/~asah/papers/2402.17995.pdf), [Morris, Ortega and Rué](https://arxiv.org/pdf/2607.17746), and [Ben Lynn's ZDD notes](https://crypto.stanford.edu/pbc/notes/zdd/zdd.html). The guide states the exact use and date of those sources and derives the interval-extension argument.

Operation: `ERDOS142-AP-FREE-FAMILY-ZDD-20261004-7CA6`.
