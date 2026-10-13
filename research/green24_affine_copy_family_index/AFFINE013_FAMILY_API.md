# Signed {0,1,3} copies in a fixed integer host

This package gives exact navigation through **all 524,288 subsets of {1,...,19}**, grouped by their size and their number of signed, nondegenerate affine copies of {0,1,3}. It contains all 102 host patterns and 283 size/count buckets. Among nine-element host subsets, the maximum copy count is 19, attained by 52 subsets. Exactly 17 nine-element subsets contain no copy, while every ten-element subset contains at least one.

These are exhaustive results inside the declared host. They do not compute the unrestricted maximum over arbitrary integer sets, prove the asymptotic constant in Green 24, or claim novelty, a best-known value, prize progress or sponsor acceptance.

## Definition and source coverage

For a finite integer set A, the counted objects are ordered pairs (x,y) in A×A such that x differs from y and 3y−2x belongs to A. Equivalently, a=x and d=y−x specify the three values a,a+d,a+3d, with d a nonzero integer of either sign. The exclusion of x=y removes degenerate copies. The roles are fixed: this is not a count of all six permutations of a triple, not an unsigned distance pattern, and not a count divided by two. The array indices in a pattern record identify x, y and z in those roles.

Ben Green's [100 Open Problems, Problem 24](https://people.maths.ox.ac.uk/greenbj/papers/open-problems.pdf#problem.24), printed page 15, asks for the maximum number of affine translates of {0,1,3} in an n-element integer set. The passage attributes the question apparently to Ganguly, heard from Robin Pemantle, and refers to James Aaronson's work. The abbreviated author passage does not independently specify signed multipliers, ordered-pair counting or degeneracy; the precise implementation convention comes from the fully read formal source.

The [FormalConjectures Green24 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/GreensOpenProblems/24.lean) was returned in full at its default ref: 3,240 UTF-8 bytes, Git blob `da8df510d00d8b01069b320cefe680b7a241cfb2`. Its definition is exactly the ordered-pair condition above. It defines gamma as the limsup of the unrestricted maximum divided by n squared and records gamma=1/3 as research open. The main function question is also annotated open. Separate bound variants are annotated solved; the trivial upper-bound variant contains a proof script, whereas the other displayed bound bodies remain placeholders. No Lean code, Aaronson proof, Hardy–Littlewood argument, extremizer table, or external status claim was reviewed or executed. The text hash does not by itself identify an immutable upstream commit.

## Identified input premises

