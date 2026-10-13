# Exact labelled tree embeddings in a finite blow-up

This module counts and navigates injective, edge-preserving maps of a labelled finite tree into an explicitly supplied blow-up graph. The actual host is the released five-part, size-six C5 blow-up, and the actual tree has vertices 0 through 12 with parent floor((v-1)/2) for each v>0. The index represents exactly **11,576,535,552,000 labelled embeddings** without listing them.

The counted maps preserve every tree edge. They do not have to preserve tree nonedges. Different maps are different embeddings even when their vertex images coincide. No automorphism quotient, image-set count or induced-copy count is claimed.

## Source and status

Václav Rozhoň, *A Local Approach to the Erdős–Sós Conjecture*, arXiv:1804.06791v2 (26 October 2018), abstract and Conjecture 1.1, attributes to Erdős and Sós the assertion that average degree strictly greater than k-1 forces every tree with k edges as an ordinary subgraph:

- https://arxiv.org/pdf/1804.06791
- Published article locator: https://epubs.siam.org/doi/10.1137/18M118195X

The author PDF's statement was read for the convention and attribution, not its proof. Ordinary subgraph containment is unpacked here as an injective vertex map preserving edges; extra edges are allowed. The dated conjecture wording in that source is not presented as current status.

The separately read FormalConjectures file is identified by blob **9b9a3d32697adf21bb9d78c2bf7db51907c0c243**, path FormalConjectures/ErdosProblems/548.lean. It currently marks the assertion research solved, while the local theorem body remains a placeholder. Its linked external Lean development was neither opened nor reviewed. The finite API supplies neither a proof of the general statement nor a new counterexample, record, prize claim or sponsor submission.

The formal file states the sufficient condition |E(G)| >= ((k-1)/2)n + 1 with k+1 <= n. The primary paper uses average degree > k-1. The formal condition is sufficient for that strict average-degree inequality, but these numerical phrasings need not be identical when the half-integer threshold is rounded. For this actual n=30 and k=12 they both hold: the host has 180 edges, above the formal threshold 166, and average degree 12>11. These facts locate the finite example; the index does not invoke the general theorem to obtain its counts.

An optional independent survey request to https://www.dim.uchile.cl/~mstein/Tree_survey.pdf returned 403 and was held without retry or alternate route. No content from that failed request is attributed here.

## Identified input and prior work boundary

Only part sizes and base-edge parameters are consumed from the accepted host:

- Commons PR #31636, merge 20e7ca9188726f97019dd82380dd095608d79097.
- research/erdos128_blowup_subsets/cycle5_size6_index.json
- Blob **444f907b1e45eb2a989b3ad8740730d193dc426a**.
- part_sizes = [6,6,6,6,6].
- base_edges = [[0,1],[0,4],[1,2],[2,3],[3,4]].

Host part p consists of labels 6p through 6p+5. Each part is independent, and every base edge supplies all cross edges between its endpoint parts. This is the classical uniform C5 blow-up from the earlier source-qualified package. Its previous occupancy rows, induced-edge histograms, subset classifications and proof work were not rerun. This package forms the small base adjacency lists needed for its new tree-template search; it never forms the 180 individual host edges.

The labelled tree is a newly declared input, not an example claimed from Rozhoň:
[[0,1],[0,2],[1,3],[1,4],[2,5],[2,6],[3,7],[3,8],[4,9],[4,10],[5,11],[5,12]].
The isolated-root case is supported by the generic API, but the actual tree has thirteen vertices.

The exact input text has blob **7299dffded56a66d8cc4e5ffd4c78d0ad487ab76**. It is embedded in heap13_cycle5_size6_index.json, along with its source lineage and the implementation identity. The actual executed implementation is **5d6e17385d2d36ad571b73b040aeec67819b089a**. There was one production build and one separate saved-index reader session. No later implementation patch or construction replay was needed.

## Why the finite count is exact

For a host with independent parts of sizes w_0,...,w_(b-1), each embedding determines a part assignment a(v) for every tree vertex. Every tree edge must map to a base edge. Conversely, any such part assignment can be lifted to an embedding by choosing distinct host vertices inside each part. There is no additional constraint on nonedges.

Root the validated tree at 0. Assign the root any base part. In breadth-first tree order, assign each other vertex one of the neighbors of its parent's assigned part. A tree vertex has exactly one earlier parent, so this enumerates every edge-preserving part assignment once and omits none. The build validates that the supplied pattern is a connected simple graph with h-1 edges before using this argument.

Let c_p be the number of tree vertices assigned to part p. The number of lifts of this assignment is
product_p (w_p)_(c_p),
where (w)_c = w(w-1)...(w-c+1), (w)_0=1, and (w)_c=0 for c>w. The tree vertices are labelled, so this is a falling factorial, not a binomial coefficient. Distinct parts have disjoint host labels, making their choices independent. Summing these weights over the complete part-assignment list proves the total.

