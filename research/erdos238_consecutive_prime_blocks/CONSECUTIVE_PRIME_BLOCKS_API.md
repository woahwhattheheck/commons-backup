# Exact consecutive-prime block navigation

This package consumes the saved consecutive-prime gaps from Commons #31723 and compiles a different finite family: every nonempty consecutive block whose internal **raw gaps are strictly greater than a specified threshold**. The retained host is the complete supplied list of 1,900 primes from 2 through 16,381. It supports counts, ranks, selections, pages, maximal-component witnesses, integer prime cutoffs and block-length restrictions.

The complete constructor retains 1,899 edges, 3,799 merge-tree nodes and 22 threshold phases. With threshold zero it represents all 1,805,950 nonempty contiguous blocks. It does not enumerate those blocks individually.

## Source and scope

The full [FormalConjectures Erdős 238 statement](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/238.lean) was read as 1,779 UTF-8 bytes, independently identified by Git blob `ffa2968d22be97aff92c7f613c52f1b156ae9349`. Its main declaration asks whether, for every positive c₁ and c₂, every sufficiently large real x admits more than c₁ log x consecutive primes at most x with every internal adjacent gap greater than c₂. Its introductory wording uses all pairwise differences; for an increasing block, the adjacent condition is equivalent, because any nonadjacent difference is a sum of positive adjacent differences. The main declaration is annotated research open with a local placeholder. A separate small-c₁ variant is annotated research solved, also with a local placeholder. No proof, external proof link or present literature survey was inspected.

These are **raw differences**, with no division by a logarithm. The preceding #31723 consumer instead ordered gap(n)/ln(n), where n is the zero-based prime index. That normalization and its exact ties remain properties of the preceding artifact and are not reused as threshold semantics here.

A bounded original-source search identified Paul Erdős, “Some problems on the distribution of prime numbers,” the 1954 Varenna congress volume, published in 1955, archive item 1955-12. The exact original route `https://combinatorica.hu/~p_erdos/1955-12.pdf` returned 502 Bad Gateway. It was held without retry or an alternate host. Bibliographic search information does not constitute an independently read original statement. The fully read formal file is the actual statement authority for this package.

The finite API permits threshold zero and singletons for navigation. Singletons satisfy the internal-gap condition vacuously. A finite block in this host does not prove the eventual assertion, the c₁ log x growth condition, a new existence range, a record, or any award claim.

## Input lineage and once-only work

| Item | Exact identity |
| --- | --- |
| Prior carrier | Commons #31723 |
| Immutable prior head | `83ddc5558cc0d228728dcb00ccdda7e696908b4f` |
| Prior data path | `research/erdos234_normalized_gap_order/prime_indices2_1898_index.json` |
| Prior data blob | `e51fb877c4b5474308e95443f9dc19e9b08fd92a` |
| Consumed fields | `.primes` and `.rows` only |
| Newly frozen input blob | `9d4ad315b87cf16e89f34a4ccf0ca3601e204c6a` |
| Executed module blob | `6dc41e0d9862d578b3b17089cd37659b907bab3d` |
| Complete new index blob | `0224dfb74525d7d18b6e5aba20f01e1784a0c8f2` |

The earlier file supplies 1,897 raw gap rows at indices 2 through 1898 and all 1,900 prime values. Those rows are copied literally. Only the previously excluded initial gaps, 3−2 and 5−3, are newly subtracted, at indices 0 and 1. No other prime difference, normalized comparison, logarithm, old sort, sieve, least-factor computation or primality test is replayed.

The ultimate prime premise is the accepted #31426 list, `.snapshot.basis.primes`, in `research/ppl040_kimberling_interspersion_primes/row493_columns10001_22000.json`, blob `7decf4b5cbf9945cf707d392e0c7d3d68e4a75bd`, at merge `8bcf059ef0fda877c0975f7a89a2ae565e71a3b8`. Primality, consecutiveness and completeness remain identified premises. The saved-row validation checks indices and endpoint alignment; it does not independently verify the inherited gap arithmetic.

## Construction and finite correctness

View the prime list as a path with vertex indices 0 through 1899. Edge i joins i to i+1 and carries its raw gap. For a threshold c, retain exactly the edges with gap > c. A consecutive block satisfies the condition exactly when all its edges are retained, so it is exactly a nonempty interval inside one connected component of this path.

