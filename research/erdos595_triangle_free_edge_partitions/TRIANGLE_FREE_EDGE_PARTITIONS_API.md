# Triangle-free edge partitions and finite palette navigation

This index classifies partitions of the edge set of one labelled K₂,₂,₂ host into nonempty triangle-free blocks. It retains the same information for all 4,096 edge subgraphs of that twelve-edge host, with all six vertices kept. The full graph has 3,391,470 such unlabelled partitions. Its minimum is two blocks, attained by 225 partitions, giving 450 labelled two-colorings without a monochromatic triangle.

The API also supports arbitrary finite palette sizes as exact BigInts. The actual reader used q=10^100+19 and selected and recovered first, middle and last colorings without enumerating colors or assignments. All 69 complete responses, 21 inverse matches and all 225 minimum partitions are retained.

## Source and scope

The fully read [FormalConjectures Erdős595 statement](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/595.lean) asks for an infinite K₄-free graph that is not the union of countably many triangle-free graphs on the same vertex type. The covering graphs may overlap. It separately records the finite Folkman–Nešetřil–Rödl existence theorem as research solved, with a local placeholder. The main assertion is tagged research open and also has a placeholder. These are observed source annotations, not a proof audit or independent current-status certification.

The complete returned formal text has 10,868 bytes and local Git blob 5030564d5dfc749cb2f02b361b2f926ddf60374e. The request used the repository default ref; no immutable source commit was supplied. Its named references include Folkman (1970), Nešetřil–Rödl (1975), and an Erdős set-systems/hypergraphs account (1994). No construction or proof from those references was imported or replayed.

Rödl, Ruciński and Schacht's author-primary abstract, [Ramsey properties of random graphs and Folkman numbers](https://arxiv.org/abs/1603.00517), v2 dated 15 July 2016, defines G→(F)_r through every r-coloring of E(G) containing a monochromatic F. For F=K₃, its negation is precisely a coloring in which no host triangle has all three edges the same color. This is Ramsey edge coloring; edges sharing a vertex may have the same color. The abstract, rather than the PDF or proof, was read.

This API explicitly defines a q-coloring as a map E→{0,...,q−1}, permitting unused labels. The source abstract does not separately discuss surjectivity, so this empty-class convention is declared here. The source's r≥2 framing is extended by the API's explicit q=0 and q=1 conventions.

Three representations remain distinct:

- An overlapping cover has triangle-free spanning graphs whose edge union is the host.
- An unlabelled edge partition has disjoint, nonempty triangle-free blocks.
- A labelled coloring assigns exactly one palette label to every active edge and may leave some palette labels unused.

The cover/coloring equivalence is supplied by the fully read formal source; it is not a new theorem here. The finite consumer counts partitions and colorings, not overlapping-cover multiplicities. Its result on one finite graph neither proves the infinite assertion nor re-proves the known finite existence theorem. This host is two-colorable in the stated Ramsey sense and is not presented as a new Folkman obstruction.

## Exact inherited host