In the actual C5 base graph each parent has two part choices, so the search has 5*2^12 = 20,480 complete templates. This is a mathematical explanation of the retained row count, not a second enumeration. Of those rows, 19,240 have positive weight and 1,240 have weight zero because a part would be overfilled. There are 575 occupancy profiles. The positive weights sum to 11,576,535,552,000.

A fixed-map condition prescribes several tree vertices' host images. A template is discarded if a prescribed image lies in a different part, if the root part is excluded, or if two prescribed tree vertices share a host label. For a compatible template, let f_p be the number of prescribed images in part p. Its conditional weight is product_p (w_p-f_p)_(c_p-f_p). The remaining labelled vertices must inject into the still available host labels, which proves the conditional formula. An empty root-parts set yields an empty family.

## Ordering and exact navigation

A part assignment is stored as the safe integer code sum_v a(v)*b^v. Tree vertex 0 is the least-significant digit. Rows are sorted by this numeric code. This is the outer family order; it is not traversal order or lexicographic order on host mappings.

Inside a template, list the unfixed tree vertices of each part in increasing tree-label order. Their image tuple is an ordered selection without replacement from the remaining host labels of that part, ordered lexicographically. The per-part tuple ranks are mixed-radix digits, with part 0 most significant. This gives a complete order on the lifts of that template.

For an available ordered pool of s host labels and a remaining tuple of length r, every possible first image has (s-1)_(r-1) completions. Repeated quotient/remainder selection therefore selects the tuple at any valid rank; multiplying and summing these block counts ranks a tuple. Empty per-part tuples have one choice and rank zero. This argument also covers conditions that fix every tree vertex.

Conditional rows retain their row index, exact weight and cumulative weight. Binary search finds the template containing a requested rank. Zero-weight templates remain in the construction but are absent from admitted conditional lists. All counts and ranks exposed as potentially large values are canonical decimal strings backed by BigInt. Host labels, row identifiers and part codes remain bounded safe integers.

Rank zero is the first map. A rank equal to the family total is out of range. A page start equal to the total is permitted and returns an empty page. Pages are limited to 32 maps.

## Generic API contract

Exports: SCHEMA, SHARD, LIMITS, buildIndex(input), openIndex(index, shards).

The bounded constructor accepts:
- 1 to 8 host parts, each of size 1 to 12, with at most 60 host vertices.
- A simple undirected base graph with no loops or duplicate edges.
- A labelled tree with 1 to 16 vertices, no loops or duplicate edges, connected with h-1 edges.
- At most 200,000 complete part templates. Exceeding this work cap throws rather than silently truncating.
- Shards of at most 4,096 rows.

At the declared maximum b=8,h=16, b^h=2^48, so encoded part assignments fit exactly in JavaScript safe integers. Generic instances are not promised to fit the work cap; in particular enumeration is exponential in the tree size and base degrees.

The current reader methods are:
| Method | Result |
| --- | --- |
| summary() | Host/tree sizes and saved total/profile counts |
| profiles() | All saved occupancy profiles and weights |
| template(row) | One row, decoded part assignment, weight and saved cumulative count |
| family(condition) | Exact total and number of positive admitted templates |
| select(rank, condition) | One map with its outer row and per-part ranks |
| rank(mapping, condition) | The inverse rank for an admitted injective map |
| page(start, count, condition) | Up to 32 selected maps |
| witness(mapping) | Tree edges with their mapped host endpoints and base-edge witnesses |
| conditions() | Complete cached condition records, including admitted rows |
| work() | Explicit counters for this opened reader |

A condition has only two optional fields:
- fixed: an array of [treeVertex, hostVertex] pairs. Each tree vertex may occur at most once. Host labels must be valid. Repeated host labels across different tree vertices describe an impossible injective family, with count zero.
- root_parts: an array of distinct allowed base-part indices. Omission allows all parts; an empty array allows none.

Unknown condition fields, duplicate prescribed tree vertices, duplicate root parts, noninteger labels and out-of-range values are rejected. Normalization sorts both fields for stable cache keys. At most 32 distinct normalized conditions are cached in one reader.

The reader copies its supplied JSON objects and returns copies or newly created outputs. Its reopening checks cover schema, shard spans, row order, canonical numeric strings, saved cumulative sums and total coverage. These are structural consistency checks, not independent proofs of the mathematical provenance or completeness of the template list. Supplied shard identities must be checked by the caller against the enclosing certificate; openIndex does not hash input files or rerun the constructor. It trusts the saved mathematical tables.

Complete condition files are retained query results. The current openIndex signature opens the construction index and template shards, not prepopulated condition caches. A later new reader computes requested condition records by scanning saved templates and looking up saved falling factorials. This query work is reported explicitly; it is not claimed to be free or to avoid all arithmetic.

A typical saved-reader call sequence, shown as usage rather than a second executed consumer, is:

~~~javascript
const {openIndex} = require('./tree_embeddings.cjs');
const certificate = /* parsed heap13_cycle5_size6_index.json */;
const shards = /* parsed template files in certificate.shard_files order */;
const reader = openIndex(certificate.index, shards);
const condition = {fixed:[[0,0],[1,6],[2,7]]};
const family = reader.family(condition); // total "2268725760"
const chosen = reader.select("1000000000", condition);
const rank = reader.rank(chosen.mapping, condition);
~~~

## Complete retained construction

The five template files cover consecutive row ranges 0 through 20,479. Each row is
[part_code, labelled_injections_decimal, cumulative_injections_decimal].
The index binds every complete shard by Git blob identity and UTF-8 byte count, and contains all 98 falling-factorial cells and all 575 occupancy profiles.

| File | Complete blob |
| --- | --- |
| heap13_cycle5_size6_index.json | a2f46b70fae64b560fab01f645054931ae520b64 |
| template_rows_00000_04095.json | 7c367e7d1c107e59235124ccb01f44e45b20a541 |
| template_rows_04096_08191.json | 57fb79c0fcb1ba4a41563c08fc2bf9ec4ae0ff30 |
| template_rows_08192_12287.json | effb18507201f9f95a53894e202bdfd61bff6f9c |
| template_rows_12288_16383.json | a495c3d2d0484a8ee3a2515f8be4e129ee5f6acb |
| template_rows_16384_20479.json | f25a9cab00ce570dcf4f57e0db3c0a166f48e848 |

The actual build counters record 40,956 recursive search nodes, 20,480 completed templates, 102,400 falling-factorial weight factors and 20,480 profile additions. The search-node counter is retained; individual recursive search nodes are not stored as separate records. The full terminal template list is stored.

## Actual saved reader

saved_reader_queries.json retains 58 ordinary complete outputs, plus references to all nine members of one complete conditions() response. Thus work.queries is 59. The nine condition files contain every admitted row, not sampled rows. There is no lost or unbanked response in this consumer.

| ID | Condition | Embeddings | Positive templates |
| --- | --- | ---: | ---: |
| 0 | All maps | 11,576,535,552,000 | 19,240 |
| 1 | Vertex 0 maps to host 0 | 385,884,518,400 | 3,848 |
| 2 | Root maps into host part 0 | 2,315,307,110,400 | 3,848 |
| 3 | 0→0, 1→6, 2→7 | 2,268,725,760 | 912 |
| 4 | 0→0, 1→1 | 0 | 0 |
| 5 | 0→0, 3→0 | 0 | 0 |
| 6 | No allowed root part | 0 | 0 |
| 7 | Every vertex fixed to the saved middle-ranked map | 1 | 1 |
| 8 | Vertices 0 through 10 fixed to that map | 30 | 4 |

Condition 4 fails because a tree edge would lie within an independent part. Condition 5 fails injectivity. These are two different finite obstructions. Condition 8's entire 30-map family was exported in one page and every map was ranked. Comparison of the saved outputs shows ranks 0 through 29 in order; no query or construction was repeated for that comparison.

The all-family first map is
[6,12,13,7,8,9,10,0,1,2,3,4,5].
At rank 5,788,267,776,000 the map is
[0,24,25,18,19,20,21,12,13,14,15,16,17].
The last map is
[23,17,16,22,21,20,19,29,28,27,26,25,24].
The reader also returned a three-map page starting at rank 10^12, full first/middle/last inverse ranks, and two complete twelve-edge witness lists. It did not enumerate the whole labelled embedding family.

Counters distinguish reopening from new query work: 20,480 rows were indexed and their saved cumulative values checked structurally; nine new conditions scanned 184,320 saved rows. Query work includes 153,962 template decodes, 24,493 saved falling-factorial lookups, 23,825 conditional weight products, 27,853 conditional cumulative additions, 176 binary-search steps, 293 partial-permutation steps, 24 edge-witness lookups and 43,654 admitted-template scans for ranks. The counters for new templates, new falling-factorial cells and new host/base-edge construction in the reader are zero. These counters measure the named operations, not every JavaScript instruction.

The original source and input were banked before the production build. Every full template shard was banked after that build. Each reader output was retained before the next query, and all full output and condition files were banked before documentation and publication. This chronology preserves the original production evidence.

## Limits

This is a reusable exact finite index for explicitly supplied small tree/base-graph data. Its actual count is for one declared host and one declared labelled tree. A polynomial-looking query interface does not change the constructor's exponential template enumeration or the reader's finite scans. No worst-case efficient embedding algorithm is claimed.

The finite result does not classify all trees on thirteen vertices, all thirty-vertex graphs, induced copies, vertex-image sets or graph isomorphism classes. It neither re-proves the general Erdős–Sós assertion nor changes its source-reported status. The accepted host remains an identified premise; classical construction and theorem attributions are preserved.
