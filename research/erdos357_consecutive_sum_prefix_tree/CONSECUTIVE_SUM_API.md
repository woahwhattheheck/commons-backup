# Consecutive-sum prefix tree

This package completely classifies the strictly increasing sequences selected from the positive integer host {1,…,19} whose sums over distinct consecutive index intervals are all different. There are **24,698 sequences**, including the empty sequence. The maximum length is **10**, attained by **five sequences**. In the finite monotone notation of the retained FormalConjectures statement, this establishes **f(19)=10**.

This is a complete explicit prefix tree, not a compressed family DAG or a claim that the family was not enumerated. It retains every accepted sequence, every possible rejected next term at every accepted prefix, and exact descendant counts. It supplies finite navigation and collision evidence. It makes no asymptotic, infinite-density, reciprocal-sum, current-record, mathematical-priority or prize claim.

## Definition and source coverage

The fully read source is [FormalConjectures/ErdosProblems/357.lean](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/357.lean). Its complete observed UTF-8 text has Git blob identity **73eb1651cac9c2e625ddf91929ea5bdb4a38fb01**, 10,222 bytes. It was acquired through the repository contents endpoint without an explicit commit/ref; the blob identifies the observed text, while the display URL is a moving branch locator.

Its definition takes the sum map on finite order-connected index sets and requires injectivity. For a finite sequence, the nonempty index sets are exactly the consecutive intervals. The empty interval is one finite set and contributes zero. Because all selected terms here are positive, no nonempty interval has sum zero.

The finite monotone variant takes a strictly increasing integer sequence with terms in [1,n]. This differs from the separately stated arbitrary-order variant. It also differs from comparing all subsets: deleting an internal term may create new consecutive intervals, so this package makes no arbitrary-subset-heredity assumption. Prefix heredity is sufficient for the construction.

The observed file annotates the main finite asymptotic and infinite full-density/summability questions as research open, with local placeholders. Its separate infinite lower-density-zero variant and several historical bounds have solved annotations. These annotations are source metadata; no linked proof or local theorem was executed, verified or replayed.

