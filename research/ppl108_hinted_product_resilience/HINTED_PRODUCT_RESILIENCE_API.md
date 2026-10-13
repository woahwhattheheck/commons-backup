# Staged Boolean products and intermediate-deletion profiles

This package compiles exact witnesses for a finite Boolean product and every deletion subset of its intermediate layer. It separates preparation of the left matrix, attachment of a hint matrix, and saved output-column queries. The retained 13-by-7 instance uses seven already published codeword agreement masks and a transpose hint. It adds finite sensitivity and conditioned failure-family navigation; it makes no asymptotic matrix-multiplication claim.

## Source formulation and scope

Jan van den Brand, Danupon Nanongkai and Thatchaphol Saranurak, *Dynamic Matrix Inverse: Improved Algorithms and Matching Conditional Lower Bounds*, arXiv:1905.05067v1 (May 13, 2019), Definition 5.1, give the v-hinted matrix-vector problem in three phases. With t=n^tau and 0<tau<1, phase 1 receives an n-by-t matrix M; phase 2 receives a t-by-n matrix V; phase 3 receives an index i and returns column i of MV. Products are over the Boolean semiring. Conjecture 5.2, for polynomial phase-1 preprocessing, asserts a phase-2/phase-3 lower-bound tradeoff: for every constant epsilon>0, phase 2 requires Omega(n^(omega(1,1,tau)-epsilon)) time or phase 3 requires Omega(n^(1+tau-epsilon)) time.

The definition and conjecture were read in the primary paper, printed pages 26–27. This is attribution to that paper, not an exhaustive current-status survey. The formulation is distinct from the separate OMv problem of receiving a sequence of online vectors. No proof of the conjecture was inspected or supplied here.

Primary locators:

- https://arxiv.org/abs/1905.05067
- https://arxiv.org/pdf/1905.05067

The finite API accepts integer dimensions rather than an asymptotic parameter tau. Its actual n=13, t=7 input has V=M transpose. This is a structured symmetric special case. It does not supply a generic unknown hint, a worst-case phase-2/phase-3 tradeoff, a subcubic algorithm, or a solution of the sponsor's general question. The intermediate-deletion feature is this package's declared finite extension of the formulation.

## Exact input and lineage

The seven columns of M are the saved agreement masks of the seven nearest codewords from Commons #31621. That previous artifact's saved-reader blob is:

`a02f4413b414c6248231fd8cdca28e59e52c23f3`

The source polynomial, field, codeword enumeration, and distance classification are premises and were not rerun.

| Intermediate label | Saved coefficient rank | Saved agreement mask |
|---:|---:|---:|
| 0 | 512 | 1923 |
| 1 | 3789 | 1582 |
| 2 | 10171 | 6229 |
| 3 | 10377 | 858 |
| 4 | 13434 | 6313 |
| 5 | 20085 | 7434 |
| 6 | 27478 | 2530 |

Rows of M are the thirteen coordinate positions. Character j of a row string is intermediate j; the first character maps to the least significant mask bit. The literal M is:

```text
1010100
1101011
0110000
0101110
0011000
0100101
0011001
1000101
1001011
1101000
1100010
0010111
0010110
```

The literal V, constructed as the declared transpose after the left preparation was saved, is:

```text
1100000111100
0111010001100
1010101000011
0101101011000
1001010100011
0101000010111
0100011110010
```

Left-input blob: `f1524b505e09a141b94605115d4e091493664205` (750 UTF-8 bytes).
Hint-input blob: `9434d1c51a5eaa4839e6fa096415644568c783a1` (354 bytes).

The standalone phase-1 envelope retains its complete input and prepared row masks. The phase-2 envelope embeds the complete left and hint inputs and the full snapshot. No output-column index was supplied to hint attachment.

## Witness and deletion conventions

There are three typed layers: source rows r, intermediate labels j, and target columns c. Numerically equal labels in different layers do not identify vertices. Entry (r,c) has a two-edge path through j precisely when M[r,j]=V[j,c]=1. Its witness set is

```text
W(r,c) = { j : M[r,j] = 1 and V[j,c] = 1 }.
```

Thus (MV)[r,c]=1 if and only if W(r,c) is nonempty. For a deleted intermediate set D, the surviving witnesses are exactly W(r,c) minus D. This proves the residual-witness rule: deleting an intermediate removes its two-edge paths and changes no other intermediate's membership. No source or target may be deleted by this API.

