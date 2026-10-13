# Complete six-vertex regular induced subgraphs

This package classifies every labelled simple graph on six vertices by all of its regular induced vertex subsets. The complete universe has 32,768 graphs and 64 vertex subsets per graph. The saved classification contains 916,268 nonempty regular-subset occurrences, plus one explicitly normalized empty record per graph.

The finite guarantee is F(6)=3: every six-vertex graph has a regular induced subset of at least three vertices, and 3,480 labelled graphs have no larger one. The complete graph-size distribution is:

| Largest regular induced subset | Labelled graphs |
| ---: | ---: |
| 3 | 3,480 |
| 4 | 26,830 |
| 5 | 2,286 |
| 6 | 172 |

The saved reader exports all 3,480 worst-case graph masks, exact regular-subset profiles and filtered navigation. These are labelled counts, not counts up to graph isomorphism. This finite result makes no assertion about F(n)/log(n) as n tends to infinity and claims no mathematical priority for F(6).

## Source conventions

Alon, Krivelevich and Sudakov, *Large nearly regular induced subgraphs*, arXiv:0710.2106 (original 10 October 2007; v2 25 February 2008), define f(n,c) through induced subgraphs whose maximum degree is at most c times their minimum degree. They explicitly identify c=1 as the regular case and credit the corresponding problem to Erdős, Fajtlowicz and Staton.

The inspected author abstract is:
https://arxiv.org/abs/0710.2106

For a nonempty independent set, maximum and minimum degree are both zero, so the inequality includes degree-zero regularity. It is an inequality, not division by the minimum degree. No connectedness restriction appears in that definition. Exactly regular means all degrees within the selected induced graph are equal; c>1 is a broader condition. The abstract does not define degree extrema for the empty graph. This API therefore declares its empty convention separately below. The source was read for conventions, not bounds, proofs, examples, tables or a current-status survey.

The complete FormalConjectures source was separately read at content identity `93cca958022b8b95276e82e9a22ed46f5dc6adf9`, 1,889 UTF-8 bytes:
https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/82.lean

It defines F(n) as the largest size guaranteed in every n-vertex graph, annotates the superlogarithmic growth assertion as research open, and records a separately solved upper-bound variant with a local placeholder. Linked proofs were not inspected. Those annotations are source metadata; this finite computation is not an independent verification of the general problem's current frontier.

## Objects, labels and empty convention

The generic constructor accepts an integer vertex count from 1 through 6. Vertices are 0 through n-1. Possible edges are all pairs (u,v) with u<v, in lexicographic order. A graph mask has bit i set exactly when the i-th possible edge is present. There are no loops or multiple edges.

For n=6 the edge IDs are:

| IDs | Pairs |
| --- | --- |
| 0–4 | (0,1), (0,2), (0,3), (0,4), (0,5) |
| 5–8 | (1,2), (1,3), (1,4), (1,5) |
| 9–11 | (2,3), (2,4), (2,5) |
| 12–13 | (3,4), (3,5) |
| 14 | (4,5) |

Vertex subsets use an independent mask convention: bit v selects vertex v. For a selected vertex set S, every host edge with both endpoints in S is retained. A subset is regular precisely when these induced degrees agree at every selected vertex. Disconnected unions are permitted; a union of edges is regular only when its induced graph really has degree one everywhere. Extra host edges cannot be discarded to make a selected subset regular.

The empty subset is stored exactly once, in degree zero. It is not stored under every possible common-degree label. Singletons are also degree zero. This convention is useful for empty-filter queries and does not affect the nonempty six-vertex guarantee.

A graph family groups graphs by the maximum cardinality of a regular induced subset. A regular-subset family groups vertex masks within one fixed graph. These are different universes with separate rank/select operations.

## Files and complete data custody

| File | Purpose |
| --- | --- |
| `regular_induced_universe.cjs` | Dependency-free constructor and saved reader |
| `six_vertex_manifest.json` | Metadata, all global groups/profiles and row-shard identities |
| `six_vertex_rows_0.json` | Graph rows 0 through 8191 |
| `six_vertex_rows_1.json` | Graph rows 8192 through 16383 |
| `six_vertex_rows_2.json` | Graph rows 16384 through 24575 |
| `six_vertex_rows_3.json` | Graph rows 24576 through 32767 |
| `saved_reader_queries.json` | All 44 actual responses, complete worst-case pages and rank matches |
| `REGULAR_INDUCED_UNIVERSE_API.md` | Definitions, finite exhaustion, interface and limits |
| `README.md` | Entry point |

Executed source: `a4bb2daf1bd3b19e473bd61d835dcaeb2c947697`, 7,407 bytes. Complete input: `2b05eb5a3ba208951d344ad571762b84f7806881`, 318 bytes; its fields are embedded in the snapshot.

The original complete compact snapshot has identity `437c42504bc57f62a679596625c3b21a48894170`, 2,297,707 bytes. It was banked before sharding. The four complete row shards and the manifest reconstruct that exact text, including property order and its terminal newline. Reconstruction was checked as byte identity only; it did not replay graph enumeration or degree calculations.