The input copies pattern 0 from [#31834](https://github.com/woahwhattheheck/commons/pull/31834), merge 48d400e8ddad6995d7ae9fd01fd2564e88ab10b4, directory research/erdos579_octahedron_independence_index/. The complete prior snapshot has blob fbec24c52dc1a50933668502962eeed26cc45596. Only its parts, required-edge IDs and mask, and vertex/edge labels are consumed.

The parts are {0,1}, {2,3}, {4,5}. All cross-part edges are present and no within-part edge is present. Hence a clique can contain at most one vertex from each part, so this declared host is K₄-free. This direct input observation does not repeat the old six-vertex graph census, independence calculation or octahedron-copy classification.

The prior complete-graph edge mask is 15870. The present twelve-edge local encoding is:

| Local edge bit | Endpoints |
|---:|---|
| 0 | 0, 2 |
| 1 | 0, 3 |
| 2 | 0, 4 |
| 3 | 0, 5 |
| 4 | 1, 2 |
| 5 | 1, 3 |
| 6 | 1, 4 |
| 7 | 1, 5 |
| 8 | 2, 4 |
| 9 | 2, 5 |
| 10 | 3, 4 |
| 11 | 3, 5 |

A subgraph mask is an integer 0 through 4095, with bit i indicating the corresponding edge. It is an edge subset, not a vertex-induced subgraph. The empty mask retains six isolated vertices. The input is 1,187 bytes, blob 0fad9c786f94ac13e15ea9ce1e033ab552f7f1fe.

## Complete finite recurrence

The new compiler enumerates the twenty three-vertex sets of this host once and records its eight triangles. For every edge mask B it stores the first contained triangle ID, or −1 when B is triangle-free. This is the new constraint calculation; no old triangle table is consumed or recomputed.

Let P(S,k) be the number of partitions of edge subset S into exactly k nonempty triangle-free blocks. The base row is P(∅,0)=1, with its other entries zero. For nonempty S, let e be its least-labelled edge. Then

    P(S,k) = Σ P(S minus B,k−1),
             over triangle-free B⊆S containing e.

Every partition has exactly one block containing e. Removing that block leaves a partition of the remaining edges, and conversely adjoining such a block gives a unique partition. Thus the recurrence counts each unlabelled partition once. Canonical block order repeatedly takes the block containing the least remaining edge.

All candidate blocks, retained branches and coefficient rows are completed and stored. Branch lists use increasing numerical block-mask order. No list of millions of complete partitions is built by the constructor.

| Number of nonempty blocks k | Full-host P(E,k) |
|---:|---:|
| 0 | 0 |
| 1 | 0 |
| 2 | 225 |
| 3 | 34404 |
| 4 | 382773 |
| 5 | 1067766 |
| 6 | 1148428 |
| 7 | 581140 |
| 8 | 153055 |
| 9 | 21915 |
| 10 | 1697 |
| 11 | 66 |
| 12 | 1 |

The coefficients sum to 3,391,470. They count partitions, with no factor for permuting block names. In particular, the 225 two-block partitions become 450 labeled two-colorings because each permits two distinct assignments of the two labels.

| Once-only construction work | Value |
|---|---:|
| Vertex triples / triangle constraints | 20 / 8 |
| Edge masks / triangle-containment tests | 4,096 / 22,519 |
| Triangle-free masks, including empty | 1,699 |
| Candidate least-edge blocks | 265,720 |
| Retained branch records | 184,072 |
| Coefficient cells / additions | 53,248 / 2,208,864 |
| Old graph census, independence or octahedron work | 0 |

The source limits vertices to twelve and edges to sixteen, with separate coefficient and branch budgets. Those budgets can stop a larger proposed input; they are not a promise that every syntactically bounded input completes. This actual twelve-edge run stayed inside the declared limits. No cap was increased and no partial run was retried.

## Finite palette formula and rank order

For q≥0, write (q)_k=q(q−1)...(q−k+1), with (q)_0=1 and (q)_k=0 for k>q. A k-block partition admits exactly (q)_k injective assignments of palette labels to its canonically ordered blocks. Therefore the number of q-colorings without a monochromatic triangle is

    F_S(q) = Σ_(k=0)^12 P(S,k) (q)_k.

Unused colors are allowed. Empty S has exactly one coloring even when q=0. A nonempty edge set has no zero-coloring.

The reader caches a falling-factorial row for each requested q and the resulting palette profile for each (S,q). These are new query multiplications/additions, recorded separately from the saved partition recurrence. It never loops over all q labels.

Coloring order is explicitly:
1. increasing number k of used colors;
2. saved canonical partition rank among k-block partitions;
3. lexicographic order of the distinct label tuple assigned to those blocks.

This is not numerical or lexicographic order of the full edge-color array. For each k-bucket, the inner size is P(S,k)(q)_k. Select splits the local rank into partition rank and injection rank. At injection position i, all unused labels have the same suffix count (q−i−1)_(k−i−1). Integer division gives the chosen label's rank among unused labels; at most twelve already-used labels are skipped. Rank performs the inverse operation.

The exact full-host palette counts include:

| q | F_E(q) |
|---:|---:|
| 0 | 0 |
| 1 | 0 |
| 2 | 450 |
| 3 | 207,774 |
| 5 | 176,133,420 |

The complete decimal count for q=10^100+19 and its navigation traces are in saved_reader_queries.json.

## Public reader

~~~javascript
const fs = require('fs');
const {loadIndex} = require('./load_saved_index.cjs');
const {openIndex} = require('./triangle_free_edge_partitions.cjs');
const read = p => JSON.parse(fs.readFileSync(p,'utf8'));
const data = loadIndex(read('edge_partition_manifest.json'),read);
const api = openIndex(data);
const count = api.paletteProfile(4095,'3');
const selected = api.colorSelect(4095,'3','103887');
const inverse = api.colorRank(4095,'3',selected.edge_colors);
~~~

This example documents CommonJS reuse. The actual source and reader were loaded unchanged in V8; no native executor or Node CLI was used.

| Method | Contract |
|---|---|
| compile(input), openIndex(saved) | Once-only construction, then trusted structural reopening. |
| summary(), profile(mask) | Complete saved coefficients, total and minimum block count. |
| triangleWitness(mask) | Saved first triangle or triangle-free outcome. |
| partitionSelect(mask,k,rank) | Canonical blocks, edge IDs and every chosen branch. |
| partitionRank(mask,blocks) | Accept blocks in any order, canonicalize, then return rank or a monochromatic-triangle obstruction. |
| partitionPage(mask,k,start,limit) | At most 100 consecutive unlabelled partitions. |
| paletteProfile(mask,q) | Exact polynomial value and every used-color bucket. |
| colorSelect(mask,q,rank) | Blocks, assigned colors, complete edge-color array and traces. |
| colorRank(mask,q,colors) | Inverse rank or a saved monochromatic triangle. |
| colorPage(mask,q,start,limit) | At most 30 consecutive labeled colorings. |
| exportCaches(), work() | Complete actual query caches and operation counts. |

Masks and block counts are exact bounded Numbers. Palette sizes and ranks accept nonnegative BigInts, decimal strings or safe integer Numbers. Block masks must be nonempty, pairwise disjoint and cover the requested edge mask. A color array has twelve entries: exact palette labels at active edges and null at inactive edges. Wrong shape, out-of-range palette labels and out-of-range selections raise an error. A correctly shaped coloring with a monochromatic triangle returns rank null with the saved triangle. An empty family has an empty page at start zero.

The loader checks shape and shard boundaries; it does not authenticate adversarially replaced evidence or independently prove completeness. Input/source provenance is an explicit premise.

## Actual reader evidence

The first saved-data consumer retained 69 responses and 21 inverse matches. It queried empty, star, triangle, single-edge-deleted and full masks; all six palette sizes; first/middle/last colorings for three palettes; and canonical partitions with 2,3,6 and 12 blocks. Coincident endpoint ranks of a singleton family were requested only once.

Three pages export all 225 minimum two-block partitions, with page sizes 100,100,25. The last three two-colorings are retained. The q=1 full-host page is empty. The empty graph at q=0 and a four-edge star at q=5 were selected and ranked back. An all-one-label full-host coloring returns an actual monochromatic-triangle witness.

The 21 inverse matches consist of nine coloring ranks for the full host, ten unlabelled partition ranks, and the empty/star coloring ranks. The q=10^100+19 selections use exact integer arithmetic throughout.

| Fresh reader work | Value |
|---|---:|
| Saved coefficient / branch reads | 112,846 / 112,579 |
| Partition rank additions | 5,832 |
| Selected partitions, including page/color consumers | 249 |
| Falling-factorial multiplications | 72 |
| Palette multiplications / additions | 104 / 104 |
| Injection divisions / label comparisons | 94 / 200 |
| Edge-bit decodes | 6,684 |
| New triangle tests, partition coefficients or branches | 0 |

Every response was banked before the next query. Source, input and construction output were retained before the respective runs. Construction and reader completed without an exception or lost response. These work counts are not timing benchmarks.

## Complete storage

The original complete snapshot is 1,074,406 bytes, blob db8d67702ee953fdd185d3d54743b3026e7e388c. Three complete state shards use rows

    [firstBadTriangle, branches, partitionCoefficients, partitionTotal]

in mask order. edge_partition_manifest.json contains all other data, with the four arrays set to null until structural loading. The decoder restores their original property order. Compact JSON plus a final newline matched the complete original snapshot exactly, without recomputing a triangle, branch, coefficient or query.

| Shard | First mask | Rows | Bytes | Blob |
|---|---:|---:|---:|---|
| edge_states_00.json | 0 | 2483 | 479914 | a8b8d8bf7f28cd1d13800e86b7d546b86ff6cb68 |
| edge_states_01.json | 2483 | 1459 | 479806 | 7b61fdbe2eee19ff1e018aeec11cf48583272049 |
| edge_states_02.json | 3942 | 154 | 120496 | 9bc8d55ff9a0c741136b743885c6284a50df0d84 |

Other exact identities:
- Source: 385d896c01d2f6126c74c528f944405a5f14f11d, 10,290 bytes.
- Structural loader: 9db3f794179b25b51b1456ad3f7880e7adcaae32, 588 bytes.
- Manifest: a1fc325454006df5c1b9b77c008b29ce79907b90, 3,036 bytes.
- Complete reader output and caches: 2165300bfd9cc83936bdca7c690b543e6836ea16, 290,486 bytes.

These finite edge-subgraph and palette results neither settle the infinite countable-cover question nor establish a new finite Ramsey/Folkman theorem, record, priority, sponsor acceptance or prize.
