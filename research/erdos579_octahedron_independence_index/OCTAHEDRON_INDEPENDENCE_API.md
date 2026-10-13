# Octahedron copies and independent sets on six labelled vertices

This package adds a new joint index to the accepted six-vertex graph universe from [Commons #31710](https://github.com/woahwhattheheck/commons/pull/31710). It consumes that package's complete degree-zero subset bitfields as the identified independent-set premise. It does not reconstruct its adjacency masks, induced degrees, regularity decisions or old finite guarantee.

The new classification visits all **32,768 labelled simple graphs** on vertices 0 through 5. Exactly **32,692 are octahedron-free**. Their maximum edge count is **13**, attained by **60 graphs**, each with independence number two. The complete joint family has 36 profiles by edge count, independence number and octahedron-copy count. All sixty maximum-edge free graphs and all seventy-six graphs containing an octahedron are exported by the saved reader.

These are finite results on six fixed labels. They do not establish a Ramsey–Turán statement for unbounded n, transfer a finite density cutoff to large graphs, claim a new extremal record, or assert prize/sponsor progress.

## Sources and exact conventions

The [FormalConjectures Erdős579 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/579.lean) was fully returned at its default ref. The observed 3,230 UTF-8 bytes have Git blob identity `20f0234f3a9831f61a228bf1e48b9f630bb62a0f`; this content identity is not an independently resolved upstream commit.

It defines the octahedron as the complete tripartite graph K2,2,2 and uses ordinary forbidden-subgraph containment. It asks whether, for every delta>0, all sufficiently large octahedron-free graphs with at least delta*n^2 edges have an independent set of at least c*n vertices for some positive c depending on delta. The main assertion is annotated research open. A separate delta>1/8 variant is annotated solved, with its own local placeholder. No linked or Lean proof was reviewed or executed.

The actually read original paper is Erdős, Hajnal, Sós and Szemerédi, [More results on Ramsey–Turán type problems](https://www.renyi.hu/~p_erdos/1983-09.pdf), Combinatorica 3 (1983), 69–81. Definition 1.1 on pages 69–70 supplies the edge-maximization and independent-set setup: forbidding an independent set of size l means alpha(G)<l. That initial definition is framed with clique restrictions on edge classes, so this package does not attribute an explicit K2,2,2 definition to that passage. The exact octahedron convention comes from the complete formal statement. An independent Cambridge primary indexed snippet identifies the octahedron as K2,2,2, but its direct DOI `10.1017/S0963548322000074` was inaccessible and remains an access gap; no full-paper convention is attributed to it.

An octahedron copy here is a distinct spanning twelve-edge subgraph obtained by partitioning the six vertices into three unordered pairs and taking all edges between different pairs. Edges within a pair may be present in the host graph. This is therefore not an induced-octahedron condition. The counted objects are distinct required edge sets, not all labelled embeddings, vertex permutations or isomorphism classes. The complete graph contains fifteen such edge-set copies, even though it is not an induced octahedron.

Independent sets are vertex subsets containing no internal edge, represented here by the inherited degree-zero bitfields. The empty set is present as the old API's declared convention, but the maximum independent set of a nonempty six-vertex graph is never empty. Isolated vertices and disconnected graphs are retained.

The density normalization is **edge_count/36**, because the formal inequality is edge_count >= delta*n^2 with n=6. It is not the fraction edge_count/15 of all available edges. Threshold comparisons use a non-strict edge inequality; a positive denominator and exact integers are required. The finite API also permits delta=0 as an explicit boundary query, beyond the positive-delta scope of the conjecture.

## Literal accepted input custody

The new `input6.json` is 497107 bytes, blob `46707cd53959e073eb513f19dc27d8711ea06fc4`. It copies the fifteen edge labels, all sixty-four subset-size/vertex records, and row field 2 from every accepted graph row. In the old row schema `[maximumSize, maximumCount, degreeBits0, ..., degreeBits5]`, field 2 is the complete degree-zero bitfield. Bit S means vertex mask S, not vertex ID S.

The retained immutable carrier is commit `b31ce2319839cfcebae956e9e63757b355ee9fb1`, directory `research/erdos82_regular_induced_universe/`:

| Identified old file | Bytes | Blob |
|---|---:|---|
| `six_vertex_manifest.json` | 491,918 | `fa4771ab9ab299c642adf42ce68416abc5c1a3e5` |
| `six_vertex_rows_0.json` | 491,964 | `118c6759ce0c5e3ab16fca22578263999f310a26` |
| `six_vertex_rows_1.json` | 529,462 | `d02d52a82348e591356909fa6a222e1c2db4eed1` |
| `six_vertex_rows_2.json` | 533,745 | `1bc0d2bb16fde81ae56f13f9488c3a8e4d68c01f` |
| `six_vertex_rows_3.json` | 553,370 | `28bbed0444f05612db065511ab3fb5eb86cf8c0c` |

These complete source bytes were already retained locally. Their identities matched before projection; no provider fetch or mathematical re-evaluation of the old data was necessary. The old guide and source establish the row and edge labels. The input does not import the old maximum-regular-subset results as a new finding.

Possible edges are lexicographic unordered pairs (u,v), u<v. A fifteen-bit graph mask selects them. The supplied vertex-subset table uses bit v for vertex v. The constructor trusts the semantic completeness of the saved independent-set fields; new structural size checks do not independently reprove that old classification.

## New construction and exhaustive family argument

The pairing recursion takes the least unpaired vertex and pairs it with each remaining vertex in increasing order, then recurses. It produces every partition into three pairs once: the pair containing the least vertex is forced by the partition, and the same argument applies to the remaining vertices. There are fifteen retained pair partitions. For each, the compiler records twelve required cross-pair edge IDs, three optional within-pair IDs and the required-edge mask.

For each of the 32,768 existing graph records, a pattern occurs exactly when every required edge is present. Additional host edges are ignored for this membership condition. The bitset of all occurring pattern IDs and its count are saved. On exactly six vertices, these fifteen patterns exhaust ordinary K2,2,2 copies because a copy uses all six distinct vertices.

The independence maximum is a new aggregate derived from the saved bits: visit each set bit, look up its already stored cardinality, retain the greatest cardinality, count all maximizers and store their complete bitfield. No edge or degree condition is recomputed. The graph's edge count is a fresh population count of its supplied numerical graph mask. Each graph enters one complete profile bucket (edges, alpha, copies), and every bucket retains its increasing list of graph masks.

Thus the constructor performs new copy tests and aggregation while preserving the old graph/independent-set results as premises. The counter `old_graph_enumeration: 0` means that the old Gray-order adjacency generator is not called; the new compiler does of course visit all 32,768 saved graph positions.

| New construction work | Actual value |
|---|---:|
| Pairing recursion nodes | 36 |
| Pair partitions | 15 |
| Pattern edge checks | 225 |
| Existing graph-row visits | 32,768 |
| Edge-popcount steps | 245,760 |
| Octahedron mask tests | 491,520 |
| Saved independent-bit reads | 2,097,152 |
| Saved independent-size lookups | 564,929 |
| Joint profile insertions | 32,768 |
| Old adjacency / induced degrees / regularity | 0 / 0 / 0 |

Source and isolated input were banked before this one call. The output was banked before the reader. The implementation accepts this exact six-vertex input shape, not an arbitrary graph size. Family preprocessing is exhaustive and finite; no improved general graph algorithm is claimed.

## Complete finite findings

| Octahedron edge-set copies | Graphs |
|---:|---:|
| 0 | 32,692 |
| 1 | 60 |
| 3 | 15 |
| 15 | 1 |

No other copy count occurs in this universe. These are labelled graph counts. The fifteen possible patterns are themselves fully retained, not selected examples.

The threshold table below applies only to octahedron-free graphs, with at least the indicated number of edges. `null` means the eligible family is empty, rather than that its independence number is zero.

| Minimum edges | Eligible graphs | Minimum alpha | Graphs attaining it |
|---:|---:|---:|---:|
| 0 | 32,692 | 2 | 5,713 |
| 1 | 32,691 | 2 | 5,713 |
| 2 | 32,676 | 2 | 5,713 |
| 3 | 32,571 | 2 | 5,713 |
| 4 | 32,116 | 2 | 5,713 |
| 5 | 30,751 | 2 | 5,713 |
| 6 | 27,748 | 2 | 5,713 |
| 7 | 22,743 | 2 | 5,703 |
| 8 | 16,308 | 2 | 5,598 |
| 9 | 9,873 | 2 | 4,938 |
| 10 | 4,868 | 2 | 3,378 |
| 11 | 1,865 | 2 | 1,605 |
| 12 | 500 | 2 | 480 |
| 13 | 60 | 2 | 60 |
| 14 | 0 | null | 0 |
| 15 | 0 | null | 0 |
| 16 | 0 | null | 0 |

The finite maximum-edge conclusion is encoded by all sixty thirteen-edge free graphs and the empty family at fourteen edges. No claim about the known literature value or a new record is made. The independently obtained six-vertex independent-set records remain the accepted premise throughout.

## Saved reader and ordering

```js
const fs = require('node:fs');
const {openIndex} = require('./octahedron_independence_index.cjs');
const manifest = JSON.parse(fs.readFileSync('snapshot_manifest.json', 'utf8'));
const rows = manifest.shards.flatMap(s =>
  JSON.parse(fs.readFileSync(s.path, 'utf8')));
const reader = openIndex({...manifest.snapshot, rows});
const maxFree = {min_edges: 13, max_copies: 0};
const all = reader.page('0', 60, maxFree);
const inverse = reader.rank(all.records[0].graph, maxFree);
const atOneThird = reader.threshold('1', '3');
```

This documents CommonJS reuse. The actual execution loaded unchanged source in V8; no Node CLI, native executor or filesystem process was used.

| Method | Contract |
|---|---|
| `compile(input)` | New pair-pattern/copy/independence aggregation over the supplied universe. |
| `openIndex(saved, caches?)` | Open saved records and optional complete condition caches. |
| `summary()`, `profiles()`, `frontier()` | Complete saved summaries. |
| `patterns()`, `pattern(id)` | Complete canonical pair partitions and edge requirements. |
| `graph(mask)` | Saved edge count, alpha, all maximum independent witnesses and occurring pattern IDs, plus decoded edges. |
| `count(options)` | Exact labelled family count. |
| `select(rank, options)`, `rank(mask, options)` | Exact zero-based navigation and membership. |
| `page(start, limit, options)` | Up to 1,000 records with explicit next-page rank. |
| `threshold(numerator, denominator)` | Exact rational density cutoff within the octahedron-free universe. |
| `caches()`, `work()` | All condition caches and fresh-reader counters. |

Options use inclusive minimum/maximum bounds for edges, alpha and copies, plus distinct edge-ID arrays `require` and `forbid`. Required/forbidden overlap gives an empty family. Unspecified copy bounds include every graph; use `max_copies:0` for the free family. Profiles are ordered by edge count, then alpha, then copy count, each ascending; graph masks are increasing within each profile. This is not numerical graph-mask order across different profiles or an isomorphism order.

Rank and threshold integers accept exact decimal strings, BigInt and safe Numbers. Graph masks and filter bounds use safe nonnegative integer Numbers. Invalid labels, duplicate required/forbidden IDs, unsafe numeric integers, negative ranks and ranks beyond a family are rejected. An endpoint page starting at the family count is empty. Saved records and caches are trusted constructor output, not a hostile-input proof format.

A family cache stores qualifying profile segments and cumulative starts. An unrestricted segment references its original graph list. An edge-constrained segment retains the exact qualifying positions in that list. Queries read saved graph/copy/independence profiles; they perform no new octahedron-containment or independence tests.

To answer a density a/b, the reader computes k=ceil(36a/b) exactly, then reads the saved threshold row. If k exceeds 16 it uses the empty row 16; `required_edges` still returns the exact, potentially huge k and `saved_threshold_row` separately identifies the lookup row. There is no floating-point rounding or claim that 16 is the original requested threshold.

## Actual first-reader evidence

`saved_reader_queries.json` contains **90 complete responses** and **66 rank/select inverse matches**. Every one of the sixty maximum-edge free graphs is exported and ranked back. All seventy-six containing graphs are exported, including the complete graph with fifteen ordinary edge-set copies. All fifteen pair partitions, every profile and the entire threshold frontier are retained in actual reader responses.

| Additional free-family condition | Count |
|---|---:|
| At least 10 edges and alpha at least 3 | 1,490 |
| At least 10 edges, require IDs 0,1,5 | 1,540 |
| At least 10 edges, forbid IDs 0,9,14 | 78 |
| At least 13 edges, require IDs 0,9,14 | 36 |
| At least 14 edges | 0 |
| Require and forbid ID 0 | 0 |

At density 1/8 the exact threshold is five edges, leaving 30,751 free graphs. At 1/3 it is twelve edges, leaving 500. At 13/36 it is thirteen edges, leaving sixty; at 7/18 it is fourteen edges, leaving none. The stored queries at (10^80−1)/(3*10^80) and (10^80+1)/(3*10^80) distinguish twelve from thirteen required edges exactly. A huge density 10^100 also returns the empty family while retaining its exact required-edge integer. These are finite lookup boundaries, not evidence for or against a large-n conjecture.

| Fresh reader work | Actual value |
|---|---:|
| Complete family caches | 8 |
| Profile scans | 252 |
| Saved graph-mask scans | 9,796 |
| Condition bit checks | 19,592 |
| Cumulative additions / cache hits | 19 / 206 |
| Binary steps | 579 |
| Graph-record reads | 140 |
| Edge-decode checks | 2,100 |
| Saved maximum-witness bit reads | 8,960 |
| Saved copy-bit reads | 2,100 |
| Exact threshold divisions | 8 |
| New patterns / copy tests / independence maxima | 0 / 0 / 0 |

Graph materialization is fresh output work: it decodes the requested saved graph mask, maximum-independent bitfield and pattern bitfield. It is not an adjacency reconstruction, degree test, or proof recheck. Named counters are not a complete instruction count or benchmark.

## Complete files and serialization

The original compact output has 1535900 bytes and blob `fbec24c52dc1a50933668502962eeed26cc45596`. Four complete row shards plus the manifest reproduce it exactly. The manifest retains the original `rows` key as null; replacing it with concatenated shard arrays preserves property order. `JSON.stringify(assembled) + '\n'` matched the original bytes. That comparison is structural custody only, not mathematical replay.

Each new graph row is `[edgeCount, alpha, maximumIndependentCount, maximumIndependentBitsHex, octahedronBits, octahedronCount]`. Maximum-independent bit positions are vertex-subset masks; octahedron-bit positions are the fifteen canonical pattern IDs. All profile graph lists and all eight condition caches are complete.

| Artifact | Bytes | Blob |
|---|---:|---|
| `octahedron_independence_index.cjs` | 8752 | `9342a04f7cfde85c86fdb042d9813981a76eed29` |
| `input6.json` | 497107 | `46707cd53959e073eb513f19dc27d8711ea06fc4` |
| `snapshot_manifest.json` | 689446 | `685a87c60a5de47f02d8e2b203ca1e101bef6ddd` |
| `graph_rows_0.json` | 232961 | `7fc208c1aeb4f9dacc8404a4795624dc98adbb4f` |
| `graph_rows_1.json` | 217687 | `957ee465965e3eecb0ed4f58f9d8b362200a3e6f` |
| `graph_rows_2.json` | 206510 | `a7fc02de547a6fedebe0c66c2753423f88d10edd` |
| `graph_rows_3.json` | 190037 | `a315eabc249f03595ee6a6ddb4accc3a11e37b19` |
| `saved_reader_queries.json` | 493555 | `b49596bd287ae9493b3a5ab0afa29f65d33f082d` |
| `saved_condition_caches.json` | 9714 | `dbfe03e0706f6439e5b51d56e7e6ac0b4bb78cb8` |

Both the new constructor and reader completed once without an exception. No output is sampled, no actual response is missing, and no accepted graph/regularity construction was repeated. The exact six-vertex family remains separate from the asymptotic source question and its attributed research annotations.
