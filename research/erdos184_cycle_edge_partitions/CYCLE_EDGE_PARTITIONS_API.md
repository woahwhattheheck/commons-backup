# Saved cycle and singleton-edge partitions

This package indexes every decomposition of every edge subset of one finite labelled simple graph into simple cycles and singleton edges. A decomposition is an unordered collection of nonempty, edge-disjoint pieces whose union is the requested edge set. Pieces may share vertices. A cycle is identified by its edge set, so rotation and reversal of a traversal do not create additional pieces. Optional isolated vertices attached to an abstract subgraph do not create additional objects.

The actual input is the labelled complete bipartite graph K3,5 on vertices 0 through 7, with parts {0,1,2} and {3,4,5,6,7}. Its complete index contains 32,768 edge-subset states and 70,068 sparse coefficients. The full graph has 406 decompositions. The minimum number of pieces is 7, attained by 180 decompositions. The saved reader exports every one of those 180 minimum decompositions, including its selection trace.

These are finite classification and navigation results for this graph. They do not prove an O(n) decomposition bound for arbitrary graphs, improve a general asymptotic bound, or claim a new extremal example.

## Source and problem boundary

Bucić and Montgomery, *Towards the Erdős–Gallai Cycle Decomposition Conjecture*, arXiv:2211.07689v2 (14 November 2023), formulate the problem using edge-disjoint subgraphs in their introduction. The “Covering problems” discussion on page 2 explicitly distinguishes covers, in which cycles may share edges. The inspected introductory passages support this distinction; they were not a proof, numerical-example or current-frontier audit.

Primary manuscript: https://arxiv.org/pdf/2211.07689  
Metadata: https://arxiv.org/abs/2211.07689

The separately read FormalConjectures source was the complete 5,178-byte file at content identity `49c110154e8a595d27a2739b40e1306f3b329334`:
https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/184.lean

That source annotates the main linear decomposition assertion as research open and contains a local placeholder. It separately records solved variants, including logarithmic and iterated-logarithmic upper bounds, a K3,n−3 lower-bound family, an overlapping-cover statement, and a dense-graph result. These annotations and references were read as source information; linked proofs were not inspected. Its “best bound” wording is not promoted here to an independently verified current literature frontier.

The formal predicate permits a connected 2-regular subgraph or a one-edge subgraph. This API explicitly fixes the counted objects to edge partitions of a simple host: a singleton edge is one piece, regardless of any unused host vertices. The labelled host, cycle representatives, ordering, and finite coefficient implementation are this package’s stated model.

## Files and exact construction identity

| File | Purpose |
| --- | --- |
| `cycle_edge_partitions.cjs` | Dependency-free CommonJS constructor and saved reader |
| `k3_5_edge_partition_index.json` | Complete compact snapshot, including every state row |
| `saved_reader_queries.json` | All 37 actual reader responses, traces, counters and seven rank comparisons |
| `CYCLE_EDGE_PARTITIONS_API.md` | Conventions, exhaustion argument, API and actual results |
| `README.md` | Entry point |

The executed source has Git blob identity `25a10360bd411e0d2868343864d09898587c95cf` and 8,291 UTF-8 bytes. The complete input has identity `17e246a466c369052385191cd4128fa296bc371e` and 752 bytes; its full fields are also embedded in the snapshot. The snapshot is compact JSON followed by a newline, 644,257 bytes, identity `08a4a000259951085405b9ad8ff00b2f67a767c3`. The full reader packet is 462,286 bytes, identity `c41779aec91b4296272fa4af8bf5d50f14243a86`.

The construction was run once after source and input were banked. A separate reader opened that exact saved snapshot. No previous graph, cut, partition or proof computation was replayed.

## Input and identifiers

`buildIndex(input)` accepts `vertices` from 1 through 12 and an `edges` array of at most 16 distinct pairs. Every pair must have integer endpoints `0 <= u < v < vertices`. Loops, repeated edges and unsorted endpoints are rejected. Other input fields are retained as provenance. The algorithm is explicitly exponential in the number of edges; these limits describe a finite utility, not a scalable general decomposition algorithm.

Edge IDs are their zero-based positions in the input array. Bit i in a mask denotes edge i. For the actual input:

| IDs | Edges in order |
| --- | --- |
| 0–4 | (0,3), (0,4), (0,5), (0,6), (0,7) |
| 5–9 | (1,3), (1,4), (1,5), (1,6), (1,7) |
| 10–14 | (2,3), (2,4), (2,5), (2,6), (2,7) |

