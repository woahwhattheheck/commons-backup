# Exact finite lattice diameter families

## Result and mathematical scope

For the finite triangular-lattice host

\[
H_3=\{(a,b)\in\mathbb Z^2:\max(|a|,|b|,|a+b|)\le3\},
\]

embedded in the real plane by

\[
(a,b)\longmapsto (a+b/2,\sqrt3\,b/2),
\]

the completed calculation classifies every maximum-cardinality subset of diameter at most \(4\). Its maximum cardinality is **19**, and exactly **seven** subsets attain that cardinality. Every one of the seven has minimum distance exactly \(1\), diameter exactly \(4\), **42 unit pairs** and **24 unit equilateral triangles**.

These are exact statements about this fixed 37-point host. They also imply that the minimum diameter among its 19-point subsets is \(4\), attained by precisely these seven sets. Indeed, a 19-point subset of smaller diameter would already occur in the complete family at diameter at most \(4\); all members of that family have diameter \(4\).

The result does not identify the minimum diameter among arbitrary 19-point sets in the real plane. In particular, it does not resolve Erdős 99's eventual assertion about every global diameter minimizer.

The seven explicit coordinate lists can be written as \(H_2+c\), with \(c\in H_1\). This is a compact description of the retained lists, not a second construction or enumeration. The saved index uses a deterministic proof-DAG order:

| Zero-based rank | Axial translation center \(c\) |
| --- | --- |
| 0 | \((-1,0)\) |
| 1 | \((-1,1)\) |
| 2 | \((0,0)\) |
| 3 | \((0,-1)\) |
| 4 | \((0,1)\) |
| 5 | \((1,-1)\) |
| 6 | \((1,0)\) |

All 133 selected point occurrences, the seven complete vertex lists, their coordinate lists, and every contained unit-triangle identifier are in `hexagon3_diameter4_family.json`.

## Sources and the global question

The complete current FormalConjectures statement was read at blob `df35f07e3d9474e88b6297b9fe25d7c18c9237de`:

[FormalConjectures/ErdosProblems/99.lean](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/99.lean).

It quantifies over sufficiently large cardinalities and every global diameter minimizer among planar sets whose pairwise distances are at least one and whose minimum distance is attained at one. Its conclusion is the existence of a unit equilateral triangle. The retained source is annotated research open and has a placeholder theorem body; neither a proof audit nor a comprehensive current status claim is made here.

