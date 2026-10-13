# Complete finite K4-free triple families

This package indexes every labelled simple 3-uniform hypergraph on six vertices that contains no complete four-vertex 3-graph. Its exact family has 477,965 members. The largest have 14 edges, and there are 30 of them. All 30 maximum members are exported in the saved-reader output.

The construction is a decision diagram and cardinality index, with conditional completion counts and rank/select. It does not scan the 2^20 candidate edge sets. This is a finite classification and navigation artifact, not a new general Turán theorem or asymptotic density result.

## Definitions and source boundary

Vertices have fixed labels 0,...,n-1. An edge is an unordered set of three distinct vertices; a hypergraph is a set of such edges. There are no repeated edges or repeated vertices within an edge. A forbidden K4^3 means that all four possible triples on one four-vertex set are present. This is an ordinary subhypergraph condition, with no induced-subgraph qualification.

The directly read PPL074 card identifies Erdős 500 as the question of determining the maximum edge count ex_3(n,K4^3):
https://prizeproblems.org/problems/074/ .
The attempted FormalConjectures/ErdosProblems/500.lean route returned 404. The directly linked OEIS A140462 route returned ServerError. Both remain held, and neither supplies a newly read formal theorem or small-n table here. The catalogue's status label is not treated as an independently verified current mathematical frontier.

The prior source qualification for the released cyclic construction #31432 read Andrew Frohmader, *More Constructions for Turán's (3,4)-Conjecture*, Electronic Journal of Combinatorics 15 (2008), R137, printed pages 1–2:
https://www.combinatorics.org/ojs/index.php/eljc/article/download/v15i1r137/pdf/ .
That account credits Turán's balanced cyclic three-part construction. With a declared cyclic orientation, its edges are ABC, AAB, BBC and CCA. Repeated part letters mean different vertices in that part, not repeated vertices.

The same retained source handoff read Oleg Pikhurko, *Constructions of Turán systems that are tight up to a multiplicative constant*, Advances in Mathematics 464 (2025), 110148:
https://pikhurko.github.io/E/Pikhurko25am.pdf .
Its covering convention uses T(n,4,3) for the minimum triple family meeting every four-set, with ex(n,K4^3)=binomial(n,3)-T(n,4,3). The paper's description of the general (4,3) case as open is dated to that publication; no later-status survey or proof audit is asserted here.

The established cyclic construction and its classical 5/9 asymptotic lower density retain their attribution. The previous package represented one large explicit construction on 2,197 vertices. This package instead indexes the full finite family on six labelled vertices; it imports no old graph, coefficient or counting output. The value 14 and the classical construction are not claimed as newly discovered mathematics.

## Actual input and edge order

The complete declared input has n=6. Its text identity is 5e762c39340bc0473a437903c9db92bf54fc4450 (348 bytes). It supplies no hypothesized optimum.

All triples are ordered lexicographically as increasing vertex arrays. The 20 positions are:

| Index | Triple | Index | Triple |
|---:|---|---:|---|
| 0 | 0,1,2 | 10 | 1,2,3 |
| 1 | 0,1,3 | 11 | 1,2,4 |
| 2 | 0,1,4 | 12 | 1,2,5 |
| 3 | 0,1,5 | 13 | 1,3,4 |
| 4 | 0,2,3 | 14 | 1,3,5 |
| 5 | 0,2,4 | 15 | 1,4,5 |
| 6 | 0,2,5 | 16 | 2,3,4 |
| 7 | 0,3,4 | 17 | 2,3,5 |
| 8 | 0,3,5 | 18 | 2,4,5 |
| 9 | 0,4,5 | 19 | 3,4,5 |

Bit i of an edge-set mask selects triple i. Each of the 15 four-sets supplies a forbidden four-edge mask. For example, the first four-set {0,1,2,3} forbids simultaneous selection of edge indices {0,1,4,10}.

The constructor accepts 3<=n<=6. Its actual consumer is only n=6. Larger parameter values are rejected; the smaller unexercised branches were source-inspected. Bit masks fit within 20 bits and counts use arbitrary-precision integers.

## Residual constraints and exact family construction

At edge position k, a residual forbidden mask lists undecided edges which cannot all be selected together. Already selected edges have been removed from that mask. A forbidden mask disappears entirely once an edge in it is excluded, because that particular clique can no longer be completed.

For bit b=1<<k:

- Excluding edge k drops every residual mask containing b.
- Including edge k removes b from every residual mask.
- If an included branch creates the empty forbidden mask, it is infeasible.
- After the final position, a branch without an empty forbidden mask is feasible.

