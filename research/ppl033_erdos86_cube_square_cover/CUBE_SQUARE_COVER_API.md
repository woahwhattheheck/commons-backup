# Exact square-cover search in a finite hypercube

## Result and deliverable

The recorded new consumer finds and certifies a `C4`-free subgraph of `Q4` with **24 of its 32 edges**. Eight deleted edges hit all 24 coordinate squares. Each edge belongs to three squares, so every deletion cover needs at least eight edges. The retained witness attains that lower bound.

This is an exact finite statement:

$$
\operatorname{ex}(Q_4,C_4)=24.
$$

The contribution is a reusable bounded constructor, resumable exact optimizer, and saved graph/certificate reader. The finite value is an illustration of those capabilities, with a transparent certificate. It is not a mathematical-priority claim.

| File | Role |
|---|---|
| [cube_square_cover.cjs](cube_square_cover.cjs) | Dependency-free ECMAScript implementation |
| [q4_square_cover.json](q4_square_cover.json) | Complete new construction, paused frontier, continuation and fresh-reader evidence |
| [README.md](README.md) | Entry point and scope |

The source used in every actual invocation is Git blob `617edf7561bf6cc982aaf48b2e895eee4d50976c`, 51,024 UTF-8 bytes. It was fixed before the first construction and has not changed after execution.

### Source contract

[Formal Conjectures, Erdős problem 86](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/86.lean), observed blob `9893cdbc1cc5534dd0c912c63693c98642d0a249`, quantifies over arbitrary simple edge subgraphs on the entire Boolean cube vertex set. It asks whether, for every fixed positive $\varepsilon$, all sufficiently large dimensions force a four-cycle above density $1/2+\varepsilon$. The observed file labels the problem open and its theorem has `sorry`. It was read as a source contract; no Lean proof or environment was run.