The snapshot enumerates every mask D from 0 through 2^t-1. For each it retains all n^2 residual witness masks, all n output-column masks, and the sorted entries that were positive at D=0 but become zero. Consequently every allowed deletion subset has exactly one profile, and selecting the minimum lost-entry count among profiles of a fixed weight establishes the reported finite optima.

Entry identifiers are r*n+c. Counts use **ordered row-column positions, including the diagonal**. For the actual symmetric product, (r,c) and (c,r) still count as two positions when r differs from c. Neither matrix symmetry nor identical resulting products identifies different deletion sets.

Bit j of a deletion mask means intermediate j is removed. Bit r of an output-column mask means row r is reachable. Failure families are ordered by numerical deletion mask. Their ranks are zero-based. The word “failure” in a query means the supplied deletion condition, not necessarily total disconnection.

## Retained construction

Executed source: `3aa3a4893177b96d9e7e46b4b8e144ab5b7142ac` (10,155 bytes).

The source and the left input were saved before phase 1 ran. Phase 1 read 91 entries and formed 13 row masks. Its complete 1,022-byte envelope is `db0319604a28374338acf3e060a671f830ea53ab`. Only after that save was the declared hint input prepared and saved. Hint attachment then ran once.

Phase 2 read 91 hint entries, formed 13 hint-column masks, and performed 169 base witness intersections. It retained 153 positive base entries. Building all 128 profiles performed 21,632 residual witness intersections. The complete 95,969-byte phase-2 envelope is `080b79d39e38b92d51e89c61593e316cd90454c9`.

Base output-column masks are:

```json
[8191,8191,7807,8191,7007,8175,7167,8171,8187,2047,8111,7679,7679]
```

There are 45 nonempty (deletion weight, lost-entry count) buckets. At each fixed weight the minimum loss and all attaining deletion masks are:

| Deleted intermediates | Minimum lost ordered entries | All attaining masks |
|---:|---:|:---|
| 0 | 0 | 0 |
| 1 | 6 | 64 |
| 2 | 18 | 96 |
| 3 | 36 | 56, 97, 98, 104 |
| 4 | 54 | 57 |
| 5 | 82 | 103, 121, 122 |
| 6 | 117 | 63, 95, 111, 119, 123, 125, 126 |
| 7 | 153 | 127 |

These are optima over this complete finite deletion family. They are not approximation or complexity results for arbitrary graphs.

## Reusable module contract

The CommonJS module has no external dependencies and exports `LEFT`, `SCHEMA`, `LIMITS`, `prepareLeft`, `attachHints`, and `openIndex`.

- `prepareLeft(left)`: left is an array of n binary row strings of common length t. It receives no hint matrix or query index and returns the original rows, packed row masks and phase-1 work.
- `attachHints(prepared, right)`: right is t binary row strings of length n. It clones the prepared input, packs right columns, builds the product witnesses, and exhausts intermediate-deletion masks. It receives no selected output-column index.
- `openIndex(snapshot)`: clones and structurally checks a saved snapshot, then exposes the reader below. It does not call either construction function.

Inputs require safe integer dimensions 2<=n<=20 and 1<=t<=min(12,n-1), with 2^t*n^2<=2,000,000. Row strings must contain only 0 and 1. These caps keep mask operations in the supported JavaScript integer range. They are runtime limits, not mathematical restrictions on Boolean products. Only the actual n=13, t=7 instance was executed; larger supported branches were source-inspected.

The preparation loader checks schema, dimensions and mask ranges, but it does not independently rederive saved row masks from their strings. Prepared inputs therefore carry a provenance premise. Likewise, the saved reader checks array shapes, mask ranges, profile ordering, and sorted unique lost-entry identifiers. It does not recompute all intersections, prove the bucket or optimum summaries, or certify an externally altered snapshot. Structural opening is distinct from mathematical verification.

| Reader method | Result |
|:---|:---|
| `summary()` | Dimensions and saved construction work |
| `matrices()` | Literal left and hint rows |
| `column(c, deleted=0)` | Saved output mask and its row labels |
| `witness(r,c,deleted=0)` | Saved witness mask, intermediate labels and typed paths |
| `profile(deleted)` | Complete saved profile |
| `profilePage(start=0,limit=16)` | Brief profiles in numerical mask order |
| `buckets()` | All weight/loss buckets and their masks |
| `bestByWeight()` | Saved complete finite optimum summaries |
| `failures(condition={})` | Canonical condition and every admitted deletion mask |
| `failureSelect(condition,rank)` | A ranked admitted profile |
| `failureRank(condition,deleted)` | Its rank, or null if excluded |
| `failurePage(condition,start=0,limit=16)` | A page of admitted profiles |
| `conditions()` | All complete condition records built by this reader |
| `work()` | Saved-index and fresh-query counters |