| Data file | Bytes | Git blob |
| --- | ---: | --- |
| six_vertex_manifest.json | 491,918 | fa4771ab9ab299c642adf42ce68416abc5c1a3e5 |
| six_vertex_rows_0.json | 491,964 | 118c6759ce0c5e3ab16fca22578263999f310a26 |
| six_vertex_rows_1.json | 529,462 | d02d52a82348e591356909fa6a222e1c2db4eed1 |
| six_vertex_rows_2.json | 533,745 | 1bc0d2bb16fde81ae56f13f9488c3a8e4d68c01f |
| six_vertex_rows_3.json | 553,370 | 28bbed0444f05612db065511ab3fb5eb86cf8c0c |

The reader packet has identity `b8d47a371760eff42e902284d86fa376078d1b19`, 103,725 bytes. Every individual reader response was banked before the next query.

The manifest format is `regular-induced-universe-shards-v1`. Its `snapshot` contains all fields of the original snapshot, with `rows: null` in its original position. Its ordered `row_shards` gives path, first graph, graph count, byte count and identity for each complete array. After reading and checking those files, assembly is:

```javascript
const snapshot = {
  ...manifest.snapshot,
  rows: rowShards.flat()
};
const completeText = JSON.stringify(snapshot) + "\n";
```

Here `rowShards` means the four parsed JSON arrays in manifest order. The spread preserves the existing rows key's position when it is replaced. This snippet documents assembly; the actual reader consumed the already assembled, byte-matched snapshot. No mathematical construction is necessary to open these saved data.

## Exhaustive construction

`buildIndex({vertices: n, ...provenance})` visits every possible simple graph. It uses binary reflected Gray order, g(t)=t xor (t>>1), for t from zero through 2^m-1, where m=binomial(n,2). This is a bijection of graph masks. Consecutive masks differ in one edge, so the adjacency masks can be updated by toggling that edge's two endpoint bits. Results are stored by the ordinary numerical graph mask, not by Gray traversal position.

For each graph, the constructor visits every nonempty vertex mask. It counts each selected vertex's neighbors within that same mask. Equal degrees accept the subset; the first differing degree rejects it. Stopping at a mismatch cannot discard a regular subset, since two unequal degrees already refute regularity. Visiting all graph masks and all vertex masks proves complete finite coverage. There is no random sampling, graph-isomorphism reduction or omitted connectedness case.

Each graph row is

[maximumSize, maximumCount, degreeBits0, ..., degreeBits(n-1)].

The degree bitfields are lowercase hexadecimal strings. In degreeBitsd, bit S is one exactly when vertex mask S is a regular induced subset of common degree d. The bit position is the integer subset mask S, not a vertex ID or a cardinality. Thus each field has at most 2^n bits. The normalized empty record is bit zero of degreeBits0.

The remaining snapshot fields are `format`, `input`, `vertices`, `edges`, `subsets`, `maximum_groups`, `occurrences_by_size_degree`, `summary`, and `work`. Format is `regular-induced-universe-v1`. The `subsets` table stores each mask, its size and its vertices. Each maximum group is a complete increasing list of graph masks. The occurrence table counts (graph, selected subset) incidences by size and regular degree, not distinct subsets without their host.

The constructor enumerates the complete finite graph/subset universe. Its actual counters were:

| Counter | Actual |
| --- | ---: |
| graph_count | 32,768 |
| gray_edge_toggles | 32,767 |
| nonempty_subset_checks | 2,064,384 |
| internal_degree_counts | 4,624,470 |
| regular_nonempty_subsets | 916,268 |
| empty_records | 32,768 |

This is explicitly exponential finite preprocessing. It is not a fast general graph algorithm.

## An elementary proof of F(6)=3

The computed finite guarantee has a short independent explanation.

Choose any vertex in a six-vertex graph. Among its other five vertices, at least three are neighbors or at least three are nonneighbors. Three neighbors either contain an edge, giving a triangle with the chosen vertex, or form an independent triple. Three nonneighbors either form a triangle, or contain a nonedge whose two endpoints together with the chosen vertex form an independent triple. Every six-vertex graph therefore has a triangle or an independent triple; either is regular.

For the reverse bound, take a triangle on vertices 0,1,2 and private pendant leaves 3,4,5 attached respectively to 0,1,2. This is the net graph, mask 2215 in the declared edge order. If a regular induced subset contains a leaf, its common degree is zero or one. Degree zero permits at most three vertices, since the three disjoint pendant edges partition all six vertices and an independent set takes at most one endpoint of each. Degree one would be an induced matching; two distinct edges cannot form an induced matching here. Two pendant edges have adjacent triangle endpoints, while a triangle edge and the remaining pendant edge have additional triangle cross-edges. Hence degree-one regular subsets have at most two vertices. A subset with no leaf lies inside the three-vertex triangle. The net graph has no regular induced subset larger than three.

These elementary finite arguments explain the guarantee and one extremal example. They do not replace or independently establish the complete labelled distribution of 3,480 extremal graphs, which is supplied by the actual exhaustive index. They do not claim priority or an asymptotic improvement.

