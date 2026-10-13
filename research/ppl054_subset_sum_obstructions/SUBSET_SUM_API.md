# Finite subset-sum fibers and obstruction navigation

This package compiles every subset sum of a supplied finite positive-integer host, groups equal values, and extracts the inclusion-minimal supports of equal-sum relations. It classifies every host subfamily by whether all of its subset sums are distinct. A separate saved-table reader returns explicit collision witnesses and count, rank, select and page results without repeating subset additions or the collision search.

For the identified thirteen-element host, the maximum sum-distinct subfamily has **nine elements**, with **61 maximizers**. This is an exact fixed-host statement. It is not an optimum over all positive-integer sets.

## Mathematical conventions and source status

[Richard K. Guy, “Sets of integers whose subsets have distinct sums,” Annals of Discrete Mathematics 12 (1982), 141–154](https://www.math.u-bordeaux.fr/~ybilu/various/subset_sums.pdf), and [Tom Bohman, “A construction for sets of integers with distinct subset sums,” Electronic Journal of Combinatorics 5 (1998), R3](https://www.combinatorics.org/volume_5/pdf/v5i1r3.pdf), use distinct positive integers and the entire power set. The empty subset contributes zero. Each element is selected at most once, and sums from subsets of unequal cardinalities are compared. A fixed-cardinality Sidon or B3 property is not the same requirement.

Bohman's extremal function minimizes the largest element among all sum-distinct sets of a specified cardinality. The historical conjecture asserted one positive constant independent of the cardinality in a constant-times-2^n lower bound. These older sources supply definitions and attribution; their historical open-status language is not used as a current status claim.

The complete current [FormalConjectures Erdős 1 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/1.lean) read for this task explicitly marks that original assertion **false / research solved**. Its local main theorem remains a placeholder and it links an external formal proof. That external proof was not opened, checked or rerun here. The decoded source has independently computed Git-blob identity `1a47a3c69fad5d58c9ba47ce01dd0500637230ae`; the connector did not supply an immutable source commit, so this identity is not presented as a native repository pin. This package makes no independent global disproof or current frontier claim.

## Input and inherited arithmetic

The host, in index order 0 through 12, is

~~~text
[1,13,32,66,169,174,396,416,756,858,915,1016,1044]
~~~

The input comes from [Commons #31527](https://github.com/woahwhattheheck/commons/pull/31527), specifically:

- Path: `research/ppl168_b3_extensions/thirteen_seed_extensions.json`.
- Complete source blob: `1d2710d39c548add71f38ce76c68d90ed117237a`.
- Commit: `2da9af6333579e135ccec4733d1d56cfde420a20`.
- Fields: `input.values`, `snapshot.pair_rows`, and `snapshot.triple_rows`.

Only rows with strictly increasing indices are imported from the predecessor's sums with repetitions: 78 of its 91 pair rows and 286 of its 455 triple rows. Together with the empty sum and thirteen literal singletons, these provide 378 cells. Selecting and encoding those rows performs no pair or triple addition. The input retains every imported row and its origin. Their arithmetic values are identified premises; the new compiler does not establish them again.

The predecessor's B3 property is not needed by this calculation and was not reverified. In particular, a B3 premise by itself would not rule out unequal-cardinality subset collisions. The new saved fiber at 409 explicitly contains

~~~text
66 + 169 + 174 = 13 + 396 = 409.
~~~

These are disjoint subsets, of sizes three and two.

## Construction and proof

Write the ordered host as H={a_0,...,a_(n-1)} and encode subsets by numeric bit masks. A subset is sum-distinct when the map T ↦ sum(T), over all T contained in that subset, is injective.

### Complete sums

S(0)=0. A singleton sum is its literal value. For a missing nonsingleton cell, let b be its least set bit, representing index i, and use

~~~text
S(mask) = S(mask xor b) + a_i.
~~~

The smaller mask has already been handled. If complete low-order layers are supplied, they are imported without arithmetic. Induction on numeric masks proves all new sums exact conditional on those imported values. The actual instance needs precisely 8,192−378=7,814 additions.

All masks are grouped by exact BigInt sum. Fibers are sorted by sum, with masks increasing inside each fiber. Every unordered pair of different masks in one fiber is an equal-sum collision; the constructor examines all such pairs, subject to its explicit collision-pair budget.

### Cancellation and obstruction supports

For a collision A≠B, cancel their intersection:

~~~text
L = A \ B
R = B \ A
support = L union R = A xor B.
~~~

Then sum(L)=sum(R). Both sides are nonempty because the input values are strictly positive. The support is a genuine obstruction: every host subfamily containing it has two different subsets with the same sum.

Conversely, every failure of sum-distinctness has some colliding A,B. Their cancelled support is contained in the failing subfamily and is among the examined supports. Thus a subfamily is bad exactly when it contains at least one recorded support.

For each distinct support, the compiler retains the lexicographically least numeric pair (left mask, right mask), after ordering left<right. The saved equality is checked against the already available sums of these two masks. The field `fiber_pair_occurrences` counts all original unordered fiber pairs that cancel to that support; it does not count distinct sign assignments or claim that each support has only one relation.

### Minimal supports and all good subfamilies

Process masks in increasing order. Every one-element deletion has a smaller numeric mask. If any such deletion is already bad, inherit its minimal obstruction witness. Otherwise, if the current mask itself is a relation support, it is inclusion-minimal and becomes its own witness. If neither case occurs, the mask is good.

To justify completeness, any proper subset lies in a one-element deletion. Hence a proper bad subset would have been found there. This establishes both the minimal obstruction antichain and the complete good/bad classification.

A good mask is inclusion-maximal exactly when none of its immediate one-element extensions is good. The property is downward closed, so any larger good extension would imply an immediate good extension. Maximum cardinality is then the largest nonempty cardinality layer of the saved good family. Inclusion-maximal and maximum-cardinality are different notions; no matroid structure or greedy-optimality theorem is assumed.

## Complete actual results

| Quantity | Result |
| --- | ---: |
| Host elements | 13 |
| Subsets, including empty | 8,192 |
| Distinct subset sums | 3,759 |
| Unordered pairs in equal-sum fibers | 7,801 |
| Distinct cancelled relation supports | 185 |
| Inclusion-minimal obstruction supports | 64 |
| Sum-distinct host subfamilies | 6,047 |
| Largest sum-distinct cardinality | 9 |
| Number attaining that cardinality | 61 |
| Inclusion-maximal good subfamilies | 258 |

The complete good-family cardinality profile is:

| Cardinality | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Count | 1 | 13 | 78 | 286 | 715 | 1,277 | 1,630 | 1,384 | 602 | 61 | 0 | 0 | 0 | 0 |

The fiber multiplicity distribution is 1:1452, 2:1058, 3:656, 4:382, 5:146, 6:57, 7:8. Here a row m:c means c distinct sums each have m subsets. The maximum multiplicity seven is a finite observation for this host.

In numeric-mask ordering, three retained maximum selections are:

| Rank | Mask | Values |
| --- | ---: | --- |
| 0 | 1903 | 1, 13, 32, 66, 174, 396, 756, 858, 915 |
| 30 | 7006 | 13, 32, 66, 169, 396, 756, 858, 1016, 1044 |
| 60 | 8148 | 32, 169, 396, 416, 756, 858, 915, 1016, 1044 |

All 61 are retained, not just these examples. For the full host, the reader's inherited minimal witness is

~~~text
756 + 858 = 174 + 396 + 1044 = 1614.
~~~

The witness selected for a bad mask is a deterministic consequence of the downward traversal; it need not be its numerically smallest contained obstruction. The first minimal support itself is mask 122 and has the 409 equality above.

## Public interface

The CommonJS file has no I/O or dependencies and exports `VERSION`, `compileSubsetObstructions`, and `openSubsetObstructions`.

### Constructor

~~~js
const {compileSubsetObstructions} =
  require("./subset_sum_obstruction_index.cjs");

const snapshot = compileSubsetObstructions(input, {
  collision_pair_budget: 1000000
});
~~~

The supplied input has `values` and optional `provenance`. Values must be strictly increasing positive integers; duplicates are rejected rather than treated as multiplicities. Canonical decimal strings, nonnegative BigInts, and safe integer Numbers are accepted by numeric conversion, with positivity enforced for host entries.

Optional `precomputed_sums` must be paired with `precomputed_through`. It must contain exactly one row for every mask of cardinality at most that threshold, and none above it. Empty and singleton identities are checked; higher supplied sums remain premises. Without this option, the constructor computes all nonsingleton sums. Row metadata is retained but does not change the arithmetic.

Bounds: 0–16 host values, each at most 128 decimal digits; at most 65,536 subset cells. Sums use BigInt and stored decimal strings. The collision-pair budget defaults to 1,000,000, with an accepted maximum of 5,000,000. If exceeded, the compiler throws without returning a partial snapshot. This is a runtime bound, not a mathematical incompleteness claim. The empty host has one good subset, the empty set, and maximum cardinality zero; this generic endpoint was source-inspected, not separately executed as a synthetic consumer.

### Saved reader

~~~js
const {openSubsetObstructions} =
  require("./subset_sum_obstruction_index.cjs");
const record = require("./thirteen_host_subset_obstructions.json");
const index = openSubsetObstructions(record.snapshot);

index.goodCount({size: 9});
index.selectGood({size: 9}, 30);
index.rankGood({size: 9}, 7006);
index.fiber("409");
index.collision(8191);
~~~

These calls illustrate the already retained outputs; they are not instructions to rebuild the snapshot.

| Method | Result |
| --- | --- |
| `summary()` | Saved finite census. |
| `subset(mask)` | Values, size, saved sum, good/bad and obstruction reference. |
| `collision(mask)` | A saved contained minimal relation, or a good result. |
| `obstructionPage(start,limit)` | Minimal support witnesses in increasing support-mask order. |
| `fiber(sum,within)` | All subsets with the requested saved sum, optionally restricted to a host submask. |
| `fibersPage(start,limit)` | Consecutive distinct-sum fibers. |
| `goodCount(query)` | Count matching a family filter. |
| `selectGood(query,rank)` | Zero-based selection in numeric-mask order. |
| `rankGood(query,mask)` | Membership, rank if present, and insertion rank. |
| `goodPage(query,start,limit)` | Paginated selected good subsets. |
| `subsetSumsPage(within,start,limit)` | Saved sums of all submasks of a selected host, in numeric submask order. |
| `statistics()` | Fresh opening/query work and zero-recomputation counters. |

A filter has optional `size` (null means any), `contains` and `excludes` bit masks, and Boolean `maximal`. Contains/excludes must be disjoint. Maximal means inclusion-maximal in the original complete host, not maximal after imposing the filter. Mask, cardinality, count, page and rank bounds fit safe integers for the stated maximum n.

Pages permit 1–64 records and an end cursor equal to the family size. Empty family selection throws, while count and end pages are valid. The reader caches up to sixteen filtered families. Each new filter scans saved good/bad cells; it does not reclassify equal sums. A requested fiber returns every matching mask, without pagination, within the overall 65,536-cell cap.

### Opening is structural, not an independent completeness proof

The reader copies its input, checks schema and shape, mask cardinalities, canonical sums, empty/singleton identities, full fiber coverage and binding to saved sums. It checks disjoint relation masks, their union and saved equality, and ensures good lists and bad-support references cover every mask consistently.

It does not recompute subset sums, rescan colliding pairs, prove supplied minimality, rerun downward classification, or re-establish maximality. It does not authenticate arbitrary edited summary counts or table provenance. Mathematical completeness belongs to the identified constructor output and argument; reopening that output is a structural operation. The JSON size cap is 20,000,000 characters.

## Retained reader work

A fresh module instance opened the completed snapshot and made **28 queries**. These include all 64 minimal witnesses in one page, all 61 maximum sets, all 258 inclusion-maximal sets through five pages, ranks 0/30/60, conditional maximum families, the two 409 fibers, empty and ten-element masks, and two pages of subset sums of the first maximum set.

The maximum-family filter requiring the first value and excluding the last value has nine members. The rank query for mask 7006 returned 30. The first maximum set has 512 subset sums, and the retained pages cover ranks 0–15 and 496–511 without summing their values anew.

The reader opened 8,192 cells and 3,759 fibers, checked 185 saved relation equalities, performed 32,768 filter-cell inspections, eleven filter cache hits, 34 fiber search steps, five fiber-mask inspections and 32 direct submask materializations. It made zero new subset additions, collision-pair replays, obstruction-closure replays, old pair/triple additions or field/B3 evaluations. Those zero counters do not mean the reader did no arithmetic or structural work.

The constructor recorded 39,977 downward-classification checks and 9,194 maximality-extension checks in addition to its 7,814 new additions and 7,801 collision-pair visits. Its observed 16 ms elapsed value is one connected-runtime observation, not a benchmark claim.

## Files and custody

- `subset_sum_obstruction_index.cjs`: frozen compiler and separate reader, blob `59516d70743535e5cfd6b3ff8df1b5107c6c2bec`.
- `thirteen_host_subset_obstructions.json`: complete input, snapshot and 28 query outputs, blob `95b8773c69e13315f505f64b8b108de2cef78689`, 428,763 bytes.
- `SUBSET_SUM_API.md`: this contract, derivation, scope and provenance.
- `README.md`: entry point.

Source and exact input were checkpointed before the one construction. The standalone input identity is `24010dbdd7ac748861ec8e4bb4dcb57979180898`, 53,362 bytes. The complete pre-reader result was checkpointed immediately at `d8ff9c1a02770b207defbd4870e4e7091da31f5d`, 346,843 bytes. The final record contains that unchanged input/snapshot and the fresh reader outputs. Complete files are published and read back by their identities; no old field, B3 proof or low-order arithmetic was replayed, and no sponsor contact or submission occurred.

This finite-host classification does not determine Bohman's unrestricted extremal function, create a new global counterexample, or independently verify the formal source's reported resolution.