[Rahil Baber, *Turán densities of hypercubes*, arXiv:1201.3587v2](https://arxiv.org/pdf/1201.3587), Introduction, supplies the binary-coordinate and layer conventions and describes the classical construction that deletes edges between layers $2r-1$ and $2r$. For dimensions at least two that construction keeps half the cube's edges. Its role here is the initial feasible witness. The paper discusses stronger asymptotic upper bounds as well; none is implemented or recertified by this module.

The finite search below operates on edge subsets. It is not an induced-vertex-subgraph problem, a closed-walk problem allowing repeated vertices, or a catalog up to isomorphism. The cube's full vertex set is fixed throughout.

## The new recorded computation

The constructor was invoked once at **2026-10-04T20:46:43.511Z** with:

~~~javascript
{
  source_id: "ERDOS86-CUBE-SQUARE-COVER-20261004-7CA6/Q4",
  dimension: 4
}
~~~

It produced the complete 16-vertex, 32-edge, 24-square incidence universe. The initial alternating-layer witness keeps 16 edges.

One requested search node was then processed. Before that node, the deterministic greedy seed built a 12-edge deletion cover, improving the kept count to 20. The first node generated four children. The saved frontier, in stack order, is `[4, 3, 2, 1]`; this first stage is explicitly incomplete.

At **2026-10-04T20:47:14.828Z**, a new engine opened that snapshot and requested at most 256 additional nodes. It processed 155 new nodes and stopped as soon as the eight-edge deletion witness attained the root-wide lower bound. The original constructor, greedy trace, first advance, processed root, and initial incumbents were preserved.

| Incumbent | Origin | Deleted | Kept |
|---:|---|---:|---:|
| 0 | Classical alternating layers | 16 | 16 |
| 1 | Greedy cover, 12 steps | 12 | 20 |
| 2 | Search node 40 | 11 | 21 |
| 3 | Search node 51 | 10 | 22 |
| 4 | Search node 140 | 9 | 23 |
| 5 | Search node 170 | 8 | 24 |

The final witness deletes:

| Edge ID | Coordinate | Lower endpoint | Upper endpoint | Squares hit |
|---:|---:|---:|---:|---|
| 0 | 0 | 0 | 1 | 0, 4, 8 |
| 7 | 0 | 14 | 15 | 3, 7, 11 |
| 10 | 1 | 4 | 6 | 1, 12, 18 |
| 13 | 1 | 9 | 11 | 2, 15, 17 |
| 19 | 2 | 3 | 7 | 5, 13, 23 |
| 20 | 2 | 8 | 12 | 6, 14, 20 |
| 26 | 3 | 2 | 10 | 9, 16, 22 |
| 29 | 3 | 5 | 13 | 10, 19, 21 |

The deleted-edge mask is `0x24182481`. The winning node is 170, depth eight, with covered-square mask `0xffffff`. Its two forbidden edges, `[3, 12]`, describe that node's branch region; they are not additional deletions.

The 24 kept edge IDs are:

~~~text
[1, 2, 3, 4, 5, 6, 8, 9, 11, 12, 14, 15,
 16, 17, 18, 21, 22, 23, 24, 25, 27, 28, 30, 31]
~~~

All 174 generated node records are retained. Of these, 156 were processed: 52 branched, 97 were pruned by a bound, and seven were complete-cover leaves. The other 18 were still pending when the feasible eight-edge cover met the global lower bound. They are explicitly marked `global_bound_closed` and listed in the completion record. They were not expanded and are not counted as processed nodes.

That distinction matters: this run finished by **attaining a valid global bound**, not by individually exhausting every queued branch. No claim is made that all equal-size optima were enumerated.

## Exact mathematical reduction

### Cube vertices, edges and squares

For dimension $d$, the vertex set is the integers from zero through $2^d-1$, interpreted as binary strings. Coordinate zero is the least significant bit.

Two distinct vertices are adjacent exactly when their binary strings differ in one coordinate. Each undirected edge has one representation $(i,b)$, where bit $i$ of the lower endpoint $b$ is zero; its other endpoint is $b+2^i$. There are

$$
V_d=2^d,\qquad E_d=d\,2^{d-1}
$$

vertices and edges.

For $i<j$ and a base $b$ whose bits $i,j$ are zero, the coordinate square is the cycle

$$
b,\quad b+2^i,\quad b+2^i+2^j,\quad b+2^j.
$$

There are

$$
F_d=\binom d2 2^{d-2}
$$

such squares for $d\ge2$. For $d=1$, the square count is zero; no negative-exponent formula is used in the implementation.

Every simple four-cycle is one of these squares. Along a closed walk in a cube, every coordinate flips an even number of times. A simple four-cycle cannot flip only one coordinate: that would revisit a vertex after two steps. It therefore flips exactly two coordinates twice each. Consecutive equal flips would again repeat a vertex, so the flips alternate. The two coordinates and the base with both corresponding bits zero determine one square uniquely.

The reverse implication is immediate from the displayed four vertices: each coordinate square is a simple four-cycle. Consequently, every four-cycle is represented exactly once in the saved square universe.

### Deletion cover equivalence

Let $D$ be a set of deleted edges, and keep every edge outside $D$. The kept graph is $C_4$-free if and only if every coordinate square contains an edge of $D$.

Thus the exact optimization is a finite set-cover problem:

$$
\tau_d=\min\{|D|:\text{every coordinate square meets }D\},
\qquad
\operatorname{ex}(Q_d,C_4)=E_d-\tau_d.
$$

The solver makes no structural restriction on $D$. All ordinary edge subsets of the fixed cube are represented by the search formulation.

### Global incidence-capacity bound

An edge in coordinate $i$ belongs to one square for each other coordinate $j$. The fixed values of the remaining coordinates and the endpoints determine that square. Therefore every edge belongs to exactly $d-1$ squares.

If $D$ hits all squares, counting its edge-square incidences gives

$$
F_d \le (d-1)|D|,
\qquad
|D| \ge
\left\lceil\frac{F_d}{d-1}\right\rceil
\quad(d\ge2).
$$

Overlaps between deleted edges can only reduce the number of distinct squares covered, so they do not invalidate this bound.

For $Q_4$, the bound is $\lceil24/3\rceil=8$. The retained eight-edge deletion cover therefore proves optimality among all edge subsets. For $d=1$, the module uses the separate bound zero and keeps its single edge.

The topology records every edge's square IDs and its incidence count. The final completion record retains the bound, the attaining incumbent, the product $8\cdot3=24$, and every pending node closed by that equality.

### Classical alternating-layer baseline

Layer $k$ consists of vertices of Hamming weight $k$. An edge between layers $k$ and $k+1$ has a lower endpoint of weight $k$. The baseline deletes precisely the edges with odd lower-endpoint weight.

A square starting in layer $k$ has two edges with lower weight $k$, and two with lower weight $k+1$. Exactly one of those two lower weights is odd, so the baseline deletes two of the square's four edges.

For $d\ge2$, the number of edges with lower weight $k$ is

$$
(d-k)\binom dk=d\binom{d-1}{k}.
$$

The sums of the even and odd binomial coefficients of degree $d-1$ are both $2^{d-2}$. The baseline thus deletes and keeps $d2^{d-2}$ edges each. This count is not extended to $d=1$: that cube has no square and the baseline keeps its one edge.

The baseline is a guaranteed feasible cover. It is not an optimality assumption.

## Search state and correctness

A node retains:

- $D$, edges already selected for deletion;
- $F$, edges forbidden from being deleted in that branch;
- the union of the square-incidence masks of $D$;
- its parent, fixed branch transition, children and disposition.

The invariant $D\cap F=\varnothing$ is preserved. Masks for edge and square populations use `BigInt`; ordinary 32-bit JavaScript bitwise integers are not used for those populations.

### Greedy starting cover

The greedy seed starts with no deleted edges. At each step it computes the number of currently uncovered squares hit by every still-unselected edge, chooses a maximum-gain edge, and breaks ties by the smaller edge ID.

Every gain array and chosen edge is retained. The greedy cover improves the initial incumbent when it uses fewer deletions. The seed is heuristic; exactness comes from the subsequent bounds and complete branch partition.

In the actual run it took 12 steps. This result was saved and reused by the continuation, which performed zero additional greedy steps.

### Node lower bounds

For an uncovered square $S$, its available deletion edges are $A_S=S\setminus F$. Since the square is uncovered, it has no edge already in $D$. An empty $A_S$ makes the node infeasible.

The first lower bound uses the maximum remaining coverage gain over **all** edges that are neither selected nor forbidden. If $u$ squares remain and that maximum is $g>0$, at least $\lceil u/g\rceil$ additional edges are needed. Gains cannot increase as more squares become covered. With uncovered squares and $g=0$, the node is infeasible; the implementation does not divide by zero.

The second lower bound greedily packs uncovered squares whose available-edge sets are pairwise disjoint. Every completion must choose at least one edge from each of those disjoint sets, so their number is a valid additional-deletion bound. The square IDs, actual available-edge sets, their masks and their union are retained. Full geometric edge-disjointness is unnecessary; disjointness of the currently available sets is what the proof uses.

The node bound is the maximum of these two bounds. Given a retained feasible incumbent of size $b$, the node is pruned when

$$
|D|+\max\!\left(
\left\lceil\frac ug\right\rceil,
\text{packing size}
\right)\ge b.
$$

Equality pruning is intentional. The goal is one optimum witness; equal-size alternatives need not be searched.

### Exhaustive, disjoint branching

The branch square is chosen among uncovered squares by smallest available-edge count, then square ID. At that parent, its available edges are sorted by decreasing current gain, then edge ID. This order is fixed before any child is generated.

Write that order $e_0,\ldots,e_{r-1}$. Child $j$ selects $e_j$ and forbids the earlier available edges:

$$
D_j=D\cup\{e_j\},\qquad
F_j=F\cup\{e_0,\ldots,e_{j-1}\}.
$$

Later edges remain available. Every feasible completion must hit the branch square and has one unique first selected edge in the frozen order. It therefore belongs to exactly one child. This proves both exhaustiveness and disjointness of the partition.

Every child's transition records the chosen square, branch index, selected edge and earlier available edges. Parent records retain the full order. All siblings are produced before the copied search transaction is committed. The frontier is a stack: children are pushed in reverse branch order so the first branch is visited first.

### Completion and incomplete states

There are two completion reasons:

| Reason | Meaning |
|---|---|
| `root_capacity_attained` | A feasible incumbent attains the global root lower bound; all pending nodes are explicitly closed by it |
| `frontier_exhausted` | Every branch has been handled by the exact partition, a valid prune, infeasibility or a complete cover |

A node-local bound cannot close unrelated pending branches. The special global closure uses only the root-wide incidence bound and an attaining full cover.

If the requested node budget is consumed while the frontier is nonempty, the result remains `incomplete` with termination `node_budget`. If the cumulative processed-node cap is reached first, termination is `total_node_limit`. Neither state is silently promoted to optimal.

At a successful advance boundary the complete updated search replaces the old one, including all generated siblings and frontier entries. A failed advance does not commit its staged search. The caller remains responsible for retaining any thrown error and for keeping snapshots within the declared copy bounds.

## Public API

The CommonJS module exports frozen `SCHEMA`, `LIMITS`, `compileCubeSquareCover` and `openCubeSquareCover`. An engine exposes the methods below. There are no package dependencies, filesystem calls, network calls, workers or native subprocesses in the module.

### Constructing a new finite object

~~~javascript
const {
  compileCubeSquareCover,
  openCubeSquareCover
} = require("./cube_square_cover.cjs");

const engine = compileCubeSquareCover({
  source_id: "my-cube-study/input",
  dimension: 4
});

// A successful advance commits a complete atomic frontier boundary.
const step = engine.advanceSearch({ node_budget: 1 });
const checkpoint = engine.snapshot();
~~~

This is the public call shape for a new caller-owned computation. The supplied JSON already contains the recorded Q4 computation; its construction and completed search do not need to be repeated to inspect that evidence.

`compileCubeSquareCover` builds all vertices, edges, coordinate squares, incidence masks, the classical baseline and one pending root. It performs no branch search. Its first session uses the requested `source_id`.

`advanceSearch` returns the search status, termination reason, incumbent counts, pending count, root bound and newly performed work counters. On the first advance it also builds the deterministic greedy seed. Later advances reuse that complete greedy history.

### Opening a saved object

~~~javascript
const saved = require("./q4_square_cover.json");

const reader = openCubeSquareCover(saved.fresh_reader.snapshot, {
  source_id: "my-cube-study/saved-reader"
});

const status = reader.assess({});
const firstSquare = reader.getSquare({ square_id: 0 });
const kept = reader.pageEdges({
  view: "kept",
  offset: 0,
  limit: 24
});
~~~

The input snapshot is defensively copied. Opening appends one new session with a unique bounded source ID. It does not mutate the caller's input object.

An incomplete checkpoint can be opened through the same entry point and advanced. The entire fixed universe, already processed nodes, incumbent history and frontier are part of the snapshot. A new session ID distinguishes that continuation from earlier activity.

`source_id` is a caller-provided provenance label. It is not authentication of an artifact or a mathematical theorem. The consumer JSON separately records the implementation blob used for its actual work.

### Graph and proof queries

Unless an explicit `incumbent_id` is supplied, graph queries use the best current incumbent. Historical incumbents remain available. Their kept and deleted edge lists are in increasing edge-ID order.

| Method | Required arguments | Main result |
|---|---|---|
| `assess` | None; optional `incumbent_id` | Selected witness counts and density, global best bounds, status and completion |
| `getIncumbent` | None; optional `incumbent_id` | Full retained edge partition and square-hit witnesses |
| `getEdge` | `edge_id` | Canonical edge, square incidences and its kept/deleted assignment |
| `selectEdge` | `view`, `rank` | Edge at a zero-based rank in that incumbent's selected view |
| `rankEdge` | `view`, `edge_id` | Membership plus zero-based rank, or `rank:null` if absent |
| `pageEdges` | `view`, `offset`, `limit` | Consecutive full edge records |
| `getSquare` | `square_id` | Coordinate square, retained hit witness and four edge assignments |
| `pageSquareWitnesses` | `offset`, `limit` | Complete square definitions with their retained hit records |
| `vertexNeighbours` | `vertex_id` | All incident edge assignments and sorted kept-neighbour IDs |
| `getSearchNode` | `node_id` | Complete retained search state, analysis, children and disposition |
| `pageSearchNodes` | `offset`, `limit` | Consecutive complete node records |
| `pageFrontier` | `offset`, `limit` | Pending nodes in current stack order |
| `getGreedyStep` | `step_id` | Complete gain array and chosen greedy transition |
| `summary` | None | Dimensions, counts, work and current session metadata |
| `snapshot` | None | Complete portable state, including all session events |
| `advanceSearch` | `node_budget` | An atomic search advance and its new-work receipt |

`getIncumbent` takes an argument object, for example `getIncumbent({})`. `assess` also accepts its default empty object. The other query methods require their listed arguments.

The graph view is exactly one of `all`, `kept` or `deleted`. Ranks are zero-based and specific to both the view and incumbent. A stable edge ID does not change when the incumbent improves; its membership and view rank can change.

A page permits offsets from zero through the total length, inclusive. An offset at the total returns an empty page. A page's `next_offset` is `null` precisely when its end reaches that view's total. No silently truncated page or omitted record is represented as complete.

The square's edge IDs are in perimeter order, not increasing numeric order. For square zero in Q4, the cycle is `[0,1,3,2]` and the edges are `[0,9,1,8]`. The final witness deletes edge zero, so that square's retained hit list is `[0]`.

`assess({incumbent_id:0})` distinguishes historical witness 0 from the final optimum: its `selected_kept_count` is 16, while the completed search's best lower and upper bounds are both 24. Selecting a historical incumbent does not rewind or invalidate the finished search.

### What opening checks

The saved loader checks bounded JSON shape, source/request agreement, universe sizes, ID order and ranges, incidence-list lengths, canonical mask width, mask/list bindings, kept/deleted edge partitions, parent/child references, fixed branch-order references, pending-frontier presence and recorded-history linkage. It checks that the last recorded advance agrees with the current frontier and incumbent.

Those checks do **not** reconstruct the cube's coordinate semantics, recompute coverage unions from chosen deletions, replay gain or packing inequalities, prove the root capacity argument, or rerun search expansions. For example, the loader checks the shape and references of a square-hit record; it does not independently prove that its listed edge hits that square.

Consequently, a structurally accepted snapshot still carries the retained compiler/certificate premise. It is not an independent proof checker for arbitrary untrusted JSON. `mathematical_proof_authenticated` remains `false` in the validation receipt. Source labels and embedded counters are not cryptographic attestations.

The new actual reader's structural work is recorded explicitly:

| Check | Recorded count |
|---|---:|
| Vertex records | 16 |
| Edge records | 32 |
| Square records | 24 |
| Search nodes | 174 |
| Incumbents | 6 |
| ID reference checks | 10,315 |
| Mask shape/binding checks | 2,390 |
| Parent/child link checks | 346 |
| Pending references | 0 |
| Universe-size equalities | 3 |
| Coverage unions recomputed | 0 |
| Gain/packing bounds replayed | 0 |
| Global capacity proof replayed | 0 |
| Search expansions replayed | 0 |

The 346 link checks cover both directions of the 173 parent/child relationships. They do not mean 346 distinct tree edges.

Opening the earlier paused snapshot checked only its five nodes, two incumbents and four pending references. That earlier opening performed 746 ID-reference checks and 146 mask shape/binding checks. Both opening receipts remain in the JSON.

### Query events and copies

Each query records its exact arguments, result or error, and declared query work in the current session. Bounded arguments are copied before execution. Successful results are copied for the caller before committing the success event, so caller edits cannot mutate the stored result.

Errors after argument retention are recorded as query errors. Invalid argument-object or copy-limit failures that occur before retention do not create a complete query event. Failed advances do not create a successful advance record.

`summary()` and `snapshot()` return defensive copies and do not append query events. `advanceSearch` appends a search-advance reference rather than an ordinary query. The returned engine and exported API constants are frozen.

### Explicit bounds

| Resource | Bound |
|---|---:|
| Dimension | Integer 1 through 6 |
| Cube vertices at dimension 6 | 64 |
| Cube edges at dimension 6 | 192 |
| Coordinate squares at dimension 6 | 240 |
| Cumulative processed search nodes | 2,048 |
| Generated nodes | 8,193 |
| Requested nodes per advance | 1 through 256 |
| Saved search advances | At most 256 |
| Sessions | At most 32 |
| Queries plus search advances in one session | At most 256 |
| Ordinary page size | 1 through 64 |
| Complete-node page size | 1 through 8 |
| Source-ID length | 1 through 512 characters |
| One defensive copy | At most 4,000,000 visited values and 32,000,000 string/key characters |
| Copy depth | At most 48 |

The generated-node ceiling is one root plus at most four children for each processed node. Coordinate and count arithmetic stays in safe integers at these dimensions. Population masks use `BigInt`, then canonical lowercase hexadecimal strings for portable JSON.

Copy bounds apply to aggregate records, including growing histories and snapshots. The dimension/node caps are not a promise that every combination of maximum-size state and query history fits every copy bound. Callers should retain incremental snapshots and use the stated page limits. A copy-limit error is not a mathematical infeasibility or optimality result.

## Fresh saved-reader evidence

At **2026-10-04T20:48:39.014Z**, a third engine opened the completed snapshot. It made 16 new queries and zero search advances. The complete search object remained literally identical before and after those queries.

The query sequence is retained, in order:

| Index | Method | Requested purpose / observed result |
|---:|---|---|
| 0 | `assess`, incumbent 0 | Historical baseline keeps 16; final best is still 24 |
| 1 | `assess`, current | Exact finite kept interval is [24,24], pending count zero |
| 2 | `getIncumbent`, incumbent 5 | Complete attaining edge partition and 24 hit witnesses |
| 3 | `pageEdges`, all | All 32 edge records |
| 4 | `pageEdges`, kept | All 24 kept edge records |
| 5 | `pageEdges`, deleted | All eight deleted edge records |
| 6 | `selectEdge`, kept rank 12 | Edge 16, coordinate 2, endpoints 0 and 4 |
| 7 | `rankEdge`, kept edge 16 | Present at rank 12 |
| 8 | `rankEdge`, kept edge 0 | Absent; rank is null |
| 9 | `getSquare`, square 0 | Cycle [0,1,3,2], retained deleted hit [0] |
| 10 | `pageSquareWitnesses` | All 24 square definitions and hit records |
| 11 | `vertexNeighbours`, vertex 0 | Kept neighbours [2,4,8]; edge to 1 is deleted |
| 12 | `getSearchNode`, node 0 | Original root bounds and four-way frozen branch |
| 13 | `getSearchNode`, node 170 | The eight-edge complete-cover leaf |
| 14 | `pageFrontier` | Complete empty frontier |
| 15 | `getGreedyStep`, step 0 | Initial complete 32-entry greedy gain array |

The reader tracked nine binary-search steps, 73 edge-assignment membership checks and 102 returned records. That last counter counts method-level records: one full incumbent, one search node or one greedy-step object counts as one even when it contains nested arrays. It is not a count of every nested JSON object or mathematical fact.

New topology construction, search processing and cover-proof replay counters are all zero for that reader. Its structural opening and the nine binary steps/73 assignment checks are real work and are reported separately.

## Complete work and retention ledger

### Construction

| Declared operation | Count |
|---|---:|
| Vertices materialized | 16 |
| Vertex weight bit steps | 64 |
| Edges materialized | 32 |
| Squares materialized | 24 |
| Edge-square memberships | 96 |
| Baseline edge parity checks | 32 |
| Baseline square checks | 24 |
| Baseline edge-hit checks | 96 |
| Global capacity divisions | 1 |

### Search, both advances combined

| Declared operation | Count |
|---|---:|
| Greedy steps | 12 |
| Computed gain entries | 3,606 |
| Gain popcount bit steps | 4,823 |
| Greedy remaining-square popcount bit steps | 100 |
| Uncovered-square availability rows | 1,166 |
| Square-edge availability checks | 4,664 |
| Packing candidates examined | 1,166 |
| Retained packing rows | 452 |
| Node capacity divisions | 144 |
| Processed nodes | 156 |
| Newly generated children | 173 |
| Branched nodes | 52 |
| Bound-pruned nodes | 97 |
| Infeasible nodes | 0 |
| Complete-cover leaves | 7 |
| Nodes closed by global equality | 18 |
| Candidate-incumbent calls | 8 |
| Incumbent improvements | 5 |
| New incumbent square checks | 120 |
| New incumbent edge-hit checks | 480 |

The root is part of the topology/search initialization, so 173 new children plus that root gives 174 generated node records.

Every computed gain entry is retained in its full edge-indexed array. Selected or forbidden edges have `null` entries because their gains were not computed in that pass. All 1,166 availability rows and all 452 packing rows are retained in node analyses.

A candidate-incumbent call that cannot improve the existing deletion count returns before constructing another full square-hit table. The five improving candidates each retain all 24 new hit rows; their 120 square checks and 480 edge-hit checks appear above. The initial baseline's 24/96 checks are in construction work instead.

Each advance also reports 58 saved topology masks decoded: 32 edge masks, 24 square masks and the two full-universe masks. Decoding those saved masks does not reconstruct coordinates, edges or squares. The work tables count the declared operations; they do not claim to count every allocation, comparison or V8 instruction.

### Portable locations in the data file

| JSON location | Complete retained content |
|---|---|
| `construction` | Exact request, first timestamp, summary and observation |
| `initial_frontier.snapshot` | Full universe, baseline, greedy cover, first processed root and all four pending child states |
| `saved_continuation` | Exact opening/advance request, result, summaries, timestamp and observation |
| `fresh_reader.snapshot.topology` | Complete fixed vertex/edge/square universe |
| `fresh_reader.snapshot.search.nodes` | All 174 node records |
| `fresh_reader.snapshot.search.greedy` | All 12 greedy steps and every gain array |
| `fresh_reader.snapshot.search.incumbents` | All six incumbents, edge partitions and complete hit witnesses |
| `fresh_reader.snapshot.search.advances` | Both complete search-advance ledgers and frontier boundaries |
| `fresh_reader.snapshot.search.completion` | Attained root bound and all 18 globally closed pending nodes |
| `fresh_reader.snapshot.sessions` | Constructor, continuation and fresh-reader sessions |
| `fresh_reader.snapshot.sessions[2].queries` | All 16 actual reader requests, results and counters |
| `finding` | Finite result, exact deleted-edge records and scope |
| `retention` | Completeness and literal-identity dispositions |

The final snapshot contains the unchanged completed search together with the new reader session. The earlier paused snapshot is retained separately because its then-pending child states matter for a portable continuation.

No generated node, computed gain row, availability row, packing witness, incumbent, advance or reader query is sampled or truncated. Flat JSON records and short primitive arrays are formatted on one line only for readability. Formatting preserved exact parsed object content.

The topology and construction counters were compared by literal retained-object identity across stages. The initial greedy history, first advance, processed root and original incumbents also matched. The completed search was literally unchanged by the reader. These comparisons did not re-enumerate squares, prove bounds or rerun the search.

### Timing observations

| Stage | Single observed time |
|---|---:|
| New constructor | 1 ms |
| First advance, including greedy seed | 2 ms |
| Open paused snapshot | 3 ms |
| New continuation advance | 10 ms |
| Open completed snapshot | 16 ms |
| Sixteen-query loop, including local result retention | 8 ms |

These are one-off observations from the recorded connected V8 execution. Snapshot serialization, publication and network operations are outside the constructor/advance timings. No benchmark or general performance guarantee is inferred.

## Scope of the conclusion

The full mathematical certificate gives one exact finite value for Q4. The generic module supports its stated bounded inputs and retains an explicit incomplete frontier when the budget stops. This contribution makes no assertion about every maximum graph, automorphism classes, larger uncomputed dimensions, current best asymptotic bounds, new priority or prize eligibility.

The open large-dimension problem remains separate. No sponsor contact, submission, native runtime, external evaluator, accepted-data reconstruction or proof replay was part of this operation.