The full edge mask is 32,767. Piece IDs 0 through 14 are the corresponding singleton edges. Cycles follow in increasing numerical edge-mask order, with IDs 15 through 104. Each saved piece contains `id`, `kind`, `mask`, `edge_ids`, and a vertex traversal. A cycle traversal omits the repeated terminal start vertex; the closing edge is included in its mask.

For example, piece 15 has mask 99, edge IDs [0,1,5,6], and vertices [0,3,1,4]. It represents the four-cycle 0–3–1–4–0.

The cycle search starts at the smallest vertex of each possible cycle, visits no vertex twice, and accepts only the orientation whose second vertex is smaller than its final vertex. Every simple undirected cycle therefore has exactly one accepted traversal. The actual catalogue contains 30 cycles of length 4 and 60 of length 6.

## Complete coefficient recurrence

For an edge mask S, let P_S(z) count its decompositions by number of pieces. The empty edge set has exactly one decomposition, the empty collection, so P_0(z)=1. If S is nonempty, let e be its least numbered edge. Then

P_S(z) = z · sum P_(S minus C)(z),

where the sum ranges over saved pieces C contained in S and containing e.

Every decomposition of S has exactly one piece containing e. Removing that piece produces a decomposition of the residual edge set; conversely, adding it to a residual decomposition produces a valid decomposition of S. The branches are disjoint and exhaustive. This proves that the recurrence counts unordered piece collections once, even though a canonical recursive order is used for navigation.

Removing a nonempty contained piece strictly decreases the numerical mask. Thus increasing-mask evaluation computes every dependency first. A singleton branch always exists. Each state is stored as a sparse array `[[k, decimalCount], ...]` in increasing k; unlisted coefficients are zero. Counts use BigInt during construction and canonical decimal strings in JSON. All 2^15 state rows are retained, not just the full-graph row.

The snapshot fields are `format`, `input`, `vertices`, `edges`, `pieces`, `by_edge`, `states`, `full_mask`, `summary`, and `work`. Its format string is `cycle-edge-partition-index-v1`. The `by_edge[e]` array lists piece IDs containing e in ascending ID order.

## Saved reader

`openIndex(snapshot)` returns `{query, stats}`. It performs a small structural check of the format and state-array length. It is a reader of trusted, identified constructor output, not a complete hostile-input validator or an independent proof checker. It does not regenerate adjacency, cycles, pieces or coefficient rows.

For example, with the saved JSON already parsed as `snapshot`:

```javascript
const {openIndex} = require("./cycle_edge_partitions.cjs");
const reader = openIndex(snapshot);
reader.query({op: "profile"});
reader.query({op: "select", piece_count: 7, rank: "89"});
reader.query({op: "force", pieces: [15]});
```

This is usage syntax, not an additional execution record. The actual results are in the saved reader packet.

All masks are integers from zero through `full_mask`; omitting a mask selects the full graph. Optional `piece_count` is an integer from zero through the host edge count. Ranks and page starts are nonnegative canonical decimal strings of at most 4,096 characters. Ranks are zero-based.

| Operation | Additional fields | Result |
| --- | --- | --- |
| `summary` | none | Saved construction summary |
| `graph` | none | Vertices, input-order edges and full mask |
| `cycles` | none | All saved cycle records |
| `piece` | `id` | One saved singleton or cycle |
| `profile` | optional `mask` | Total, minimum, minimum count and complete histogram |
| `count` | optional `mask, piece_count` | Exact decimal count |
| `select` | `rank`; optional `mask, piece_count` | One decomposition and complete branch trace |
| `rank` | `pieces`; optional `mask, piece_count` | Rank, canonical piece sequence and trace |
| `page` | `start, limit`; optional `mask, piece_count` | Up to limit selections, with traces |
| `validate` | `pieces`; optional `mask` | Edge coverage/overlap outcome and edge owners |
| `force` | `pieces`; optional `mask` | Residual mask and exact completion profile |

Page limits are integers from 0 through 1,000. A start equal to the family size returns an empty page; a larger start is rejected. Selection requires a rank strictly below the family size. Invalid IDs, masks, count parameters and malformed rank strings are rejected. A selected list passed to `rank` must cover the requested mask exactly without overlap; its input ordering does not matter.