## Saved-reader contract

`openIndex(snapshot)` returns `{query, stats}`. It checks the format and outer row count. It trusts the identified constructor output; it is not a complete hostile-input validator or a formal proof checker. It does not enumerate the graph universe or recompute induced degrees.

Vertex-subset queries use `graph` as a numerical graph mask. Their optional filters are:

| Field | Meaning |
| --- | --- |
| `size` | Exact subset cardinality, integer 0 through n |
| `degree` | Exact saved regular degree, integer 0 through n-1 |
| `required` | Vertex mask that must be contained; default 0 |
| `forbidden` | Vertex mask that must be disjoint; default 0 |
| `largest` | Boolean: restrict to maximum-size regular subsets of the original graph |

The `largest` filter refers to the unfiltered graph maximum. It does not mean the largest subset after other restrictions. To find the largest size under required/forbidden/degree filters, use `profile` without `largest`; its returned maximum is over the filtered family. Required and forbidden masks may overlap, in which case the result is empty. An empty family has maximum_size null and maximum_count "0".

All subset families are ordered by increasing numerical vertex mask. This is not lexicographic order of the displayed vertex lists. Selection and ranking apply to the exact supplied filters. Unspecified degree includes every saved common-degree class, counting the empty subset once.

| Operation | Fields | Result |
| --- | --- | --- |
| `summary` | none | Complete finite-universe summary |
| `graph` | `graph` | Decode selected graph edges and return its saved row information |
| `subset` | `mask` | Saved subset size and vertex list |
| `global_profiles` | none | Graph-maximum histogram and all degree/size incidences |
| `profile` | `graph`, optional filters | Filtered count, maximum and complete size/degree histogram |
| `count` | same | Same exact count/profile information |
| `select` | `graph, rank`, optional filters | One regular subset |
| `rank` | `graph, mask`, optional filters | Rank of a regular subset in that filtered family |
| `page` | `graph, start, limit`, optional filters | A bounded slice of regular-subset records |
| `graph_select` | `maximum_size, rank` | One graph in a saved maximum-size group |
| `graph_rank` | `graph` | Its saved maximum group and rank |
| `graph_page` | `maximum_size, start, limit` | A bounded slice of graph masks in that group |

Ranks and page starts are nonnegative canonical decimal strings of at most 4,096 characters. Page limits are integers 0 through 1,000. A start at the family count yields an empty page; a larger start or a selection rank outside the family is rejected. An invalid subset rank request is rejected if the mask does not belong to the filtered family. All graph, vertex-mask, degree and size inputs have explicit bounds.

The reader filters saved degree bitfields by checking subset masks and saved sizes. Those scans are new query work; they are not degree classification. A `graph` query decodes its existing graph mask into the declared edge labels, counting those bit inspections. It does not traverse all graph masks or rerun the Gray-code construction.

## Actual query evidence

The reader retained 44 complete responses. Four graph pages exported all 3,480 worst-case masks. Their first, selected middle and last entries were:

| Rank among worst-case graphs | Graph mask |
| ---: | ---: |
| 0 | 619 |
| 1739 | 16212 |
| 3479 | 32148 |

All three selected graph ranks were recovered exactly. The net graph 2215 has rank 212 in that same group. Its complement, mask 30552, also has largest regular-subset size three; both complete profiles are retained.

The net graph has 27 regular-subset records including the empty set: 20 degree-zero records, six degree-one pairs and one degree-two triangle. Its five largest subsets are:

| Vertex mask | Vertices | Regular degree |
| ---: | --- | ---: |
| 7 | [0,1,2] | 2 |
| 28 | [2,3,4] | 0 |
| 42 | [1,3,5] | 0 |
| 49 | [0,4,5] | 0 |
| 56 | [3,4,5] | 0 |

Requiring vertices 3 and 4 (mask 24) leaves three regular subsets, with two of size three. Also forbidding vertex 5 leaves two subsets, with one of size three. Requiring and forbidding vertex 0 simultaneously gives an empty family. Filtering degree one together with `largest:true` also gives an empty net-graph family: its degree-one subsets have size two, whereas its original maximum is three. The empty-size page returns the one normalized empty record.

The empty graph and complete graph each have all 64 vertex subsets regular. Their degree assignments differ. The complete graph's full six-vertex subset has degree five and count one, as shown by a retained filtered query.

Four subset select/rank pairs matched exactly, covering the net graph's largest, independent and degree-one families and the first worst-case graph's largest family.

| Reader counter | Actual |
| --- | ---: |
| queries | 44 |
| graph_row_reads | 32 |
| subset_checks | 1,472 |
| saved_degree_bit_tests | 2,132 |
| edge_bit_decodes | 75 |
| group_reads | 14 |

These counters describe instrumented operations, not every memory copy or arithmetic instruction. The complete reader packet includes both graph and subset comparisons and explicitly records that graph-universe construction, induced-degree classification and global-profile construction were not replayed.

The result is a complete labelled six-vertex classification with finite navigation. It does not establish the conjectured asymptotic growth, independently validate any linked formal proof, or infer payout or mathematical novelty.