The bibliography was independently located as N. Hegyvári, “On consecutive sums in sequences,” Acta Mathematica Hungarica 48 (1986), 193–200, DOI [10.1007/BF01949064](https://doi.org/10.1007/BF01949064). The direct DOI route was inaccessible through the source reader and remains held. The author-journal archive [volume 48](https://real-j.mtak.hu/7472/) confirms the citation, but its 138 MB whole-volume PDF was not opened. No convention passage, theorem proof, bound, example or numerical table from that paper was read. The exact definition used here is attributed to the complete FormalConjectures source, not to an unavailable full-text reading.

## Actual result

Counts by sequence length:

| Length | Count |
|---:|---:|
| 0 | 1 |
| 1 | 19 |
| 2 | 171 |
| 3 | 888 |
| 4 | 2,941 |
| 5 | 6,229 |
| 6 | 7,614 |
| 7 | 4,978 |
| 8 | 1,653 |
| 9 | 199 |
| 10 | 5 |

The complete maximum family, in numeric sequence lexicographic order, is:

1. [1, 2, 5, 10, 11, 12, 13, 14, 16, 19]
2. [1, 3, 6, 11, 12, 13, 14, 16, 18, 19]
3. [1, 3, 6, 11, 12, 13, 15, 16, 18, 19]
4. [3, 5, 9, 10, 11, 12, 13, 15, 16, 18]
5. [5, 8, 9, 10, 11, 12, 14, 15, 16, 18]

The order compares the first differing numerical term. A sequence precedes each proper extension. Under this order, the empty sequence has global rank 0, [1] has rank 1, [3,4,8,14,17,19] has rank 12,348, and [19] has rank 24,697. For the size-10 family, the five listed sequences have ranks 0 through 4.

Some retained prefix-completion counts are:

| Required initial sequence | Completions, including the prefix itself |
|---|---:|
| empty | 24,698 |
| [1] | 6,789 |
| [1,2] | 1,751 |
| [1,2,4] | 376 |
| [2,4] | 947 |
| [10,19] | 1 |
| [1,2,3] | 0 |

The invalid prefix [1,2,3] has the saved collision 1+2=3: old interval [0,1] and new interval [2,2], in zero-based inclusive index notation. At [1,2,4], appending 6 is rejected by 2+4=6 and appending 7 by 1+2+4=7. These are returned from stored records; the reader does not compute those sums again.

Exactly one maximum sequence starts with [1,2,5], namely the first listed maximum. Prefix conditions here constrain the initial sequence, not a collection of arbitrary required elements.

## Construction and completeness

For an accepted prefix a_0<…<a_(l−1), a node retains its positive interval-sum bitset and the l suffix sums ending at its last term. Bit s of the hexadecimal bitset records whether s is an existing nonempty interval sum.

For each possible append v>a_(l−1), up to the host maximum, the constructor computes the new suffixes in start-index order:

- each saved old suffix plus v;
- the singleton suffix v.

These are all intervals newly introduced by the append. They are pairwise distinct because the terms are positive: removing the first term strictly decreases a suffix sum. Consequently the new sequence is valid exactly when none of these sums appears in the old interval-sum bitset. No pairwise comparison among the new suffixes is needed.

On the first collision, the constructor locates the matching old interval by examining saved suffix rows at the current node and its ancestors. It records the sum and both interval endpoints. It does not recompute old interval sums to recover the witness. The remaining new suffixes for that rejected append are not evaluated; the first witness already proves rejection.

On acceptance, all new suffixes are added to the saved bitset and the child is visited. The root is the empty sequence. Every valid increasing sequence has a valid prefix and a unique final append, so induction shows that the tree contains all and only the valid host sequences. A rejected prefix cannot become valid by appending more terms, since its colliding intervals remain present. This proves the pruning rule without assuming preservation under deletion of internal terms.

Every node itself is one possible stopping sequence. If P_v(z) counts additional selected terms below node v, then P_v(z)=1+z·sum(P_child(z)). Coefficients are computed after its children and retained as exact decimal strings. The root coefficients give the displayed complete cardinality distribution, whose last nonzero degree is 10.

The implementation uses JavaScript BigInt for interval masks and exact coefficient/rank arithmetic. Host terms and interval sums fit safe integers under the declared N≤24 bound. It uses no floating-point numerical approximation.

## API

The dependency-free CommonJS module exports:

- construct(input): constructs a new bounded finite prefix tree.
- open(snapshot): opens an already retained complete snapshot and returns a saved reader.
- SCHEMA: the snapshot schema identifier.

There is no import-time construction. Reopening a published snapshot does not call construct. The first constructor run for this package was completed once, banked in full, and then used by a fresh reader.

Example consumer, after assembling the saved snapshot:

~~~javascript
const api = require("./consecutive_sum_prefix_tree.cjs");
const reader = api.open(snapshot);
reader.family({prefix:[1,2], size:10});
reader.select("0", {size:10});
reader.rank([1,2,5,10,11,12,13,14,16,19], {size:10});
reader.prefix([1,2,4]);
~~~

Reader methods:

| Method | Contract |
|---|---|
| summary() | Saved host, counts, maximum and construction-work summary |
| family({prefix?,size?}) | Number of valid completions of the initial sequence; size is the full final length |
| select(rank,{prefix?,size?}) | Full sequence at a zero-based local rank in the requested family |
| rank(sequence,{prefix?,size?}) | Local rank or a nonmember result with the first saved rejection |
| page(start,limit,{prefix?,size?}) | Up to 1,000 full sequences, with next rank and completion flag |
| prefix(prefix) | Saved additional-length coefficients and every accepted/rejected next term |
| node(id) | Saved record and its full sequence recovered through parent pointers |
| work() | Cumulative explicit reader counters |

Ranks and counts are decimal strings. Prefixes and sequences must be strictly increasing arrays of host integers. A valid prefix is included as a completion unless an incompatible total size is requested. The default family includes the empty sequence. Fixed size 0 contains only that sequence.

A structurally well-formed but property-invalid prefix has count zero and a stored collision. Malformed arrays and out-of-range rank requests throw. There are no arbitrary required/forbidden-subset conditions or internal-deletion transformations in this API.

The reader verifies structural shapes and references, not the mathematical certificate anew. It reads saved children and coefficients; selection subtracts preceding branch counts, while ranking adds them. It sums saved coefficients when the requested family has unrestricted size. These fresh arithmetic operations are measured explicitly. It never recalculates an interval sum, bitset, collision witness, coefficient recurrence or prefix-tree edge.

## Complete data and assembly

The data are distributed as a manifest and 25 complete node shards. Each shard is one compact JSON object with a contiguous node slice. The shard format changes whitespace only; nodes and their fields are not reduced or reconstructed mathematically. The manifest contains the input, full snapshot metadata and every shard's range and Git blob identity.

The full original snapshot serialization has **13,643,941 bytes**, Git blob **d81243a181550e72c627aa1b94fbd0ce5193dee7**. Concatenating the parsed node arrays in manifest order and restoring them as snapshot.nodes reproduces that exact text with JSON.stringify(snapshot,null,2)+"\n". That assembly was checked by byte equality and Git blob identity only. It is not a second construction or a second proof/collision computation.

A local assembly example:

~~~javascript
const fs = require("node:fs");
const manifest = JSON.parse(fs.readFileSync("snapshot_manifest.json","utf8"));
const nodes = manifest.shards.flatMap(s =>
  JSON.parse(fs.readFileSync(s.path,"utf8")).nodes);
const snapshot = {...manifest.snapshot, nodes};
const originalText = JSON.stringify(snapshot,null,2)+"\n";
// Check the manifest's full_snapshot_identity with a Git-blob hash implementation.
const reader = require("./consecutive_sum_prefix_tree.cjs").open(snapshot);
~~~

The example is documentation; it was not executed to repeat the published calculation. The banked assembly check used the already retained shard texts. Publication paths and their expected identities are checked separately by the connected Git publisher.

The snapshot is complete: 24,698 nodes, 24,697 accepted parent-child appends and 17,856 rejected append records. Each node retains its parent, last term, length, total, interval bitset, full suffix row, ordered children, rejected candidates and descendant coefficient row.

## Actual bounded work

The predeclared generic host bound is N≤24. The actual host is N=19. The run was capped at 50,000 accepted states, 300,000 append attempts and 2,000,000 newly evaluated suffix cells. Each applicable counter is checked before the bounded operation. A cap raises an error rather than returning a partial classification. No cap was reached and no failed constructor was rerun.

| Operation | Actual count |
|---|---:|
| Accepted states, including root | 24,698 |
| Append attempts | 42,553 |
| Accepted appends | 24,697 |
| Rejected appends | 17,856 |
| New suffix cells | 226,063 |
| Old bitset membership lookups | 226,063 |
| Saved suffix-cell comparisons to locate witnesses | 68,028 |
| Coefficient additions | 47,062 |

The family is explicitly enumerated by accepted prefix states. Runtime and storage are finite but can grow exponentially with the host size. The caps are engineering limits, not a general complexity bound.

## First saved-reader use

The fresh reader produced **35 complete responses**, each banked immediately before the next query. They include all five maximum sequences, their five inverse ranks, four additional global select/rank pairs, one prefix-local select/rank pair, seven prefix-family and next-step records, a rejected nonmember, and full root/maximum-node records.

All ten actual selection/rank pairs matched their requested ranks. The additional rank query for [1,2,3] correctly returned nonmembership and its stored witness. This describes the saved responses; no second query run was used to check them.

| Fresh reader operation | Count |
|---|---:|
| Queries | 35 |
| Saved edge scans | 345 |
| Saved coefficient reads | 1,095 |
| Parent-path node reads | 10 |
| Rank additions | 64 |
| Rank subtractions | 61 |
| Selections, including page rows | 10 |
| Rank requests, including the rejected nonmember | 11 |
| Prefix steps | 35 |
| Full node reads | 8 |
| Rejection-record reads | 3 |

Constructor calls, new interval sums, new suffix cells, coefficient recurrences and witness reconstructions were all zero in the reader. There was no failed reader query, lost ephemeral response or numerical continuation.

## Provenance and limits

The actual input is declared here and in the manifest; it was not imported from an earlier Sidon, arbitrary-subset-sum or accepted consecutive-sum table. The constructor source and input were banked before the first calculation. The complete snapshot was banked before opening the fresh reader. Sharding and final assembly were byte operations on that banked result.

The result is exact for this one finite increasing host. It does not establish f(n)=o(n), any infinite density or reciprocal-sum conclusion, the arbitrary-order variants, or a new published bound. The inaccessible primary route remains inaccessible; no source access, proof review, mathematical novelty, sponsor acceptance or award eligibility is inferred from this finite package.