A condition may contain `zero_entries` and `one_entries`, each an array of [row,column] pairs, and inclusive `min_weight`, `max_weight`, `min_lost`, `max_lost`. Default ranges are 0..t and 0..n^2. Entry lists are deduplicated and sorted. Unknown keys, invalid indices, reversed bounds, and invalid ranks are rejected. Requiring the same entry to be both zero and one yields an empty family. There are at most 128 distinct cached conditions, and page limits are 0..128.

A condition scans saved profiles and examines saved residual masks; this is new query work, even though it does not rebuild any product. Reusing the same canonical condition hits the cache. Rank uses binary search in its saved numeric-mask family. This implementation deliberately spends exponential time and storage in t: the construction performs O(2^t*n^2) profile work and retains that many witness cells. It does not meet a polynomial-preprocessing asymptotic requirement as t grows.

## Opening the saved record

The following is a user example, not an additional execution record:

```javascript
const fs = require('node:fs');
const { openIndex } = require('./hinted_product_resilience.cjs');
const saved = JSON.parse(fs.readFileSync(
  './nearest_word_resilience_certificate.json', 'utf8'
));
const index = openIndex(saved.snapshot);

index.column(0, 64);
index.witness(0, 0, 0); // intermediates 0, 2, 4
index.witness(0, 0, 21); // none survive
index.failures({ zero_entries: [[0, 0]] }); // 16 deletion sets
index.failureSelect(
  { min_weight: 3, max_weight: 3, max_lost: 36 }, 3
); // deletion mask 104
```

To construct a distinct authorized input, call `prepareLeft`, persist the complete prepared result, then supply `right` to `attachHints`. The library does not itself perform storage or enforce external custody; the retained execution above documents that separation for this instance. Opening saved data for navigation requires no construction call.

## Saved reader results and work

The fresh reader opened the banked phase-2 envelope and retained 37 complete responses, seven complete condition records, and its final counters. The 127,149-byte result is `008afc92c7551cef567f90f8aacf0ba98245a295`.

| Condition | Number of deletion sets |
|:---|---:|
| No positive base entry lost | 1 |
| Weight 3, loss at most 36 | 4 |
| Weight 4, loss at most 54 | 1 |
| Entry (0,0) zero | 16 |
| Entry (0,0) zero and (1,1) one | 15 |
| Entry (0,0) both zero and one | 0 |
| Loss at least 100, weight at most 6 | 7 |

For example, W(0,0)={0,2,4}; its mask is 21. Entry (0,0) vanishes precisely when those three intermediates are deleted, leaving four deletion bits free, consistent with 16 admitted masks. W(0,1)={0} and W(6,12)={2}; the retained witness responses return the corresponding typed paths.

The four best weight-three masks are [56,97,98,104]. Selecting rank 0 gives 56 and selecting rank 3 gives 104; mask 98 has rank 2, while mask 57 is excluded from that conditioned family. The complete responses, rather than these illustrations alone, delimit the query evidence.

Opening indexed 128 profiles and 21,632 saved witness cells. Fresh queries performed 179 profile lookups, six witness lookups, 896 saved-profile scans, 416 saved-entry lookups, seven condition creations, eight cache hits, and ten binary-search steps. Counters for new base intersections, residual intersections, and profile reconstruction are all zero. Decoding bits to requested labels and paths remains ordinary query arithmetic.

## Files

| File | Role |
|:---|:---|
| `hinted_product_resilience.cjs` | Source and reusable API |
| `left_preparation.json` | Complete phase-1 input and prepared record |
| `nearest_word_resilience_certificate.json` | Complete phase-2 inputs and all profiles |
| `saved_reader_queries.json` | All 37 outputs, seven conditions and work |
| `HINTED_PRODUCT_RESILIENCE_API.md` | Contract, argument, provenance and scope |
| `README.md` | Entry point |

The saved data establish only the identified finite staged construction and its complete intermediate-deletion family. They make no new lower-bound theorem, general online-matrix solution, current prize claim, or mathematical priority claim.
