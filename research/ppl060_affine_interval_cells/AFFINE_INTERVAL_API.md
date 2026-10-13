# Exact affine copies in a union of intervals

This package gives the complete feasible parameter region for a finite increasing real pattern P, a finite union E of separated closed intervals, and a bounded rectangle of positive scales a and translations b. It decomposes the pairs satisfying aP+b ⊆ E into exact rational convex cells, retaining successful prefixes, rejected branches, polygons and boundary data. A saved reader answers fiber, area, point-location and witness queries without repeating the assignment search.

The actual thirteen-point instance has seven two-dimensional cells and three disjoint scale bands. Its largest permitted scale is **25/29248**, with **b=0** as the only translation at that scale. These are exact results for the declared input and parameter rectangle.

## Source conventions and mathematical boundary

Feng, Lai and Xiong, [*Erdős similarity problem via bi-Lipschitz embedding*, arXiv:2312.01319v1, December 2023](https://arxiv.org/pdf/2312.01319), §1.1, use affine copies λP+t for real λ≠0 and t, and Lebesgue-measurable target sets. They credit Steinhaus (1920) with the established finite-pattern theorem: every finite real pattern has an affine copy in every measurable set of positive measure. Their infinite question asks whether every infinite pattern can be avoided, at every nonzero affine scale, by some measurable set of positive measure. This is dated author-source context; the paper's bi-Lipschitz results concern a different class of maps.

The separately read [FormalConjectures/ErdosProblems/120.lean](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/120.lean) annotates the infinite question as research open and the finite-set variant as research solved, with local placeholder proofs. Its complete decoded text had computed Git blob identity b29e2ba0152856d83ba539e9e757664df19648ac. The connector supplied no immutable upstream commit or provider blob, so this is a content identity, not an invented upstream pin. No external proof was opened or audited.

The new contribution is finite exact parameter representation and navigation. Finite-copy existence is prior mathematics. This API restricts scales to a specified positive interval, uses a finite interval union as target and a finite pattern as source, and imposes a translation window. It does not decide the infinite problem, cover all nonzero scales or all positive-measure sets, establish current global status, or assert mathematical novelty.

## One identified input

The retained host from Commons #31551 is

~~~text
[1,13,32,66,169,174,396,416,756,858,915,1016,1044].
~~~

Its exact input values came from:

- path: research/ppl054_subset_sum_obstructions/thirteen_host_subset_obstructions.json
- blob: 95b8773c69e13315f505f64b8b108de2cef78689
- released commit: d0b51f786f58d15ab8c69f7440234abc6cb012ed

Only the literal values are used. Subtracting one gives the new finite pattern

~~~text
P = [0,12,31,65,168,173,395,415,755,857,914,1015,1043].
~~~

No field, B3, subset-sum or earlier geometry result is required or recomputed. The new target is explicitly declared as

~~~text
E = [0,5/32] ∪ [7/32,3/8] ∪ [5/8,25/32] ∪ [27/32,1].
~~~

Its four components are closed, pairwise separated by positive gaps, and have total Lebesgue measure 5/8. This is the entire finite target, not a partial approximation silently standing for an infinite set. Components are indexed 0,1,2,3 in increasing order.

The parameter rectangle is

~~~text
1/66752 <= a <= 1/1043
0 <= b <= 1.
~~~

All boundaries are included. Since 66752=64·1043, the smallest allowed copy has span 1/64. The parameter rectangle has area 9/9536. Parameter area is measured in the stated (a,b) coordinates; reparametrizing the scale would change that numerical area.

## Exact finite result

All seven cells have dimension two. The compiler also preserves segments and points for other allowed inputs; those branches were source-inspected, not exercised through an additional consumer.

| Cell | Interval assignment along the 13 sorted points | Scale projection | Area |
|---|---|---|---|
| 0 | 0000000000000 | [1/66752, 5/33376] | 81/8544256 |
| 1 | 0000000011111 | [1/5440, 3/8344] | 58023647/17217487544320 |
| 2 | 0000001122233 | [11/13472, 25/29248] | 171221929/592710326906880 |
| 3 | 1111111111111 | [1/66752, 5/33376] | 81/8544256 |
| 4 | 2222222222222 | [1/66752, 5/33376] | 81/8544256 |
| 5 | 2222222233333 | [1/5440, 3/8344] | 58023647/17217487544320 |
| 6 | 3333333333333 | [1/66752, 5/33376] | 81/8544256 |

A digit here names the target component containing that pattern point's image. It does not label a separate copy of an interval endpoint. The full scale projection is

~~~text
[1/66752, 5/33376]
∪ [1/5440, 3/8344]
∪ [11/13472, 25/29248].
~~~

The union's exact two-dimensional area is

~~~text
39995949762970723 / 889803874067822418432.
~~~

Dividing by the rectangle's area gives the exact area fraction

~~~text
39995949762970723 / 839789730139513608.
~~~

The total is an area of a continuous family, not a count of individual affine copies.

Cell 2 is the only cell reaching the maximum scale. Its four vertices, in counterclockwise order starting at the lexicographically least vertex, are

~~~text
(11/13472, 101/6736)
(27/32480, 0)
(25/29248, 0)
(5/5928, 245/23712).
~~~

Consequently the maximum scale is attained at exactly (a,b)=(25/29248,0). The other cells have strictly smaller maximum scale. This is optimality inside this target/pattern/rectangle, not an optimization over all measurable sets.

## Boundary fibers

Closed endpoints matter. A fiber can have zero one-dimensional measure and still contain copies. The saved reader records the following examples.

| Scale a | Complete translation fiber |
|---|---|
| 1/66752 | [0,9/64] ∪ [7/32,23/64] ∪ [5/8,49/64] ∪ [27/32,63/64] |
| 5/33376 | {0,7/32,5/8,27/32} |
| 1/6000 | empty |
| 1/5440 | {87/1088,767/1088} |
| 1/3000 | [0,43/2400] ∪ [5/8,1543/2400] |
| 3/8344 | {0,5/8} |
| 1/2000 | empty |
| 11/13472 | {101/6736} |
| 25/29248 | {0} |
| 1/1043 | empty |

In particular the fiber at a=1/3000 has length 43/1200. At fixed translation b=0, the scale fiber is

~~~text
[1/66752,5/33376] ∪ [7/24160,3/8344] ∪ [27/32480,25/29248].
~~~

There is no feasible scale in the declared rectangle at b=1/2. The exact cumulative area for a≤1/3000 is

~~~text
6798691439 / 154217145600000.
~~~

These queries intersect saved cells. They do not reconstruct the assignment tree.

## Why the cell decomposition is complete

Let the sorted pattern be x0<...<x(n−1), and let the separated target intervals be [Lj,Uj] in increasing order. For positive a, the images axk+b are increasing. Their interval indices therefore form a nondecreasing sequence. Conversely, a nondecreasing interval assignment is feasible precisely when its linear constraints and the parameter rectangle have a common point.

For an assignment j0,...,j(n−1), that region is

~~~text
rectangle ∩ ⋂k { (a,b) : Ljk <= a*xk+b <= Ujk }.
~~~

It is an intersection of closed half-planes with a bounded rectangle, hence a compact convex polygon, segment, point, or empty set. Exact rational clipping constructs that intersection.

The root is the entire parameter rectangle. At each pattern point, every interval index at least the previous index is considered. Each branch clips first against the lower constraint and then the upper constraint. Empty branches are retained as rejected; accepted children retain their complete resulting polygon. Induction on the prefix length shows that every permissible interval assignment is either represented by a final cell or excluded at its first empty prefix. There is no discarded sampling region.

For n points and m target intervals, there are at most binomial(n+m−1,m−1) nondecreasing complete assignments. Here that bound is binomial(16,3)=560. This is a combinatorial bound before clipping, not the actual number of explored prefix branches.

Because the target components are strictly separated closed sets, an image point cannot belong to two components. Thus every feasible (a,b) has exactly one complete interval assignment. Distinct cells in this decomposition are disjoint as sets. Summing their areas consequently gives the union area without overlap corrections. Lower-dimensional cells, if present, contribute zero area but remain in the feasibility result.

### Clipping and rejection evidence

For a half-plane A*a+B*b<=C, the compiler evaluates A*a+B*b−C at every current vertex. A linear functional reaches its minimum on a convex polygon at a vertex; the same assertion holds for a segment or point. If every value is strictly positive, the entire current cell is outside and the branch is rejected. The record retains the positive minimum and its vertex index.

If the lower constraint passes but the upper one rejects, the lower-clipped polygon is also stored, making the second rejection's input explicit. Accepted nodes retain the final polygon. The branch list records every interval option, its parent, current pattern index and accepted child or rejection.

An edge crossing a boundary is intersected by exact rational interpolation. Consecutive duplicates are removed. Degenerate collinear output is retained as its extreme segment or single point. A nondegenerate polygon is kept in counterclockwise order with a fixed starting vertex. No floating-point predicates are used.

The area uses the rational shoelace formula. Projection uses vertex extrema. A vertical or horizontal fiber intersects each saved polygon edge exactly and takes the extreme intersection coordinates; all resulting closed intervals, including points, are retained and merged for the union summary. The reader's cumulative-area query clips saved polygons at a requested scale before summing their areas.

This argument describes the implementation's finite correctness contract. The saved JSON and structural reader are not an independent formal verification of every arithmetic step.

## Files and durable lineage

- affine_interval_cells.cjs — pure CommonJS compiler and separate saved reader.
- thirteen_pattern_interval_cells.json — exact input, complete snapshot, construction counters and all 32 reader outputs.
- AFFINE_INTERVAL_API.md — this guide.
- README.md — entry point and scope.

The frozen source identity is **55856b4c50be412b04725f882a960d4861ea6ad3**. The exact standalone input was banked as **ae41deb1eb6b84aad33a23e5348aaa14391baee9** before construction. The complete initial result was banked immediately after the one constructor call as **03a68c30c954513e64e09cae698aeaa405601c13**, 35,549 bytes. The final complete record, after saved-reader queries, is **c5745d1e7e120255dec87bb6172531ca48c60099**, 83,464 bytes. These are Git blob identities of exact UTF-8 texts, not commit identifiers.

The record's source field binds the implementation used by the actual call. The source was not changed after that execution. The final record preserves the construction snapshot and appends the new query records.

## API

~~~js
const {
  VERSION,
  compileAffineIntervals,
  openAffineIntervals
} = require("./affine_interval_cells.cjs");

const record = JSON.parse(savedText);
const index = openAffineIntervals(JSON.stringify(record.snapshot));

index.summary();
index.cellsPage(0, 64);
index.cell(2);
index.witness(2);
index.translationFiber("25/29248");
index.scaleFiber("0");
index.areaThrough("1/3000");
index.assignmentPrefix([0]);
index.statistics();
~~~

These calls show the retained consumer's usage. They are not an instruction to recompile it before reading.

### Compiler input

~~~js
const snapshot = compileAffineIntervals({
  pattern: ["0","12","31","65","168","173","395","415",
            "755","857","914","1015","1043"],
  intervals: [
    ["0","5/32"], ["7/32","3/8"],
    ["5/8","25/32"], ["27/32","1"]
  ],
  scale: ["1/66752","1/1043"],
  translation: ["0","1"],
  provenance: { /* caller's identified input source */ }
}, {
  max_nodes: 20000,
  max_branches: 100000
});
~~~

The actual constructor was run once on this input with its complete retained provenance. Other accepted input shapes have been inspected in source but not exercised through another consumer.

Contracts:

- 1–16 pattern points, supplied strictly increasing; duplicates are rejected.
- 1–6 target intervals, ordered, of strictly positive length and strictly separated. Touching intervals must first be represented as their single union component by the caller; they are not accepted as distinct components.
- Scale bounds satisfy 0<a_min≤a_max. Translation bounds satisfy b_min≤b_max. Degenerate parameter rectangles are permitted.
- Rationals are safe integer Numbers or strings such as "7", "-2", "5/32". Decimal/floating notation is rejected. Reduced compiler-input numerator and denominator have at most 80 digits.
- Exact output and saved-query rational components have a 4,096-digit cap. Exceeding it throws instead of rounding.
- Accepted-prefix node budget defaults to 20,000 and may be set from 1 to 30,000.
- Attempted-branch budget defaults to 100,000 and may be set from 1 to 200,000.
- Exhaustion throws without returning a completed snapshot. This interface does not advertise resumable partial construction.
- Provenance is copied as JSON data. The implementation has no filesystem, network or external-process access.

The API accepts only positive scales. A reflected-pattern transformation could model negative scales, but that transformation is not performed by this consumer and is not silently included in its counts or projection.

### Saved reader

openAffineIntervals accepts the snapshot object or its JSON string, with a 24,000,000-character string limit. It copies the input and validates its schema, rational shape, array caps, ordered input contract, prefix/parent links, complete interval-option lists, accepted-child links, positive saved rejection margins, required lower-clipped polygons, complete final-leaf list and inherited assignment vectors.

These structural checks bind the navigation layout. They do **not** repeat half-plane clipping, independently authenticate edited polygons, recompute rejection minima or prove the stored summary and areas. Use the identified frozen source and complete saved record as the construction premise.

The methods return copies rather than mutable references to the retained record.

| Method | Result and ordering |
|---|---|
| summary() | Saved dimensions, area, projection and maximum-scale metadata |
| cellsPage(start=0,limit=32) | Final cells in accepted-prefix traversal order |
| nodesPage(start=0,limit=32) | Complete accepted prefix nodes and their polygons |
| branchesPage(start=0,limit=32) | Complete attempted branches, including rejected ones |
| cell(id) | One final cell, assignment, projection and complete polygon |
| witness(id) | Vertex-average parameter pair and all affine images with target-membership checks |
| locate(a,b) | Domain check, first failed image or the unique saved assignment/cell |
| translationFiber(a) | Closed translation intervals and their exact union/length |
| scaleFiber(b) | Closed scale intervals and their exact union/length |
| areaThrough(a) | Exact area of the saved region with scale at most a |
| assignmentPrefix(indices) | Matching saved cell IDs and summed area |
| statistics() | Actual reader-operation counters |

Page starts range from zero through the array length; page limits range from zero through 64. Cell IDs are zero-based. A zero-length page is intentionally allowed. Prefix interval IDs must be nondecreasing. A prefix is an interval-assignment prefix, not a numerical point prefix or an ordering of arbitrary copies.

The witness is the average of polygon vertices. It lies in the cell by convexity; for a nondegenerate polygon it is an interior point, while for a segment or singleton it lies in the corresponding relative interior. It is not generally the maximum-scale witness. Cell 2's saved witness query therefore gives an interior example, whereas its maximum-scale endpoint comes from the saved cell/fiber.

No query enumerates the infinitely many feasible affine copies. The finite objects being paged are cells, prefix nodes and branch records.

## Actual work and saved query work

The once-only constructor formed:

- 86 accepted prefix nodes.
- 183 attempted branches.
- 93 lower-constraint and 5 upper-constraint rejections.
- 273 half-plane clips.
- 895 vertex-inequality evaluations.
- 154 new edge intersections.
- 7 final cells.
- Zero old subset-sum computations.

Its single observed elapsed time was 7 ms in the connected runtime. This is not a benchmark or performance guarantee.

A fresh context opened the saved snapshot and made 32 queries. It exported every final cell, every prefix node and every attempted branch through pages; queried all seven cell witnesses; located the interior witness of cell 2; queried ten vertical fibers, three horizontal fibers, two cumulative areas and one assignment prefix.

Reader counters record 115 saved-cell scans, 14 fresh query clips, 8 fresh query edge intersections, 48 query vertex evaluations and 104 affine-image evaluations. Those are new query arithmetic and are reported explicitly. New assignment branches, compiler clips and old subset sums were all zero. Structural opening of the records is distinct from reconstructing the construction.

The complete finite result retains exact closed boundaries and every declared input. It establishes this instance's feasible region and restricted maximum scale, with no conclusion about the infinite Erdős similarity conjecture.