Duplicate masks are merged. If one forbidden mask is contained in another, the larger is redundant: avoiding the smaller automatically avoids the larger. Removing such supersets changes no family. The memo key contains k and the normalized residual masks, so identical remaining problems share the same result.

The two terminals are 0 for the empty family and 1 for the family containing only the empty remaining edge set. A decision node has a variable, a low child excluding it, and a high child including it. If the high child is zero, the node is suppressed: the variable is forced absent. Thus skipped variables mean absence; they are not free choices. Identical (variable,low,high) nodes are shared.

This gives an induction proof of the represented family. The two branches are disjoint by the current edge, each has exactly the corresponding residual constraints, and their union is every feasible continuation. The complete retained residual-state rows record both branch results, including zero-suppressed states.

Every node carries the exact cardinality polynomial
\[
P_v(z)=P_{\mathrm{low}}(z)+zP_{\mathrm{high}}(z),
\qquad P_0=0,\quad P_1=1.
\]
Its z^j coefficient counts members with j selected edges remaining at that node. Child indices are smaller than their parent's, so the retained diagram has an explicit bottom-up order. All coefficients and totals are saved as canonical decimal strings. No probabilistic sampling, graph-isomorphism quotient or second candidate census is involved.

The actual construction has 1,372 residual states, 1,063 nonterminal decision nodes and two terminals, using 7,599 coefficient cells. It records 20,299 residual-subset tests, 309 zero-terminal hits, three one-terminal hits and 309 zero suppressions.

## Complete cardinality profile

| Edges | Number of labelled hypergraphs |
|---:|---:|
| 0 | 1 |
| 1 | 20 |
| 2 | 190 |
| 3 | 1,140 |
| 4 | 4,830 |
| 5 | 15,264 |
| 6 | 36,960 |
| 7 | 69,180 |
| 8 | 99,495 |
| 9 | 107,600 |
| 10 | 83,930 |
| 11 | 43,920 |
| 12 | 13,545 |
| 13 | 1,860 |
| 14 | 30 |

All higher coefficients are zero. The total is 477,965. This exact finite coverage establishes the maximum within the complete six-vertex labelled family, rather than merely a lower-bound construction.

## Relationship to the classical balanced construction

The balanced cyclic construction with three parts of size two has eight ABC edges and two edges of each of AAB, BBC and CCA, for a total of 14. It is K4-free: a four-set has part sizes (2,2,0) or (2,1,1). In the first case only one orientation of the repeated-part triples is allowed, giving two edges; in the second, the two ABC triples and only one repeated-part triple are present, giving three. Neither contains all four.

There are 15 partitions of the six labelled vertices into three unordered pairs and two cyclic orientations for each partition. These give 30 distinct constructions. To see distinctness without another computation, a vertex pair within one part has codegree two, whereas a pair from different parts has codegree three. The three codegree-two pairs therefore recover the part partition. With that partition fixed, reversing cyclic orientation changes which repeated-part triples are edges.

Consequently these 30 established constructions attain the computed upper count, so they exhaust this finite maximum family. This is a deduction from the complete saved count and the elementary construction argument; no additional construction enumeration was run. It does not prove the corresponding conjecture for arbitrary n or identify a new hypergraph construction.

## Navigation and ordering

A rank is zero-based. The decision order considers edges in increasing index order and places the absent branch before the present branch. This is lexicographic order on the 20-bit membership word read from edge 0 to edge 19. It is **not** increasing integer-mask order.

The count for the low branch comes from its saved polynomial. With a fixed cardinality j, taking the high branch reduces the remaining cardinality by one. Without a cardinality restriction, the count is the sum of all saved coefficients. Selection subtracts complete low branches; ranking adds them whenever a present branch is taken. Both return their complete decision traces.

Suppressed variables remain absent. Ranking refuses a mask containing a skipped variable, an infeasible high branch, or a mismatched requested cardinality. No four-set test is rerun during membership/rank queries; they follow the saved diagram.

All 30 maximum members are exported in the actual reader result, each with its edge list and branch trace. The first and last masks in the stated order are 818684 and 521015, respectively. Their numerical order illustrates why mask order must not be substituted for the documented decision order.

## Conditional completions

A condition supplies disjoint arrays of required and forbidden edge indices. Required and forbidden instances of the same edge are rejected as inconsistent input.