The ordering is recursive: choose the piece containing the least remaining edge in ascending piece-ID order, then use the same order on the residual mask. With a piece-count filter, only branches with the requested residual coefficient contribute. This is not an ordering by minimum piece count. For the full unfiltered family, rank 0 is the all-singleton partition, while rank 405 has seven pieces.

Selection traces retain the mask before and after each step, anchor edge, chosen piece, skipped count and residual rank. Rank traces retain the corresponding skipped counts. These are saved-table operations: inspecting branches and coefficients is fresh query work, not recurrence reconstruction.

A valid `force` request specifies pairwise edge-disjoint pieces contained in the requested mask. Removing their edges gives a bijection between completions and partitions of the returned residual mask. Its histogram is shifted by the number of forced pieces; its minimum includes those pieces. To navigate such completions, select on the residual mask and adjoin the forced IDs. This API does not introduce a separate conditioned rank field. Overlap or an out-of-mask piece returns an explicit invalid result. An empty forced list leaves the family unchanged.

## Actual full-graph family

| Pieces | Decompositions |
| ---: | ---: |
| 7 | 180 |
| 9 | 135 |
| 10 | 60 |
| 12 | 30 |
| 15 | 1 |
| Total | 406 |

There is a direct finite lower-bound explanation. Each of the five degree-three vertices on the right must be incident to an odd number of singleton-edge pieces, since every cycle contributes even degree at each vertex. At least five singleton pieces are therefore necessary. Every cycle in K3,5 uses at most six edges. A partition with at most six total pieces would then cover at most eleven edges (five singletons and one cycle), or at most six edges if all its pieces were singletons. It cannot cover the graph’s fifteen edges. The retained seven-piece partitions attain the resulting lower bound. This argument concerns this host and is not a replay or proof of the general lower-bound family recorded in Formal184.

| Requested edge mask | Description | Total | Minimum | Minimum count |
| ---: | --- | ---: | ---: | ---: |
| 32767 | Full graph | 406 | 7 | 180 |
| 32766 | Remove edge 0 | 182 | 6 | 60 |
| 32764 | Remove edges 0 and 1 | 86 | 5 | 18 |
| 99 | First four-cycle’s edge set | 2 | 1 | 1 |
| 0 | Empty edge set | 1 | 0 | 1 |

The first seven-piece selection is [0,1,2,55,44,8,14]. Rank 89 within the seven-piece family is [25,103,4,5,6,8,12]; rank 179 is [101,41,4,6,7,8,10]. Forcing cycle 15 leaves residual mask 32,668 and 16 completions: six with seven total pieces, nine with nine pieces, and one with twelve pieces. Forcing both cycle 15 and singleton 0 is rejected because their edges overlap.

## Actual work and retained evidence

The constructor did not enumerate individual full decompositions. It retained the cycle catalogue and all coefficient rows. Its work counters were:

| Counter | Actual value |
| --- | ---: |
| cycle_neighbor_visits | 890 |
| cycle_extensions | 250 |
| cycle_closures | 90 |
| state_count | 32,768 |
| piece_subset_checks | 1,081,311 |
| valid_transitions | 77,063 |
| coefficient_additions | 112,530 |
| coefficient_cells | 70,068 |

The separate reader made 37 queries and retained every complete response before continuing. It exported all 180 minimum decompositions in one requested page, so that finite family was explicitly expanded by the reader. Seven selection/rank comparisons matched, including the empty decomposition. Other responses retain the full cycle catalogue, histogram counts, deletion profiles, valid and invalid forced-piece conditions, reversed input-order ranking and a validated forced-cycle completion.

| Reader counter | Actual value |
| --- | ---: |
| queries | 37 |
| state_reads | 4,486 |
| coefficient_visits | 10,167 |
| piece_visits | 7,911 |
| mask_checks | 7,842 |
| rank_steps | 67 |
| selection_steps | 1,338 |

These counters measure their named code paths rather than all machine instructions or wall time. Snapshot copying and profile summation are not all represented by the coefficient-visit counter. The saved reader packet contains its source and snapshot pins, `outputs`, `comparisons`, final `work`, and a `reconstruction` declaration. The latter records that graph construction, cycle enumeration and the coefficient recurrence were not run by the reader.

The evidence is a complete finite construction plus its declared saved queries. It is not a proof of the infinite family’s conjectured bound, a novelty claim, or a formal verification of the implementation.
