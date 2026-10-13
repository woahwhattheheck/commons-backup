# Exact graph partition polynomials and saved navigation

This package compiles the unordered vertex partitions of a supplied finite labelled graph in three modes: independent blocks, clique blocks, and blocks satisfying either condition. It stores the complete partition-count polynomial for every induced vertex subset. A separate reader answers exact count, prefix, rank, select, page and labelled-colour queries without rerunning the graph predicates or polynomial recurrences.

The actual consumer uses the eleven-vertex, twenty-edge Mycielski graph already retained in [Commons #31448](https://github.com/woahwhattheheck/commons/pull/31448). No Mycielski construction, component calculation, cut objective or local edge-bipartization profile was rerun.

All **2,048 induced vertex sets** are covered, with **39,936 exact coefficient cells** and 28 parameter-profile rows. For the full graph G:

| Parameter | Value | Number of optimum unordered partitions |
| --- | ---: | ---: |
| Chromatic number χ(G) | 4 | 520 |
| Cochromatic number ζ(G) | 4 | 840 |
| Chromatic number χ(complement G), equivalently clique-cover number of G | 6 | 87 |

The classical value χ(G)=4 is prior construction knowledge. The new artifact supplies complete finite partition coefficients and navigation, not a new chromatic-number theorem.

## Sources and scope

[Heckel, *The difference between the chromatic and the cochromatic number of a random graph*, arXiv:2409.17614v2, February 19, 2025](https://arxiv.org/html/2409.17614v2), defines cochromatic classes as cliques or independent sets. Sections 2.2–2.3 distinguish ordered and unordered partitions. Singleton blocks require care: Proposition 6's simple type-choice factor assumes that they are absent.

The Erdős–Gimbel question concerns G(n,1/2), with each potential edge independently present with probability one half. It asks for some f(n) tending to infinity such that Pr[χ(G)−ζ(G)>f(n)] tends to one. Heckel's Theorem 1 covers a specified range of n described as roughly 95% of sizes; the paper still conjectures the all-n extension. This is a dated partial result, not a general resolution or an exhaustive current-status survey.

The input construction is credited to Jan Mycielski, *Sur le coloriage des graphes*, Colloquium Mathematicum 3 (1955), 161–162, DOI 10.4064/cm-3-2-161-162. The predecessor guide identifies its accessible construction source as [Lin–Liu–Zhu, *Multi-colouring the Mycielskian of Graphs*](https://www.calstatela.edu/sites/default/files/multicolomycillz.pdf), introduction and reference [6]. This continuation consumes that guide's exact graph rather than rebuilding the construction or rereading its proof.

The present graph is deterministic. Its induced-subset census is neither a random sample nor a statement about most large graphs. All extrema here concern this single finite host and its complement. No asymptotic gap, new frontier or conjecture solution is claimed. The FormalConjectures path for Erdős 625 returned 404 once and was not retried; no formal status or linked proof is inferred from that unavailable route. No sponsor contact or submission occurred.

## Literal input and custody

Only the canonical edge list from the accepted predecessor guide is consumed:

~~~json
{
  "vertex_count": 11,
  "edges": [
    [0,1],[0,4],[0,6],[0,9],[1,2],
    [1,5],[1,7],[2,3],[2,6],[2,8],
    [3,4],[3,7],[3,9],[4,5],[4,8],
    [5,10],[6,10],[7,10],[8,10],[9,10]
  ]
}
~~~

Labels 0 through 4 are the base cycle, 5 through 9 are their twins, and 10 is the apex. These labels are inherited, not quotiented under graph automorphisms.

The precise input source is:

- Repository: woahwhattheheck/commons.
- Accepted carrier: #31448.
- Immutable source commit: 91a4ff5a5dadccff0e3d2d4be77ba09d850c6ca2.
- Path: research/ppl046_erdos74_local_bipartization/LOCAL_BIPARTIZATION_API.md.
- Guide Git blob: 3ab3a88d1be44bd29d07fcd3729988d74ba92087, 25,504 bytes.
- Field: literal canonical edge-ID list in section 2.

A native PR-file read supplied the complete added-file patch. Its added lines were reconstructed into the full guide bytes and independently matched to that Git blob. The literal twenty-edge JSON list was then extracted. The old large cut dataset and old constructors were not needed.

The standalone new input packet, including provenance, was banked as blob e413424286ac5cec9df6b29b0129b948733de735, 1,306 bytes. The implementation was inspected, syntax-parsed and banked before the single actual computation as blob 968148d74804a3fd4bb07c46ce223c98c4fdaabb, 14,348 bytes. The initial full result was checkpointed during that computation invocation as blob e9d5bd5a65b2b552330fb2cc52a4b117a793a0c1, 1,089,650 bytes.

The final JSON is compactly serialized. Compact serialization changes whitespace only; all constructor tables and all actual reader outputs remain present.

## Counted objects

A graph is finite, simple and undirected, with vertices labelled 0 through n−1. A vertex subset is encoded by the usual bit mask. All partitions consist of disjoint, nonempty blocks whose union is the queried subset.

The three modes are:

- independent: every block induces no edges;
- clique: every block induces a complete graph;
- homogeneous: each block independently satisfies at least one of those two predicates.

A singleton satisfies both predicates but is **one block**, not two choices with separate type labels. No empty block is introduced. The empty vertex set has one empty partition with zero blocks.

The counted partitions have no colour names and no arbitrary block order. For navigation, order the blocks by their smallest vertices. This canonical representation does not multiply the partition count. Within a fixed subset and fixed number of blocks, compare possible first-block masks numerically, then recurse on the remaining subset. This is the declared rank order; it need not match lexicographic ordering of written vertex lists.

Clique partitions of G[S] are precisely independent partitions of its complement on S. Homogeneous partitions are unchanged by graph complementation. Therefore the same three tables provide χ(G[S]), χ(complement G[S]) and ζ(G[S]) without constructing a second graph.

## Exact recurrences

For a subset S, let v be its least vertex and R=S without v. Let I(S) and C(S) denote its independent and clique predicates. The empty subset satisfies both. Then

I(S) = I(R) and N(v)∩R is empty,

C(S) = C(R) and N(v)∩R = R.

These recurrences classify all 2^n masks using the explicit adjacency input. The classifications are new production prerequisites for this partition task; they are not old bipartization calculations.

For one of the three allowed block predicates A, define

P_A(S;t) = sum_k c_A(S,k) t^k,

where c_A(S,k) counts unordered admissible partitions of S into exactly k blocks. The empty-subset polynomial is 1. For nonempty S,

P_A(S;t) = t · sum_{B⊆S, v∈B, A(B)} P_A(S without B;t).                 (1)

Every partition has exactly one block containing the least vertex v. Deleting that block leaves exactly one admissible partition of the remaining set. Conversely, any such block and remaining partition form a unique partition of S. These two operations are inverse, proving (1) without division by factorials or arbitrary block labels.

Removing v makes the remaining mask numerically smaller than S, so numeric subset order is a valid dynamic-programming order. The constructor stores every coefficient from degree 0 through |S|, including zeros. Every nonempty subset has exactly one partition into |S| singletons.

The least index with a nonzero coefficient gives the corresponding minimum number of blocks. The optimum partition count is the coefficient at that index. The homogeneous predicate is a union of predicates, so its singleton contribution is added once.

The number of anchored candidate blocks examined over all nonempty subsets is

sum_{s=1}^n binomial(n,s) 2^(s−1) = (3^n−1)/2.

The actual n=11 input therefore has exactly 88,573 candidates. This coverage formula concerns candidate blocks, not enumeration of complete partitions.

### Prefixes, rank and selection

Fix S, mode and required block count k. For a candidate first block B, exactly c_A(S without B,k−1) completions follow it. These quantities are already stored.

Selection subtracts the completion counts for preceding candidate masks until it locates the containing branch, records that block and repeats. Ranking sums the counts of preceding branches along a complete canonical block sequence. A prefix query returns the remaining subset, remaining block count, total completions and the first rank of that contiguous completion interval.

This follows directly from the disjoint first-block decomposition in (1). Reader candidate-mask scans are fresh navigation work, but they use the saved predicates and coefficients; no coefficient recurrence or graph-predicate calculation is repeated.

### Labelled colours

For an integer q≥0, a partition with k nonempty unlabelled blocks can receive distinct names from q colours in

(q)_k = q(q−1)…(q−k+1)

ways. Hence the number of valid vertex-to-colour maps is

sum_k c_A(S,k) (q)_k.                                               (2)

Unused colours are allowed. In independent mode this is the usual proper-colouring count, and in clique mode it is that count for the complement. Homogeneous mode counts colour maps whose classes are homogeneous, without adding independent/clique type labels to singletons.

Equation (2) distinguishes unlabelled set partitions, canonically represented blocks, and genuinely labelled colours. The empty graph has one colouring for every q, including q=0; a nonempty graph has none with zero colours.

## Complete actual full-graph coefficients

The full-mask polynomials have the following nonzero coefficients. All degrees below four are zero in every mode; clique mode also has zero coefficients at four and five.

| Number of blocks k | Independent | Clique | Homogeneous |
| ---: | ---: | ---: | ---: |
| 4 | 520 | 0 | 840 |
| 5 | 4,265 | 0 | 11,385 |
| 6 | 8,938 | 87 | 31,875 |
| 7 | 7,171 | 360 | 26,336 |
| 8 | 2,590 | 365 | 8,065 |
| 9 | 445 | 135 | 1,030 |
| 10 | 35 | 20 | 55 |
| 11 | 1 | 1 | 1 |
| Total over all k | 23,965 | 968 | 79,587 |

The 840 minimum homogeneous partitions include all 520 minimum independent partitions and 320 additional partitions using at least one nontrivial clique block. This is a finite difference of the retained complete counts, not a general relation between such families.

The complete 28-row profile groups all induced subsets by size and the triple (χ, χ of complement, ζ). In this host, the only induced subsets with χ−ζ>0 are its twenty two-vertex edges, where the gap is one. For the complement, the largest induced-subset gap is four, attained on mask 992, the five twins: they are independent in G and therefore form K5 in its complement. These conclusions are restricted to the retained eleven-vertex universe.

For the full complement the gap is 6−4=2. This explicit small example has no bearing on the probability or large-n limit in Erdős 625.

## Public interface

The module is plain CommonJS JavaScript, with no imports, I/O, native dependency or random sampler.

| Export or reader method | Result |
| --- | --- |
| compilePartitionIndex(input, options={}) | Compile all three complete subset-polynomial tables. |
| openPartitionIndex(snapshotOrJSON) | Open saved coefficients without repeating the recurrences. |
| summary() | Saved coverage and full-graph counts. |
| parameters(mask) | Vertex list, size, three minimum block numbers, gaps and optimum counts. |
| coefficients(mask, mode) | All exact coefficients, with the saved minimum. |
| count(mask, mode, k) | Decimal exact partition count for k blocks. |
| profile() | Saved grouping of all induced-subset parameter triples. |
| parameterPage(start=0, limit=32) | Consecutive numeric masks, at most 64 rows. |
| selectPartition(mask, mode, k, rank) | One partition and complete skipped-completion trace. |
| rankPartition(mask, mode, k, blockMasks) | Rank of a complete canonical partition and branch trace. |
| prefixCount(mask, mode, k, blockMasks) | Number and rank interval of completions of a canonical prefix. |
| partitionPage(mask, mode, k, start=0, limit=16) | Up to 64 selected partitions with their traces. |
| labelledColourings(mask, mode, q) | Equation (2), retaining every evaluated term. |
| statistics() | Reader counters; this accessor is not counted as a query. |

Modes are the exact strings independent, clique and homogeneous. All returned records are copies. Query callers cannot mutate the internal saved index through returned values.

Example using the actual published data:

~~~js
const { openPartitionIndex } = require("./partition_index.cjs");
const delivery = JSON.parse(savedDataText);
const api = openPartitionIndex(delivery.constructor.snapshot);

api.parameters(2047);                            // χ=4, ζ=4, complement χ=6
api.count(2047, "homogeneous", 4);                 // "840"
api.prefixCount(2047, "homogeneous", 4, [3]);       // 26 completions, first rank 14
const p = api.selectPartition(2047, "homogeneous", 4, "420");
api.rankPartition(2047, "homogeneous", 4, p.blocks.map(b => b.mask));
api.labelledColourings(2047, "independent", "4");   // "12480"
~~~

Call the constructor only for a new explicit graph. Reopen the existing snapshot for further queries of this input.

### Bounds and refusals

The constructor accepts 0≤n≤14, and labels are integer Numbers from 0 through n−1. Edges must already be canonical: each pair has u<v, and the distinct pairs are listed in lexicographic order. Loops, reversed pairs, duplicates and out-of-range endpoints are refused. At most binomial(n,2) edges can be supplied.

The default coefficient-visit budget is 2,000,000. A caller may supply coefficient_budget from 1 through 20,000,000. Crossing it throws and returns no partial snapshot. Thus the vertex cap does not promise that every graph at that cap fits every budget. The sole actual compilation used n=11 and consumed 171,384 visits. Larger branches and budget refusals were source-inspected, not expanded into a second graph run.

Masks are Numbers from 0 through 2^n−1. Block counts range from 0 through n; a count query above the selected subset's size returns zero. Prefix blocks must be positive, pairwise disjoint subsets of the remaining mask, each contain its least vertex, and satisfy the selected saved predicate. Their list length cannot exceed k. Complete partition ranking additionally requires that no vertices or blocks remain and that the saved terminal completion count be one.

Ranks and colour counts accept canonical nonnegative decimal strings or BigInts, or safe-integer Numbers. Decimal inputs are limited to 100 digits. Selection requires rank less than the saved family count. Paging permits a start equal to the family count, returning an empty page, but rejects larger starts. Page limits are 1 through 64. Prefixes with no completions return count zero and first_rank null rather than fabricating an admissible rank.

The reader accepts JSON text or an object, with a 12,000,000-character serialized limit. Empty-graph and zero-block cases are part of the same contract. Every saved data count is a decimal string; BigInt is used for all coefficient and colour arithmetic.

The reader's checks cover schema, graph ordering, subset-size rows, predicate-code shape, coefficient-row lengths, nonnegative integers, empty/all-singleton endpoint identities and the minimum inferred from each saved row. They do **not** recompute the graph's homogeneous predicates or equation (1), and they do not authenticate an arbitrarily edited coefficient table. The profile is saved constructor data, not independently re-proved by opening. Mathematical provenance rests on the identified source, once-run implementation and retained complete output.

## Fresh saved-reader results

A separate module instance reopened the complete snapshot once and performed 30 queries. No graph predicate or polynomial recurrence was replayed.

The query set includes all three full-mask coefficient rows, the 28-row profile, individual induced-subset parameters, fixed-k counts, selected partitions, complete rank traces, two prefixes, an eight-partition tail page, four labelled-colour evaluations, the empty partition and a final page of 32 induced-subset rows.

For homogeneous four-block partitions:

- Rank 0 has blocks {0}, {1,3}, {2,4,10}, {5,6,7,8,9}.
- Rank 420 has blocks {0,8}, {1,4,10}, {2,5,7,9}, {3,6}.
- Rank 839 has blocks {0,3,10}, {1,6,8,9}, {2,5,7}, {4}.

All three round-trip ranks are retained. They happen to be independent partitions; the full homogeneous family is larger, as the coefficients and clique-prefix query establish.

The first-block mask 3, representing clique {0,1}, has **26** homogeneous four-block completions occupying ranks 14 through 39. A singleton first block {0} has **14** completions starting at rank 0. The complete fixed-three-block homogeneous count is zero.

Labelled-colour queries give:

| Mode and number of colours | Valid colour maps |
| --- | ---: |
| Independent, q=4 | 12,480 |
| Homogeneous, q=4 | 20,160 |
| Clique, q=6 | 62,640 |

A further independent-mode query used q=8,388,608, the literal policy count from the released #31548 artifact solely as a reproducible new scalar input. Its exact result is:

~~~text
14473976645971871180656308791375023272007494280862187137433868343357472768000
~~~

No game property is needed for that choice, and no game calculation was repeated.

The actual work records are:

| Work or retained object | Count |
| --- | ---: |
| Explicit source edges consumed | 20 |
| New nonempty block-predicate states | 2,047 |
| Anchored candidate blocks | 88,573 |
| Constructor coefficient visits | 171,384 |
| Positive coefficient additions | 103,735 |
| Retained coefficient cells | 39,936 |
| Complete partitions enumerated by constructor | 0 |
| Fresh reader queries | 30 |
| Reader candidate blocks inspected | 26,955 |
| Saved completion lookups | 727 |
| Selected block records | 64 |
| Labelled-colour polynomial terms | 29 |
| Reader graph-predicate / partition-recurrence recomputations | 0 / 0 |
| Old graph-constructor / cut-or-component evaluations | 0 / 0 |

The observed constructor time was 39 ms and reader opening 20 ms. These are individual execution observations, not benchmark guarantees. Candidate scans, saved-row validation and new BigInt query arithmetic are accounted for as reader work; “no recurrence replay” does not mean no work.

## Files

- partition_index.cjs: explicit-graph compiler and separate saved reader.
- mycielski_partition_polynomials.json: full literal graph, all subset polynomials, profile and all 30 reader outputs.
- PARTITION_API.md: source conventions, exact recurrences, bounds and usage.
- README.md: entry point and concise result.

The implementation was frozen before the single actual construction. There was no synthetic test suite, old accepted computation replay, graph sampling, larger-host escalation, external submission or mathematical novelty claim.