Conditional counting traverses the saved diagram. A required skipped variable makes a state infeasible. A required current variable suppresses the low branch; a forbidden variable suppresses the high branch. Otherwise both branches remain. The same polynomial recurrence counts total edges, including required ones. The memo key is the saved node plus the remaining required mask; the forbidden mask is fixed for that query family.

These conditional coefficients are new query work and are retained explicitly. The original diagram, four-set constraints and base coefficients are never rebuilt. A returned family object supports summary, rank, select and page with the same ordering. Its snapshot contains every new conditional cell.

Four actual conditions are retained:

| Condition | Family size | Maximum edges | Maximum members | New cells |
|---|---:|---:|---:|---:|
| Exclude edge 0 | 273,995 | 14 | 9 | 705 |
| Require edges 0,1,4,10, a complete four-set | 0 | none | 0 | 111 |
| Require 0,1,2 and exclude 3,4,5 | 9,158 | 14 | 1 | 84 |
| Require every edge of the first maximum member | 1 | 14 | 1 | 56 |

An infeasible family has maximum_edges:null, not a claimed maximum of zero. The family containing the empty hypergraph does have maximum zero. These are distinct cases.

## API

~~~javascript
const { openIndex } = require('./k4_free_families.cjs');
const data = require('./six_vertex_family_certificate.json');
const reader = openIndex(data.record);

reader.summary();
reader.page(14, '0', 256); // all 30 maximum members
const family = reader.condition({present:[0,1,2], absent:[3,4,5]});
family.summary();
family.select(14, '0');
~~~

| Method | Contract |
|---|---|
| buildIndex({n}) | Construct the full finite family for 3<=n<=6. |
| openIndex(record) | Structurally load a matching trusted saved diagram. |
| summary() | Complete base profile, optimum count and construction work. |
| edges(), constraints() | Copies of the declared edge order and forbidden four-set rows. |
| select(cardinality,rank) | Select one member; null cardinality means all sizes. |
| rank(mask,cardinality?) | Return rank and trace, or null for a nonmember/mismatched size. |
| page(cardinality,offset,limit) | At most 256 selected members with traces. |
| membership(mask) | Saved-diagram membership and unrestricted rank. |
| decode(mask) | Convert a bounded mask to edge indices and triples, without membership assertion. |
| condition({present,absent}) | Build a conditional coefficient family on the saved diagram. |
| work(), snapshot() | Copies of reader counters or the saved construction. |

Conditional family methods are summary(), select(), rank(), page() and snapshot(). Decimal ranks and offsets are canonical nonnegative strings of at most 128 digits. Edge indices are safe integers in the declared range. Duplicate condition indices are rejected. Offsets may equal a family's count, producing an empty page; select requires a strictly smaller rank.

Construction caps are 100,000 residual states, 100,000 total diagram nodes and 1,500,000 coefficient cells. A conditional family has a 100,000-cell cap. Exceeding a cap raises an error; no partial answer is labelled complete.

Structural loading checks bounds, node order, nonzero high children and integer coefficients. It does not authenticate an arbitrary external record, reprove its constraint generation, or recompute its polynomial equalities. Use the matching trusted certificate. All returned arrays and snapshots are copies. No additional parameter sweep or standalone test suite was run.

## Actual retained evidence

Executed source: a52f65c8b6e5223a1b6a7af9fac895b8c5526966, 9,231 bytes.
Complete construction: bb3748e67572ff2a2b89b2fe09f3ad015c5d0886, 570,644 bytes.
Complete 22-query reader: 096d4f5605d89353858af7eda5e2f7074a731f1c, 540,713 bytes.

The reader exports all 30 maximum hypergraphs and all 20 single-edge hypergraphs. It also retains selected/ranked examples, membership of the complete and empty graphs, and all four conditional tables. These selected-output materializations are explicit; the work counter hypergraphs_enumerated refers to an exhaustive candidate-family census, not to these returned query records.

Fresh-reader work: 1,065 saved nodes and 7,599 coefficient cells indexed, 1,161 node visits, 956 new conditional cells, 5,447 conditional coefficient cells and 957 memo hits. Base-recurrence updates, constraint generation and exhaustive hypergraph-census passes are zero.

These exact results concern the full six-vertex family and the stated conditions. They supply no asymptotic Turán density, current general status, sponsor submission or mathematical novelty claim. The old cyclic construction and unrelated accepted calculations were not replayed.

Publication uses guarded serial Contents operations, exact text, preimages, lineage and expected-head checks. It does not independently establish Git modes or the whole repository tree.
