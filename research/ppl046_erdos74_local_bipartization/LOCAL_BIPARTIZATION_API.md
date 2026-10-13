# Complete local edge-bipartization profiles

## Result and current source boundary

This package computes the exact minimum number of edges to delete from every induced vertex subset of a finite labelled graph to make it bipartite. It retains the complete two-color cut transcript, all optimal vertex bipartitions, distinct minimum edge-deletion representatives, and navigation over the resulting local profile.

The sole actual graph is the established eleven-vertex Mycielski graph obtained from the five-cycle. Its local maxima for subset sizes \(0,\ldots,11\) are
\[
\boxed{[0,0,0,0,0,1,1,1,2,2,3,4]}.
\]
The full graph has 20 edges, minimum deletion number 4 and exactly five minimum deletion sets. The complete data covers 2,048 vertex subsets and 88,574 canonical cuts, including the empty cut.

This finite parameter is Definition 3.1, printed page 121, of [Erdős, Hajnal and Szemerédi, *On almost bipartite large chromatic graphs*, Annals of Discrete Mathematics 12 (1982), 117–123](https://renyi.hu/~p_erdos/1982-11.pdf). Their Problem 3, on page 123, asks how slowly the local deletion function can grow for an infinite-chromatic graph.

The [current FormalConjectures statement for Erdős 74](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/74.lean), observed at Git blob **bbf29b01a71c08497b96dcff85374dab9e916f07**, declares the arbitrary-\(f\to\infty\) question `research solved` with `answer(False)` and links an external Lean proof. Its local theorem body is a placeholder. The separate \(\sqrt n\) variant is annotated `research open`. These are the exact observed source annotations; the linked proof was not opened, audited or rerun. The earlier intake card's open label is not used as current evidence.

The finite computation supplies no infinite-chromatic construction, new disproof, resolution of the square-root variant, smallest-obstruction classification, novelty claim or external computational frontier.

## 1. Graph and parameter conventions

A graph is finite, simple and undirected. Vertices have fixed labels \(0,\ldots,N-1\); an edge is an unordered pair of distinct labels. Reversed or repeated input pairs describe the same edge and are deduplicated. Loops are rejected. Vertex subsets and colorings are not identified under graph isomorphisms.

For \(S\subseteq V(G)\), define
\[
\delta_G(S)=\min\{|D|:D\subseteq E(G[S]),\ G[S]-D
\text{ is bipartite}\}.
\]
The local profile is
\[
F_G(s)=\max_{\substack{S\subseteq V(G)\\|S|=s}}\delta_G(S),
\qquad0\le s\le N.
\]
The empty subset has deletion number zero. Only this finite range of sizes is returned.

The original paper defines the parameter using induced subgraphs. The actual set-comprehension in the observed formal source permits all finite subgraphs, despite an explanatory comment using the word “induced.” The two worst-case finite quantities agree. If \(H\) is any subgraph on vertex set \(S\), restrict a coloring that makes \(G[S]\) bipartite after \(\delta_G(S)\) deletions. It deletes at most that many edges from \(H\), so
\[
\delta(H)\le\delta(G[S]).
\]
Since the induced graph itself is among the subgraphs, the maximum is attained at it. Thus the stored profile controls every subgraph of the finite host, including those obtained by removing additional edges.

Restriction to a smaller vertex set also cannot increase the deletion number. In particular, \(F_G(s)\) is nondecreasing for \(0\le s\le N\). This is a finite-host statement and supplies no graph beyond the given vertex universe.

## 2. Source-defined Mycielski input

The construction is due to **Jan Mycielski**, *Sur le coloriage des graphes*, Colloquium Mathematicum 3 (1955), 161–162, DOI [10.4064/cm-3-2-161-162](https://doi.org/10.4064/cm-3-2-161-162). The original archive PDF returned an access error and was not retried. The construction and original attribution were read in the introductory section of the author-hosted [Lin–Liu–Zhu, *Multi-colouring the Mycielskian of Graphs*](https://www.calstatela.edu/sites/default/files/multicolomycillz.pdf), printed page 2 and reference [6].

For a base graph \(H\), retain its vertices and edges, make a disjoint twin copy \(u_v\) of every base vertex \(v\), and add an apex \(w\). Each base edge \(xy\) adds \(x u_y\) and \(y u_x\). The apex is joined to all twins. There are no other edges. The source states that this construction raises chromatic number by one and preserves clique number when the original clique number is at least two. The triangle-free, four-chromatic status of the \(C_5\) specialization is established source material, not a new chromatic computation here.

Our labels are:

| Role | Labels and incidences |
| --- | --- |
| Base five-cycle | \(0,1,2,3,4\), with \(i\) adjacent to \(i+1\bmod5\) |
| Twin of \(i\) | \(5+i\), adjacent to base \(i-1,i+1\bmod5\) and apex 10 |
| Apex | 10, adjacent to all five twins |

No twin is adjacent to its base mate or another twin. The source-defined construction produces \(5+10+5=20\) edges. Canonical edge IDs are the positions in this sorted list:
```json
[
  [0,1], [0,4], [0,6], [0,9], [1,2],
  [1,5], [1,7], [2,3], [2,6], [2,8],
  [3,4], [3,7], [3,9], [4,5], [4,8],
  [5,10], [6,10], [7,10], [8,10], [9,10]
]
```
The graph construction was consumed once. No chromatic-number search, triangle census or published numerical profile was replayed.

## 3. Minimum deletions as a complete cut calculation

For a vertex bipartition \(S=A\sqcup B\), allow either part to be empty. Its crossing edges form a bipartite graph. Deleting the noncrossing edges costs
\[
c_S(A)=e_G(A)+e_G(B),
\]
where \(e_G(T)\) is the number of host edges induced by \(T\). Hence
\[
\delta_G(S)\le\min_{A\subseteq S}\{e_G(A)+e_G(S\setminus A)\}.
\]

Conversely, take a minimum deletion set \(D\) and a proper two-coloring of \(G[S]-D\). Every retained edge crosses the coloring. A deleted edge that also crossed could be restored without destroying bipartiteness, contradicting minimum cardinality. Therefore \(D\) is exactly the noncrossing edge set of that coloring. This proves
\[
\boxed{\delta_G(S)=\min_{A\subseteq S}
\{e_G(A)+e_G(S\setminus A)\}}.                         \tag{1}
\]
Equivalently, it is the edge count minus the maximum crossing-edge count.

The constructor precomputes all induced edge counts. If \(v\) is the least vertex of a nonempty set \(S\), then
\[
e_G(S)=e_G(S\setminus\{v\})
+\bigl|N_G(v)\cap(S\setminus\{v\})\bigr|.               \tag{2}
\]
Numeric subset order places the smaller mask first, so (2) is available when needed. Every subsequent cut objective requires just two saved edge-count lookups and their sum.

### Canonical vertex bipartitions

Swapping \(A,B\) preserves the cut. For each nonempty \(S\), require its least vertex to lie in \(A\). There are exactly \(2^{|S|-1}\) such vertex bipartitions. They are ordered by increasing numeric \(A\)-mask. The remaining bits of \(S\), in increasing vertex order, are compressed into a zero-based cut code. Thus the code range is \(0,\ldots,2^{|S|-1}-1\).

The empty subset has one empty coloring, one cut code 0 and cost zero. The total number of retained canonical cuts over every subset of an \(N\)-vertex graph is
\[
1+\sum_{s=1}^N\binom Ns2^{s-1}
=\frac{3^N+1}{2}.                                    \tag{3}
\]
For \(N=11\), this is 88,574: 88,573 from nonempty subsets and one empty cut. This is exact coverage of the labelled cut family, not a sample or a symmetry heuristic.

A “vertex bipartition” here means two classes modulo a common color reversal. Some graph terminology instead calls the crossing edge set itself a cut. The next section explains why their counts can differ.

## 4. Distinct minimum deletion sets and component flips

Let \(H=G[S]\), and let \(K\) be the graph of crossing edges of an optimal coloring. Then \(K\) has the same connected-component partition as \(H\).

Indeed, suppose a connected component \(W\) of \(K\) is only a proper part of an original component of \(H\). Some original edge leaves \(W\). Every edge leaving \(W\) is noncrossing, because a crossing edge would connect \(W\) to another vertex in \(K\). Flip the colors on all vertices of \(W\). Internal crossing status is unchanged, and every original edge leaving \(W\) becomes crossing. At least one edge is gained and none is lost, contradicting optimality.

Fix a minimum deletion set \(D\). By (1), \(H-D\) is the crossing graph of every proper two-coloring of it, and the preceding argument gives exactly \(c(H)\) connected components, where isolated vertices count as components. Each nonempty connected bipartite component has exactly two ordered colorings. Thus \(D\) has exactly
\[
2^{c(H)}
\]
ordered colorings. If \(S\ne\varnothing\), common reversal acts freely, giving
\[
\boxed{2^{c(H)-1}}
\]
canonical vertex bipartitions for each distinct minimum deletion set.

Fixing the least vertex of **each original component** in \(A\) selects exactly one representative per minimum deletion set. This is the `deletion_sets` family. Isolated vertices are fixed in \(A\); empty color classes remain allowed. For \(S=\varnothing\), there is one empty coloring and one empty deletion set, handled separately without a negative exponent.

The constructor retains all optimal canonical cut codes and all component-normalized deletion representatives. Neither family is a quotient by graph automorphisms. The deletion representatives are sorted by their normalized \(A\)-mask, not by lexicographic order of the deleted edge lists.

## 5. Complete actual profile

The following table is the exact distribution of minimum deletion numbers among every vertex subset of the single host. A dash denotes zero.

| Size \(s\) | Subsets | \(\delta=0\) | \(\delta=1\) | \(\delta=2\) | \(\delta=3\) | \(\delta=4\) | \(F_G(s)\) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 1 | 1 | — | — | — | — | 0 |
| 1 | 11 | 11 | — | — | — | — | 0 |
| 2 | 55 | 55 | — | — | — | — | 0 |
| 3 | 165 | 165 | — | — | — | — | 0 |
| 4 | 330 | 330 | — | — | — | — | 0 |
| 5 | 462 | 431 | 31 | — | — | — | 1 |
| 6 | 462 | 326 | 136 | — | — | — | 1 |
| 7 | 330 | 120 | 210 | — | — | — | 1 |
| 8 | 165 | 15 | 105 | 45 | — | — | 2 |
| 9 | 55 | — | 10 | 45 | — | — | 2 |
| 10 | 11 | — | — | — | 11 | — | 3 |
| 11 | 1 | — | — | — | — | 1 | 4 |

Across all subsets, the saved transcript contains **5,004 optimal canonical vertex-bipartition codes** and **3,589 distinct minimum-deletion representatives**, the latter counted separately for each vertex subset.

The full graph is connected, so its five optimal canonical vertex bipartitions correspond one-to-one to minimum deletion sets:

| Rank | Cut code | \(A\)-mask | Deleted edge IDs | Deleted edges |
| ---: | ---: | ---: | --- | --- |
| 0 | 244 | 489 | 2, 4, 11, 19 | \(\{0,6\},\{1,2\},\{3,7\},\{9,10\}\) |
| 1 | 466 | 933 | 3, 9, 10, 16 | \(\{0,9\},\{2,8\},\{3,4\},\{6,10\}\) |
| 2 | 534 | 1069 | 6, 7, 14, 15 | \(\{1,7\},\{2,3\},\{4,8\},\{5,10\}\) |
| 3 | 586 | 1173 | 1, 5, 12, 17 | \(\{0,4\},\{1,5\},\{3,9\},\{7,10\}\) |
| 4 | 645 | 1291 | 0, 8, 13, 18 | \(\{0,1\},\{2,6\},\{4,5\},\{8,10\}\) |

Each leaves 16 crossing edges. The complete histogram for the full graph's 1,024 canonical vertex bipartitions, indexed by deletion cost \(0,\ldots,20\), is:
```json
[0,0,0,0,5,26,45,55,105,165,186,190,140,60,25,11,5,5,0,0,1]
```
Every underlying cut cost, not only this histogram, is retained in the data.

### The square-root budget in this fixed host

For integer deletion counts, a bound by \(\sqrt s\) is equivalent to a bound by \(\lfloor\sqrt s\rfloor\). The retained public budget query uses
```json
[0,1,1,1,2,2,2,2,2,3,3,3]
```
for sizes 0 through 11. Exactly one vertex subset violates it: the full eleven-vertex set, requiring four deletions where the budget is three. Every proper vertex subset, and hence every subgraph on a proper vertex subset, meets the bound.

This makes the host an obstruction minimal under vertex deletion within this fixed graph. It also gives a necessary exclusion for the separate infinite question: any graph whose every finite subgraph satisfies the square-root deletion bound cannot contain this eleven-vertex graph as a subgraph. This implication does not construct or rule out an infinite-chromatic graph satisfying that condition, and asserts no smallest obstruction over all graphs.

## 6. Saved-reader consumer

The actual graph constructor and profile constructor were each called once, followed by one fresh-context opening of the saved transcript and 24 public queries. The source was unchanged between them.

Some useful retained queries are:

- Full-graph minimum-deletion pages return all five witnesses above.
- Mask **1055**, the base five-cycle plus isolated apex, has minimum one deletion, ten optimal canonical vertex bipartitions and five distinct deletion sets. The five deletion witnesses are all retained.
- Mask **992**, the five twins without the apex, consists of five isolated vertices. It has sixteen optimal canonical vertex bipartitions and one deletion set, the empty set. Its component-normalized representative places all vertices in \(A\).
- There are **45** eight-vertex subsets with minimum deletion number at least two. Rank 22 has mask **1662**, vertices \(\{1,2,3,4,5,6,9,10\}\), ten edges and nine distinct two-edge minimum deletion sets. The query returns all nine.
- Requiring the apex, excluding all five base vertices and requiring deletion number zero yields **32** vertex subsets. Rank 31 is the five-twin star, mask **2016**.
- Full-graph cut code 0, with \(A=\{0\}\), has cost sixteen and is absent from the optimal family. The rank interface reports this absence explicitly.

Opening checks the complete saved transcript; it does not recreate its graph-dependent objective table. Requested cut pages materialize their edge witnesses from the saved graph and check the selected cost. Those inspections are accounted for as reader work.

| Operation or retained object | Actual count |
| --- | ---: |
| Induced subsets | 2,048 |
| Canonical cut objectives, including empty | 88,574 |
| Nonempty subset edge-count recurrence states | 2,047 |
| Component searches | 2,047 |
| Component vertex expansions | 11,264 |
| Optimal cut codes retained | 5,004 |
| Minimum deletion representatives retained | 3,589 |
| Stored cost cells checked by reader | 88,574 |
| Stored optimal codes checked by reader | 5,004 |
| Stored component records checked by reader | 2,967 |
| Saved public queries | 24 |
| Subset filters compiled / cache hits | 2 / 4 |
| Filter rows inspected | 4,096 |
| Selected cut records returned | 22 |
| Edge inspections for selected witnesses | 440 |
| Selected witness cost checks | 22 |
| New reader full cut objectives / subset edge counts / component searches | 0 / 0 / 0 |

The single observed elapsed times were 18 ms for graph plus profile construction, 24 ms for reader opening and 11 ms for the query sequence. They are observations of this execution, not a statistical benchmark or a promise for larger inputs. Work counters record the named operations; they are not a count of every runtime instruction. Reader canonical graph normalization also examines the small input edge list.

## 7. Public API

The pure CommonJS module exports:
```js
const {
  mycielskiGraph,
  compileLocalBipartization,
  openRetainedLocalBipartization,
  LOCAL_BIPARTIZATION_LIMITS
} = require("./local_bipartization_index.cjs");
```

### Constructors

`compileLocalBipartization(graph)` accepts:
```js
{
  vertex_count: N,
  edges: [[u, v], ...]
}
```
Vertices and edge endpoints must be safe integer Numbers. The generic cap is \(0\le N\le14\). At most 4,096 input pairs are allowed; repeated or reversed pairs are deduplicated, loops rejected, and normalized edges sorted lexicographically. Edge IDs are their zero-based positions in that normalized list. There are no edge weights or directed arcs.

`mycielskiGraph(base)` uses the same input convention with at most six base vertices, so its result has at most thirteen vertices. It returns the graph and an explicit construction/label record. It constructs the graph; it does not calculate chromatic or clique numbers. The profile constructor uses the graph's vertex and edge fields. The actual construction record is preserved in the delivery wrapper.

`openRetainedLocalBipartization(snapshot)` checks and opens the complete saved index. For already obtained module and JSON texts in a connected V8 runtime:
```js
const module = { exports: {} };
new Function("module", "exports", moduleText)(module, module.exports);
const delivery = JSON.parse(dataText);
const index =
  module.exports.openRetainedLocalBipartization(delivery.snapshot);

index.profile();
index.budgetReport([0,1,1,1,2,2,2,2,2,3,3,3]);
index.pageCuts(2047, 0, 8, "deletion_sets");
index.subsetCount({ size: 8, minimum_at_least: 2 });
```
These examples use the saved consumer data; opening does not call either constructor.

### Query methods

| Method | Result |
| --- | --- |
| `summary()` | Host size, complete coverage, full-graph minimum and family counts. |
| `graph()` | A copy of the normalized graph, including adjacency masks. |
| `profile()` | All size rows, complete minimum distributions and every maximizing subset mask. |
| `subset(mask)` | Vertices, edges, component masks, minimum, maximum crossing count and family multiplicities. |
| `subsetCount(query = {})` | Number of subsets matching the recognized filters. |
| `selectSubset(query, rank)` | Subset at zero-based rank among matches. |
| `rankSubset(query, mask)` | Membership, rank when present, and insertion rank. |
| `pageSubsets(query = {}, start = 0, count = 64)` | A page of matching subsets in increasing numeric-mask order. |
| `cutHistogram(mask)` | Complete distribution of costs among canonical vertex bipartitions. |
| `cutCount(mask, kind = "optimal")` | Size of the selected cut/deletion family. |
| `selectCut(mask, rank, kind = "optimal")` | A full partition and deleted/kept-edge witness. |
| `rankCut(mask, A, kind = "optimal")` | Canonicalizes \(A\), then reports family membership and rank/insertion rank. |
| `pageCuts(mask, start = 0, count = 64, kind = "optimal")` | Ranked cut witnesses with a terminal or next offset. |
| `budgetReport(bounds)` | Every violating size, its worst excess, count of violating subsets and first maximizing mask. |
| `snapshot()` | A complete copied snapshot. |
| `work()` | A copied work record for this index instance. |

Subset query fields are:

| Field | Meaning |
| --- | --- |
| `size` | Exact cardinality \(0,\ldots,N\); omitted or `null` means any size. |
| `minimum_at_least` | Inclusive lower bound on the minimum deletion number; default 0. |
| `minimum_at_most` | Inclusive upper bound; default host edge count. |
| `contains` | Vertex mask that must be contained in the subset; default 0. |
| `excludes` | Vertex mask disjoint from the subset; default 0. |

Minimum-deletion filter bounds must lie from zero through the host edge count; reversed bounds and conflicting contains/excludes masks are rejected. Normalized queries can be reused, including their `size: null` form.

The three cut kinds are:

| Kind | Family and normalization |
| --- | --- |
| `"all"` | Every vertex bipartition modulo a common reversal; least selected vertex in \(A\). |
| `"optimal"` | The minimum-cost members of that canonical family. |
| `"deletion_sets"` | One minimum-cost representative with the least vertex of every original component in \(A\). |

For rank queries, \(A\) must be a subset of the selected vertices. The first two kinds complement the entire selected vertex set when necessary to put its least vertex in \(A\). The deletion-set kind flips original connected components independently. Those flips preserve the edge-deletion set. The method returns the original and normalized masks, the canonical cut code and saved cost, and `found: false, rank: null` when it is outside the requested family. Insertion rank is always supplied.

Masks, ranks and page starts accept safe nonnegative Number integers, nonnegative BigInts, or canonical nonnegative decimal strings of at most sixteen digits, then enforce the relevant finite bound. Page counts are safe integer Numbers from 1 through 256. A page may start at the end of a family and returns an empty terminal page; selection requires a rank below the family size. Subset filters can have no matches.

`budgetReport` accepts an array of \(N+1\) nonnegative safe integer Numbers, one for each size 0 through \(N\). It concerns the fixed finite host only. Bounds need not be monotone, and may exceed the host edge count. Up to sixteen normalized subset filters are cached; adding a new distinct filter beyond that limit evicts the oldest entry.

All returned graphs, records, arrays and snapshots are copies. The interface does not mutate the supplied graph or snapshot.

## 8. Complete transcript, validation and resource bounds

The delivery wrapper schema is `commons.erdos74.mycielski_c5_local_profile_delivery.v1`. The snapshot schema is `commons.local_bipartization_cut_index.v1`. For every numeric subset mask, the complete snapshot contains:

- its induced edge count;
- every connected-component mask and their anchor mask;
- the complete hexadecimal cut-cost row;
- the cost histogram, minimum and all optimal cut codes;
- every component-normalized minimum-deletion code.

It also contains the graph, ordering rules, coverage totals, complete size profiles, parameter-source locator and constructor counters. The wrapper retains the base cycle, Mycielski construction record, formal-source identity/status boundary, constructor observation, all 24 reader requests and responses, and separate work records.

Each cost is two lowercase hexadecimal digits. The complete row for \(S\) has length \(2\cdot2^{|S|-1}\) when \(S\ne\varnothing\), and length two when \(S=\varnothing\). The code order is the order described in Section 3. A byte is sufficient because the vertex cap gives at most \(\binom{14}{2}=91\) edges.

All masks use at most fourteen bits, all exact combinatorial counts in one construction are bounded by \((3^{14}+1)/2=2,391,485\), and edge counts are at most 91. Ordinary integer Number arithmetic and bit operations are exact within these bounds. BigInt is used only to parse and check optional integer-form inputs before conversion. The source uses no native process, external package or random sampling.

The induced edge recurrence and bit-mask component searches require bounded work proportional to \(N2^N\). The cut evaluation count is exactly (3). The transcript intentionally stores every cut cost; it does not claim to evade exponential worst-case output. The public cap is a resource contract, not a mathematical limitation of the local deletion parameter.

### Reader assurance

Opening validates canonical graph normalization, all complete array lengths, cost widths/ranges, coverage metadata, and the disjoint ordered partition of each subset into the stored component masks. It checks each stored cost against the saved minimum and edge-count range; verifies that the optimal list includes exactly every minimum-cost code; rebuilds the stored cost histogram; checks the component-normalized representatives and multiplicities; and checks the profile aggregation from the saved minima.

It does **not** recompute the induced edge counts from the graph, search the stored components for connectivity, or recalculate all 88,574 cut objectives. Thus opening authenticates internal relationships in the complete saved transcript, not arbitrary mathematical provenance. Interpretation as the graph's true profile relies on the identified constructor, (1)–(3), and its actual saved output.

For each requested full cut witness, the reader additionally scans the retained graph's edges, materializes the deleted and kept edge IDs, and checks the selected deletion count against its stored value. This gives direct graph evidence for those returned cuts. It does not independently establish the optimality of every unqueried cost row or the completeness of a fabricated graph transcript.

The actual run exercises empty, edgeless, isolated, connected and disconnected induced subsets inside this one host. Separate alternate whole-graph inputs and sizes, duplicate normalization, malformed/rejection branches, cache eviction, additional queries and empty-at-end pages were source-inspected rather than executed as extra consumers.

## 9. Identities and release scope

The exact executed module `local_bipartization_index.cjs` has 22,226 UTF-8 bytes and Git blob **a94c4465e7ae7ef0548c2f627edcb46e8f4f4723**. It was unchanged between constructor and reader.

The complete `mycielski_c5_local_profile.json` has 776,379 UTF-8 bytes and Git blob **937421e391af3907b184a8ca1bbfbb60da910788**. All actual cut costs, minima, component partitions, profile entries and query responses are retained; none is replaced by a summary-only record.

The new result is the full finite profile and usable saved index for the identified classical graph. Construction and chromatic attribution remain with the cited sources. The current formal source's negative arbitrary-growth annotation and separate square-root variant remain distinct from this finite calculation.

Original narrow claim: `C0C3MEWHTR6 / 1789714992.581159 / 1791151449.283649`.