The constructor groups the saved edges by raw gap and processes these groups in decreasing order. Initially every vertex is a leaf. Each activated edge joins two adjacent components and creates one binary merge node. Each node retains its two children, boundary edge, gap, first and last indices, and length. A path has no cycles, so every one of its 1,899 edges creates one merge.

Equal gaps are processed as a complete group before a public phase is saved. Intermediate merge nodes inside an equal-gap group describe the construction tree; they are **not** separately exposed as threshold phases. The initial phase has no active edges. A later phase with `min_active_gap = g` includes all edges with gap at least g. The reader chooses the last saved phase whose g satisfies g > c, using exact integer cross multiplication for rational c.

Each phase stores its ordered component roots and cumulative nonempty-block counts. For a component of length L, the unrestricted count is L(L+1)/2. Restricting block lengths to a ≤ length ≤ b gives, with v=min(L,b) and u=v−a+1,

```text
C(L,a,b) = 0                                  if u ≤ 0
         = u(L+1) − (a+v)u/2                  otherwise.
```

An index interval or prime cutoff intersects each saved component in another interval or the empty set. Computing C on these intersections gives the conditional family. This query arithmetic does not rebuild the threshold phases.

The order is lexicographic by **(first prime index, last prime index)**. Components appear in increasing index order. Inside a component, starts increase first, then ends increase. For the first k possible starts, the cumulative count is C(L,a,b)−C(L−k,a,b). This monotone prefix permits binary-search selection; the corresponding expression plus the end offset gives rank. Zero-count components are permitted and do not contribute a rank.

The complete index is trusted saved output with structural consistency checks when reopened. Those checks inspect dimensions, endpoint labels, merge links and the saved partition coverage. They are not a hostile-input verifier of all inherited mathematics, recomputation of the unions, or a new primality proof.

## Actual complete phases

All counts include singleton blocks unless a length restriction is stated.

| Strict threshold c | Maximal components | Valid nonempty blocks | Longest component |
| ---: | ---: | ---: | ---: |
| 0 | 1 | 1,805,950 | 1,900 |
| 1 | 2 | 1,804,051 | 1,899 |
| 2 | 292 | 11,116 | 29 |
| 4 | 595 | 5,629 | 24 |
| 6 | 1,038 | 3,397 | 11 |
| 8 | 1,200 | 2,929 | 10 |
| 12 | 1,548 | 2,313 | 4 |
| 20 | 1,794 | 2,007 | 3 |
| 44 | 1,900 | 1,900 | 1 |

For c=8 there is exactly one longest component: indices 1597 through 1606, primes 13,477 through 13,591. Its nine internal gaps are 10, 12, 14, 10, 14, 16, 14, 10 and 14. The adjacent outside gaps are 8 on the left and 6 on the right, so they fail the strict threshold. All 329 blocks of length at least three for c=8 were exported by the reader.

For c=4 there are 141 blocks of length at least ten. Requiring all primes to be at most 1,000 and length at least three leaves 90 blocks; the longest maximal component in that prime prefix has length nine. Restricting instead to indices 1000 through 1300 and lengths three through eight leaves 357 blocks. Its `longest` field is ten because that field describes maximal components **before** the length filter, not the largest permitted returned block length.

Rational thresholds 7/2 and 9/2 give the same phases as 2 and 4, respectively. A cutoff x=1 gives an empty family. At c=44 every singleton remains valid, but the two-prime block at indices 0 and 1 is rejected.

## API

The module exports `compile(input)` and `openIndex(saved)`. Existing consumers should call `openIndex` on the saved JSON. Running `compile` is a new construction, not a reader operation.

```javascript
const {openIndex} = require("./consecutive_prime_blocks.cjs");
const saved = require("./prime_prefix1900_blocks.json");
const api = openIndex(saved);
api.query({op:"family", condition:{threshold:4, x:1000, min_length:3}});
// 90 blocks, 77 maximal components, longest maximal component 9.
```

The constructor contract is 3–4,096 increasing supplied prime values at most 10,000,000. The imported rows must cover every edge from index 2 onward, with matching endpoint labels and positive saved gaps at most 10,000,000. Only the first two gaps are newly formed. No claim is made for incorrectly identified prime or gap premises.

A condition has these optional fields:

| Field | Meaning and bound |
| --- | --- |
| `threshold` | Nonnegative integer, or `{n,d}` for n/d; n ≤ 10⁹, 1 ≤ d ≤ 10⁶; default 0 |
| `first_index` | Inclusive lower index, default 0 |
| `last_index` | Inclusive upper index, default final host index; −1 permits empty prefix |
| `x` | Integer prime cutoff 0…10⁹; restricts the last index to prime ≤ x |
| `min_length` | At least 1, default 1 |
| `max_length` | At least min_length, default host size |

All numeric inputs must be safe integers. Counts and cross products stay exactly representable under these declared bounds. No floating-point logarithm or rounded threshold decision is used. Up to 32 distinct normalized conditions are cached; rational thresholds are not reduced, so different encodings of the same rational value can occupy separate cache entries. Prime-cutoff binary searches occur before the condition cache lookup and are counted as fresh query work.

| Operation | Result |
| --- | --- |
| `summary` | Host dimensions, every phase summary and constructor counters |
| `family` | Normalized condition, selected phase, count, component count and longest maximal component |
| `components` | Every intersected maximal component, per-component count and cumulative counts |
| `select` | Block at a zero-based rank, with indices, prime endpoints and length |
| `rank` | Membership and zero-based rank for a supplied first/last index pair |
| `page` | Up to 512 blocks, starting at `offset`; reports total and next offset |
| `block` | Endpoint data and literal saved internal and outside gaps |
| `phase` | One complete saved phase by `id` |
| `node` | One saved leaf or merge node by `id` |
| `conditions` | Summary of every condition created in this reader |

`block` is an evidence lookup for an arbitrary in-host interval. It does not accept or certify a threshold by itself. Its left and right boundary records may lie outside a requested query window; they are always the original host boundaries. Use `rank` for conditional-family membership.

Ranks select only nonempty blocks. There is no empty-block rank. A reversed index condition or a prime cutoff below the first retained prime produces an empty family; selection from such a family fails rather than inventing an element. Out-of-domain block indices fail validation. Every query result is returned as a detached JSON copy. The original saved input is likewise copied on opening.

## Fresh saved-reader use

The frozen reader packet contains all **37 complete outputs**, each individually banked before the next query, and the final work counters. No response was lost and no reader exception occurred.

Six selections were followed by their inverse rank queries, with exact matches:

| Condition | Rank | Selected indices |
| --- | ---: | --- |
| Full threshold-zero family | 0 | [0,0] |
| Full threshold-zero family | 902,975 | [556,1421] |
| Full threshold-zero family | 1,805,949 | [1899,1899] |
| c=4, length at least 10 | 140 | [1770,1779] |
| c=4, prime cutoff 1,000, length at least 3 | 45 | [122,124] |
| c=4, indices 1000…1300, lengths 3…8 | 178 | [1127,1131] |

The packet also retains the complete c=8 component list, its longest-block boundary witness, every one of the 329 c=8 blocks of length at least three, the full cutoff-1,000 component list, the empty-cutoff result, the terminal full-host phase, the root merge node, and all 16 condition summaries.

The new constructor performed 1,899 raw-gap grouping insertions, 1,899 union merges and 31,716 component-root snapshot visits. Its two initial gap subtractions are separate from the 1,897 inherited gap records. It performed zero old-gap subtractions, old normalized comparisons, sieve steps or primality tests.

The fresh reader performed 275 phase comparisons, 12,837 saved-component scans, 11,217 condition-count formula evaluations, 55 prime-cutoff comparisons, 4,339 selection steps and 12 rank formula evaluations. It created 16 conditions and had 15 condition-cache hits. The two block-evidence queries returned 11 internal saved gap records. These counters describe the named operations rather than all interpreter overhead. They explicitly include new conditional arithmetic and do not imply zero-cost queries.

Reader counters for new gap subtraction, union merging, phase reconstruction, prior normalized comparison, primality testing and sieving are all zero.

## Files and limits

- `consecutive_prime_blocks.cjs`: generic bounded constructor and separate saved reader.
- `prime_prefix1900_blocks.json`: complete prime, gap, merge-tree and phase index.
- `saved_reader_queries.json`: all actual requests, responses, individual output blob identities and work counters.
- This guide and `README.md`.

The data cover only the identified finite prime prefix. At x beyond the final retained prime, queries still concern only that host. No missing later prime or later block is inferred. No assertion of an infinite run, an eventual lower bound, current prize eligibility, or mathematical novelty is made.