The formal source cites Paul Erdős, *Some problems in number theory, combinatorics and combinatorial geometry*, **Mathematica Pannonica 5(2) (1994), 261–269**. The bibliographic record is [EUDML 232764](https://eudml.org/doc/232764); its direct transport was unavailable.

Bezdek and Fodor's [*Minimal Diameter of Certain Sets in the Plane*](https://doi.org/10.1006/jcta.1998.2889), **Journal of Combinatorial Theory, Series A 85(1) (1999), 105–111**, defines the related \(D(n)\) problem in its indexed publisher abstract using distinct points at mutual distance at least one. The full publisher paper was unavailable in this source check. No known packing table or optimum from that paper was consumed.

For coordinate attribution, Gillespie, Mayne and Jiang's [*RNA folding on the 3D triangular lattice*](https://pmc.ncbi.nlm.nih.gov/articles/PMC2780420/), **BMC Bioinformatics 10 (2009), 369**, includes a two-dimensional triangular-lattice warm-up with axes at \(120^\circ\). Relabeling its second coordinate by its negative gives the \(60^\circ\) convention used here. This citation concerns coordinates, not a packing extremum.

## Exact geometry

For two axial points, write their coordinate differences as \(a,b\). The squared Euclidean distance under the displayed embedding is

\[
(a+b/2)^2+3b^2/4=a^2+ab+b^2.
\]

This positive-definite form is a positive integer for every nonzero integer pair. Thus distinct host points are separated by at least one. An arbitrary subset need not contain a unit pair, so the attained-minimum condition is recorded separately. For zero or one selected point, the API reports a null minimum squared distance and does not assert an attained minimum of one.

The compiler accepts distinct axial integer points, preserving their input order as vertex labels. It computes the complete upper-triangular pair table exactly once. A pair is an edge of the compatibility graph precisely when its squared distance is at most the supplied cap. Consequently cliques correspond exactly to feasible subsets.

Unit equilateral triangles are unordered triples of distinct labels whose three retained squared distances equal one. Each appears once in increasing label order. The complete host ledger is independent of whether a particular query subset contains the triple. Profiles filter that saved ledger.

For the actual host there are 666 pair records, 525 compatibility edges at squared cap 16, 90 unit pairs and 54 unit triangles. The full host has squared diameter 36; it is not itself a feasible subset at cap 16.

Coordinates have absolute value at most \(10^6\). Differences therefore have absolute value at most \(2\cdot10^6\), and every intermediate squared-distance result has magnitude at most \(12\cdot10^{12}<2^{53}\). All integer multiplications and additions in this calculation are exactly representable by JavaScript Number. The irrational coordinate embedding is used for the proof, not as floating-point input to the compiler. Bit masks and family counts use BigInt.

## Complete optimization and retained proof

Let \(G[P]\) be the compatibility graph induced by a candidate vertex mask \(P\). The solver records its maximum clique size \(\omega(P)\) and the number \(c(P)\) of cliques attaining that size. The empty candidate has \(\omega(\varnothing)=0\) and \(c(\varnothing)=1\), representing its one empty clique.

### Forced universal vertices

If \(U\) consists of vertices adjacent to every other vertex in \(P\), every maximum clique contains \(U\). A clique omitting any such vertex can be enlarged by adding it. Therefore

\[
\omega(P)=|U|+\omega(P\setminus U),\qquad
c(P)=c(P\setminus U).
\]

The snapshot retains \(U\) and the child state. The actual root has forced mask `51255296`, containing seven universal vertices, and child node 587. The complete root is node 588.

### Include and exclude branches

If no vertex is universal, a deterministic pivot \(v\) is chosen by maximum degree within \(P\), breaking ties by the smallest label. Every clique either includes \(v\) or excludes it. The two corresponding candidate masks are

\[
P_{\rm in}=P\cap N(v),\qquad P_{\rm out}=P\setminus\{v\}.
\]

The include optimum is \(1+\omega(P_{\rm in})\), and the exclude optimum is \(\omega(P_{\rm out})\). The larger value wins. When the two values agree, both families are retained and their counts are added. They are disjoint because exactly one contains \(v\).

The compiler first solves the include branch. It then greedily partitions \(P_{\rm out}\) into independent color classes of the compatibility graph. Every clique uses at most one vertex from each class, so the number of classes is a valid upper bound for the exclude optimum. Exclusion is pruned only when this upper bound is **strictly smaller** than the include optimum. Equality never prunes a branch, because it could contain additional maximum subsets.

Every used coloring is saved, including all its class masks. Every solved state is memoized by its candidate mask. This is an exact recurrence with auditable pruning evidence, not an assertion that the greedy coloring itself is optimal.

### What the DAG establishes

Nodes occur in child-before-parent order, and all child identifiers are smaller than their parent identifier. Each node contains its mask, kind, optimum and exact decimal count. Forced nodes retain their forced mask and child. Branch nodes retain the pivot, children, complete exclude-coloring partition, upper bound, prune flag and optimal-branch list.

The actual proof has:

| Retained quantity | Count |
| --- | ---: |
| Complete proof nodes | 589 |
| Empty nodes | 1 |
| Forced nodes | 164 |
| Branch nodes | 424 |
| Exclude branches pruned by strict coloring bounds | 205 |
| Memo hits | 219 |
| Greedy color classes retained | 2,017 |
| Vertex placements in those colorings | 3,699 |

The recurrence proves both the upper bound 19 and completeness of the seven-member family. The explicit members supply attainment. There is no isomorphism quotient: the 37 host labels are fixed, and all seven distinct subsets remain separate.

## Public API

The module has no I/O or dependency imports. It exports:

| Export | Purpose |
| --- | --- |
| `triangularHexagon(radius)` | Construct the bounded axial host, in increasing first coordinate and then second coordinate. |
| `compileLatticeDiameterFamily(input, options)` | Compute exact pair geometry, the complete unit-triangle ledger and the maximum-family proof DAG for one host and cap. |
| `openRetainedLatticeDiameterFamily(saved)` | Load a saved snapshot and expose its complete maximum-family index. |
| `LATTICE_DIAMETER_LIMITS` | Published resource and arithmetic limits. |

### Compile contract

`input` has `points` and `squared_diameter`. Points form a set: duplicate coordinate pairs are rejected, rather than counted with multiplicity. Labels follow the supplied order. The squared cap is a nonnegative exact integer.

`options.max_states` may lower the hard state cap. The actual operation supplied 50,000 and completed after 589 states. The generic hard cap is 100,000.

The return value has `snapshot` and `summary`. All geometry, proof nodes and compiler counters needed for the finite result are inside the snapshot. A state-budget exception carries `code: "STATE_CAP"` and a `partial` record with completed nodes, pending masks and geometry. This preserves incomplete work but is not a complete index or a supported resumable snapshot. It provides no optimum or infeasibility conclusion for the unfinished root. A character-budget exception retains the completed snapshot under `completed_snapshot`.

No state or character budget was reached by the actual input.

### Retained-reader contract

The loader accepts a snapshot object or its JSON string and makes its own copy. It checks the pair-table endpoints and order, reconstructs graph adjacency from the **retained** distances and cap, checks every listed unit triangle against those distances, and checks every proof recurrence, forced-vertex assertion and coloring certificate.

It does not independently recompute the squared norms from the supplied coordinates or certify completeness of the triangle ledger by reconstructing it. Those two geometric properties are identified premises from the retained compiler output. The complete combinatorial DAG is checked relative to that retained graph. Loading arbitrary data is therefore not an independent geometric provenance certificate.

This distinction is material: the compiler computed the full geometry once, while the reader uses that saved geometry and validates the finite optimization evidence.

The reader exposes:

| Method | Result and ordering |
| --- | --- |
| `summary()` | Host size, cap, exact maximum size and count, table sizes and family-order description. |
| `select(rank)` | One maximum subset, with increasing vertex labels and corresponding coordinates. |
| `rank(vertices)` | The exact zero-based rank of a supplied maximum subset; rejects nonmembers. |
| `membership(vertices)` | Feasibility, maximum-family membership, rank when applicable, or a first incompatible pair. |
| `profile(vertices)` | Minimum and maximum squared distances, cap feasibility, unit-pair count and all contained unit-triangle identifiers. |
| `page(start, limit, include_profiles)` | A bounded page of maximum subsets, optionally with complete profiles, and a next cursor. |
| `unitTriangle(id)` | One saved triangle's labels and axial coordinates. |
| `proofNode(id)` | A detached copy of a saved proof node. |
| `snapshot()` | A detached copy of the complete saved artifact. |
| `statistics()` | Load and query work counters. |

Ranks follow **include-first proof-DAG order**, not lexicographic order on the sorted vertex lists. Forced vertices do not add a branch. At a tied branch, the entire include family precedes the exclude family. This ordering is deterministic for the saved DAG and requires no new optimization.

A subset query rejects duplicate labels and labels outside the host. Profile queries may describe any host subset, including an infeasible or nonmaximum one. Empty and singleton subsets have squared diameter zero, null minimum squared distance and no unit triangles. They do not satisfy the attained-minimum-distance-one predicate.

Ranks and masks use exact decimal representations. The family has at most \(2^{40}\) members under the point cap, and decimal strings are bounded to 13 characters. Pages contain at most 4,096 rows. Object and array outputs are detached from the retained internal state.

### Connected V8 use of the saved data

With the published source text in `moduleText` and the complete JSON text in `dataText`:

```js
const module = { exports: {} };
new Function("module", "exports", moduleText)(module, module.exports);

const data = JSON.parse(dataText);
const index = module.exports.openRetainedLatticeDiameterFamily(data.snapshot);

const firstPage = index.page("0", 3, true);
const nextPage = index.page(firstPage.next, 3, true);
const summary = index.summary();
```

The data file already contains the complete geometry and proof. A caller can navigate it without invoking either the host constructor or compiler.

For a different finite input within the published limits:

```js
const result = module.exports.compileLatticeDiameterFamily(
  { points: callerAxialPoints, squared_diameter: callerSquaredCap },
  { max_states: callerStateBudget }
);
const index = module.exports.openRetainedLatticeDiameterFamily(result.snapshot);
```

This illustrates the interface; no second finite input was executed for this publication.

## Actual saved-reader consumer

A fresh connected V8 context loaded the completed snapshot and made nine queries:

1. A summary.
2. Three pages beginning at ranks 0, 3 and 6, each requesting up to three profiled rows. Together they exported every maximum subset once.
3. The rank of the central \(H_2\) subset, which is 2.
4. The full host's distance profile.
5. The full host's membership result, exposing incompatible pair \([0,14]\).
6. One unit triangle in the central maximum subset.
7. The proof root.

The reported unit triangle has vertex labels \([5,6,11]\) and coordinates \([(-2,0),(-2,1),(-1,0)]\). Its three squared distances are one in the saved pair table.

The reader checked all 589 proof recurrences, 263 forced-vertex occurrences and 2,015 pairs within retained color classes. Its seven page selections visited 98 DAG nodes. The one rank query visited 14 nodes. Eight profiles used 1,863 saved pair lookups and 432 saved-triangle containment checks.

Reader counters recorded:

| Work | Count |
| --- | ---: |
| New squared-norm evaluations | 0 |
| New unit-triangle ledger constructions | 0 |
| New optimization states | 0 |
| Maximum subsets exported | 7 |
| Complete profiles returned | 8 |

The zero counters concern recomputation of the original geometry and optimization. Loading and querying still performed the structural checks and lookups listed above.

One compiler observation took 10 ms; the fresh load took 8 ms and its queries took 2 ms in that connected V8 context. These are single observations, not a statistical benchmark or a runtime guarantee.

## Limits and execution coverage

The public module accepts at most 40 points with integer axial coordinates of absolute value at most \(10^6\), squared caps at most \(12\cdot10^{12}\), at most 100,000 solved states and snapshots of at most 16,000,000 characters. The convenience hexagon constructor is capped at radius 3. These are implementation bounds, not mathematical theorems about larger instances.

Only the radius-3 host at squared cap 16 was compiled. Empty and singleton inputs, other caps and point sets, larger searches, invalid-input paths and budget exceptions were inspected in the source but were not separately executed. No synthetic suite, second packing input, prior packing enumeration or external proof was replayed.

The executed source was frozen before the first construction and remains unchanged at Git blob:

`44a72997f6af110dbb05766c4550119cd65905ac`.

## Artifact map

- `lattice_diameter_index.cjs` contains the public compiler and saved reader.
- `hexagon3_diameter4_family.json` contains the full formal-source identity, source boundaries, request, complete geometry, all 589 proof nodes, all seven maximum subsets, every reader response and work counters.
- `README.md` provides the outcome, entry points and source links.
- This guide supplies the proof, API contract and finite/global distinction.

The mathematical interpretation of a saved index remains attached to its identified source and complete retained data. This artifact makes no claim to a new global packing record, an unconditional resolution of Erdős 99, or priority for triangular-lattice constructions.