The new input file copies the nineteen literal host integers from [#31808](https://github.com/woahwhattheheck/commons/pull/31808), `research/green2_affine_sum_avoiding_index/input_affine19.json`, blob `e84a704410acfea6209d6b09a4afe271a0e00a4f`. It does not consume or repeat that package's restricted-sum graphs or subset-family calculation.

The binomial accounting row is copied from `/pascal/19` in the accepted [#31787](https://github.com/woahwhattheheck/commons/pull/31787) artifact `research/erdos10_selected_prime_binary_minima/bit70_minima_index.json`, blob `a781a03e3113d1bf6ecfe968178a33248d6dcacf`. It supplies the known total number of host subsets of each size. Its recurrence is not rerun. No earlier AP, sum-product, Sidon or affine restricted-sum calculation is used as a new result here.

The isolated `input19.json` is 1311 bytes, blob `537a9e3f260243eec428cca2599b60ebfbc58a0d`. Source and input were banked before the one construction. The complete output was banked before opening the reader. Each reader response was retained immediately. Neither stage failed or was repeated.

## Complete construction and counting argument

The compiler examines every ordered pair of distinct host positions once, computes the exact integer z=3y−2x, and retains the pattern when z is a host element. BigInt is used for these integer values. Each retained pattern contains its three role indices, a and signed d, full host mask, largest index and the two lower indices as a mask. Repeated numerical elements are disallowed by the input's strictly increasing host requirement.

For each nonempty subset mask M, let h be its highest selected index and P=M without h. Copies already contained in P remain. The new copies are precisely the saved patterns whose highest index is h and whose other two indices lie in P. Thus

    score(M) = score(P) + number of saved h-patterns with lower pair contained in P.

Every pattern has one highest index, so this recurrence neither omits nor duplicates a counted ordered pair. The cardinality recurrence is |M|=|P|+1. Increasing numerical mask order visits P before M. Starting with the empty subset, the loop visits each mask exactly once. Each result enters exactly one bucket (cardinality, copy count), preserving increasing mask order inside each bucket.

All 524,288 memberships are retained in the buckets, so both the cardinality and score of every mask can be recovered. Temporary score/cardinality arrays are represented by this complete lossless bucket partition; they are not an additional omitted family. Each size total agrees with the supplied binomial row, a twenty-row accounting comparison rather than a recomputation of that row.

| Construction work | Actual value |
|---|---:|
| Ordered-pair checks / exact pattern values | 342 / 342 |
| Signed host patterns | 102 |
| Subset rows / bucket memberships | 524,288 / 524,288 |
| New lower-pair membership checks | 5,692,272 |
| Positive score increments | 1,423,068 |
| Cardinality increments | 524,287 |
| Size-accounting comparisons | 20 |
| Prior graph / Pascal / AP work | 0 / 0 / 0 |

The implementation accepts a strictly increasing integer host of size 1 through 20. The actual input is size 19. It uses exact Number masks of at most twenty bits, Uint16 scores (at most n(n−1)), and Uint8 sizes. The full family is exponential in host size; this is a bounded finite index, not an asymptotic algorithm improvement.

## Exact finite extremal profile

| Subset size | Number of subsets | Minimum copies | Minima | Maximum copies | Maxima |
|---:|---:|---:|---:|---:|---:|
| 0 | 1 | 0 | 1 | 0 | 1 |
| 1 | 19 | 0 | 19 | 0 | 19 |
| 2 | 171 | 0 | 171 | 0 | 171 |
| 3 | 969 | 0 | 867 | 1 | 102 |
| 4 | 3,876 | 0 | 2,522 | 2 | 278 |
| 5 | 11,628 | 0 | 4,031 | 4 | 201 |
| 6 | 27,132 | 0 | 3,281 | 7 | 80 |
| 7 | 50,388 | 0 | 1,272 | 11 | 2 |
| 8 | 75,582 | 0 | 235 | 14 | 125 |
| 9 | 92,378 | 0 | 17 | 19 | 52 |
| 10 | 92,378 | 1 | 2 | 24 | 68 |
| 11 | 75,582 | 4 | 2 | 30 | 42 |
| 12 | 50,388 | 9 | 2 | 37 | 16 |
| 13 | 27,132 | 16 | 2 | 44 | 24 |
| 14 | 11,628 | 25 | 2 | 52 | 18 |
| 15 | 3,876 | 34 | 1 | 61 | 8 |
| 16 | 969 | 48 | 2 | 70 | 8 |
| 17 | 171 | 63 | 2 | 80 | 6 |
| 18 | 19 | 81 | 2 | 91 | 2 |
| 19 | 1 | 102 | 1 | 102 | 1 |

The first nine-element maximum in saved order is {1,2,3,4,5,6,7,8,10}, with 19 copies. All 52 nine-element maxima are exported. The two ten-element minima, each with one copy, are {1,2,3,6,9,10,11,17,18,19} and {1,2,3,9,10,11,14,17,18,19}. All 17 largest copy-free subsets are exported. These statements use the fixed host; they do not say that arbitrary ten-element integer sets must contain a copy.

## API and order

```js
const fs = require('node:fs');
const {openIndex} = require('./affine013_family_index.cjs');
const m = JSON.parse(fs.readFileSync('snapshot_manifest.json', 'utf8'));
const buckets = m.shards.flatMap(s =>
  JSON.parse(fs.readFileSync(s.path, 'utf8')).buckets);
const saved = {...m.metadata, buckets};
const reader = openIndex(saved);
const maximumNine = {size: 9, min_copies: 19, max_copies: 19};
const all = reader.page('0', 52, maximumNine);
const first = all.records[0];
const inverse = reader.rank(first.mask, maximumNine);
const signedImage = reader.affine(first.mask, '-1000000000000000000007', '31');
```

The example documents ordinary CommonJS reuse. No Node CLI, native executor or filesystem command was run for this delivery; unchanged source was loaded in V8.

| Method | Contract |
|---|---|
| `compile(input)` | Build signed patterns, subset scores and complete buckets once. |
| `openIndex(saved, caches?)` | Open complete saved buckets and optional complete condition caches. |
| `summary()` | Full minimum/maximum profile by subset size. |
| `count(options)` | Count a declared size/score/required/forbidden family. |
| `select(rank, options)` | Selected mask, original host indices/values, bucket and count. |
| `rank(mask, options)` | Membership and inverse rank with reason for exclusion. |
| `page(start, limit, options)` | At most 1,000 records and exact next-page position. |
| `profile(mask)` | Locate the saved cardinality/score bucket of a mask. |
| `occurrences(mask)` | Return all saved pattern records contained in the mask. |
| `affine(mask, scale, shift)` | Evaluate points and pattern roles at integer scale≠0 and integer shift. |
| `bucket(id)`, `pattern(id)` | Full identified saved record. |
| `caches()`, `work()` | Full condition caches and explicit fresh-reader counters. |

Options are `size` (optional exact cardinality), inclusive `min_copies` and `max_copies`, plus distinct host-index arrays `require` and `forbid`. Indices are zero-based, so index 0 denotes value 1 and index 18 denotes value 19. Required and forbidden indices may overlap; the resulting family is empty. Reversed score bounds also give an empty family. Invalid indices, duplicate indices, unsafe numeric integer values and out-of-range ranks are rejected.

The complete order is increasing size, then increasing copy count, then increasing numerical host mask. A restricted family inherits that order. It is not lexicographic order of the selected integer lists or increasing numerical mask across different scores. Rank is zero-based; exact decimal strings or BigInt are accepted, with safe Numbers also permitted. Pages allow the endpoint rank equal to the family count and then return no records.

A condition cache stores segments referring to the original bucket IDs. Unconditioned segments directly reuse all bucket members. Required/forbidden conditions store exact qualifying index positions within those lists and cumulative segment starts. The reader scans saved masks, never recalculates their scores. Rank performs binary searches in saved sorted memberships. Opening trusts the saved mathematical records and does not independently authenticate their construction.

For integer scale lambda≠0 and shift tau, the map t↦lambda*t+tau is injective, and 3(lambda*y+tau)−2(lambda*x+tau)=lambda*(3y−2x)+tau. Hence the signed-copy count is preserved exactly. Negative scaling reverses the signs of d, which is why both signs belong to the model. This elementary affine invariance is a property of the declared finite input, not a reduction of the unrestricted extremal problem to this host.

`affine` computes only the requested selected values and the contained pattern records. It supports arbitrarily large signed integer parameters within ordinary BigInt resource limits. It does not enumerate all integer sets, permit scale zero, or add arbitrary rational-scale conventions.

## Actual first reader

`saved_reader_queries.json` retains **65 complete responses**, including 36 exact rank/select inverse matches. It exports every maximum at sizes 7, 9, 10, 12, 16, 18 and 19; all 17 copy-free nine-element subsets; both one-copy ten-element subsets; rank 300000 of the full family; complete occurrence records for one maximum and the full host; and two huge signed affine images.

| Condition | Exact count |
|---|---:|
| Size 9, require values 1 and 19 | 19,448 |
| Size 9, count 19, require values 1 and 19 | 4 |
| Size 9, count 19, forbid value 10 | 10 |
| Size 9, no copies, require value 1 | 15 |
| Size 10, require 1 and 19, forbid 10 | 12,870 |
| Require and forbid value 1 | 0 |

The actual negative affine scale is −(10^60+7), with shift 10^100+31, applied to the first nine-element maximum. It retains 19 complete transformed patterns. The actual positive scale is 10^50+3, with shift −10^90, applied to the first copy-free nine-element set. Its zero-pattern outcome follows from the same saved family rather than a new pattern search.

| Fresh reader work | Actual value |
|---|---:|
| Complete family caches | 16 |
| Saved bucket scans | 4,245 |
| Saved mask scans | 184,877 |
| Condition bit checks | 369,754 |
| Cumulative additions | 338 |
| Cache hits | 210 |
| Binary-search steps | 2,602 |
| Lookup bucket probes | 308 |
| Popcount steps | 372 |
| Materialized host values | 1,784 |
| Saved pattern scans | 408 |
| Affine multiplications / additions | 37 / 18 |
| New pattern values / subset scores / histogram | 0 / 0 / 0 |

These counters describe their named work, not all instructions or a runtime benchmark. Conditional filtering, popcounts for rank lookup and affine arithmetic are fresh query work, explicitly distinguished from rebuilding the score table.

## Complete storage and custody

The full compact JSON snapshot is 3590367 bytes, blob `48bc966d91074881868b815fc72123118be8d61f`. The manifest carries metadata, all patterns, summary and work counters; eight complete bucket shards carry every membership exactly once. Serializing the metadata and concatenated buckets in the original field order reproduced the entire snapshot byte-for-byte. This was a structural byte comparison, not a replay of pattern arithmetic, subset scores or histogram construction.

To reproduce that identity, form keys in this order: `schema`, `input`, `order`, `patterns`, `buckets`, `summary`, `work`, then use `JSON.stringify(snapshot) + '\n'`. JSON property order does not affect `openIndex`, but it matters to the recorded byte hash.

| File | Bytes | Blob |
|---|---:|---|
| `affine013_family_index.cjs` | 8802 | `f385264bf93a94e71314bb8550be26e041f390cc` |
| `input19.json` | 1311 | `537a9e3f260243eec428cca2599b60ebfbc58a0d` |
| `snapshot_manifest.json` | 32561 | `6e0d94556965b8fe2900fb9431f15e088830470d` |
| `buckets_00.json` | 281308 | `4cadd44655fa3ff5da2d96c9e58c5b4eb360ce5e` |
| `buckets_01.json` | 334329 | `422b000471bd8306e179b89536ebff7574d4d7df` |
| `buckets_02.json` | 508689 | `6703c5ac4cfec82d8bee79185c6f3c4b67b52ee8` |
| `buckets_03.json` | 628861 | `9c8f5b8b86f1c695e8421c1c5d6974ddafb5db35` |
| `buckets_04.json` | 634618 | `ca4f5df3ec3701afbe6bd229c7d26907554448ec` |
| `buckets_05.json` | 523169 | `28ce813290769e876c55a2b0e20f4ea363cd6a56` |
| `buckets_06.json` | 351204 | `cff4fd76693d12193419c1b1e1261cc47c913678` |
| `buckets_07.json` | 312715 | `dbbd89c57d996f5ce1c666bcf8e1eb6858ae7b1d` |
| `saved_reader_queries.json` | 227931 | `41e7a2760411b48909b132bcb3a388e91b0c5f11` |
| `saved_condition_caches.json` | 186577 | `040248772e1babbf7826c157a091988284553f82` |

The output is complete for the fixed host, with no sampled family members or omitted conditional cache entries. No failed invocation, missing response, accepted-calculation replay, source-proof review, or sponsor action is part of this package. Its exact finite maximum and minimum values remain separate from the unrestricted Green24 function and its asymptotic conjecture.
