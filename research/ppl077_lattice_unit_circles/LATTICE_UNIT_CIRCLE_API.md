# Rational lattice unit-circle index

This API compiles every distinct circle of radius one containing at least three points of a finite rational lattice rectangle. It retains exact rational centers, complete incidences and the separate family of unordered triples determining each circle. Saved queries navigate those records without reconstructing circumcenters.

The one input is
`P = {(i/5,j/5): 0 <= i < 17, 0 <= j < 29}`.
It has 493 distinct points and exactly **837 qualifying unit circles**. Their memberships contain 5,680 incidences and 51,576 unordered determining triples. This establishes the finite lower bound `maxUnitCircleCount(493) >= 837`; it is not an equality or a planar extremal record.

## Complete actual result

| Points on a circle | Number of circles |
| --- | --- |
| 3 | 140 |
| 4 | 60 |
| 5 | 204 |
| 6 | 28 |
| 7 | 156 |
| 8 | 8 |
| 9 | 52 |
| 10 | 4 |
| 11 | 52 |
| 12 | 133 |

The local constructor examined 316 nonzero integer offsets in the disk of radius 10 and their 49,770 unordered pairs. It recorded 878 collinear pairs, 48,232 incorrect-radius pairs and 660 exact radius-five pair witnesses. Those witnesses produced 12 local centers, each with 12 lattice points including the origin.

The compiler did not assume integral centers. In this actual kernel, all centers happened to have integer lattice coordinates: (±5,0), (0,±5), (±4,±3) and (±3,±4). Their actual coordinates are obtained after division by five. Each local center has 55 retained witnesses choosing two of its other 11 points. This is the result of the finite exact kernel calculation.

Across the rectangle, 5,916 anchor translations merged to 1,013 candidate centers. Of these, 176 had fewer than three retained points; the remaining 837 are the complete published circle family. No whole-grid point-pair or point-triple family was enumerated. The earlier unscaled rectangle computations were not replayed. The observed 34 ms is one environment observation, not a benchmark.

## Files and reopening

- `lattice_unit_circles.cjs`: dependency-free CommonJS API, published version 1.0.1.
- `rectangle17x29_scale5_unit_circles.json`: input, all offsets and local witnesses, reverse point-incidence lists, full summaries, shard identities and source lineage.
- `circles_0000_0418.json`: circle IDs 0 through 418.
- `circles_0419_0836.json`: circle IDs 419 through 836.
- `saved_reader_queries.json`: all 17 completed continuation requests/results, full subset outputs, selection traces and work counters.
- This guide and `README.md`.

The circle shards are complete and consecutive. They are not samples or a first page.

```js
const fs = require("node:fs");
const path = require("node:path");
const { openLatticeCircles } = require("./lattice_unit_circles.cjs");
const data = JSON.parse(fs.readFileSync("./rectangle17x29_scale5_unit_circles.json", "utf8"));
const circles = data.circle_shards.flatMap(shard =>
  JSON.parse(fs.readFileSync(path.basename(shard.path), "utf8")).rows);
const index = openLatticeCircles({
  ...data.construction.snapshot,
  circles
});
const answer = index.tripleSelect("25788");
```

This is usage documentation, not an extra execution claim. The reader accepts the saved version-1.0.0 construction as well as version-1.0.1 snapshots. It performs structural and combinatorial checks when opening; it does not rerun geometric tests.

## Exact geometric construction

The public constructor is `compileLatticeCircles({rows,columns,denominator,...provenance})`. It admits integer row and column counts from 1 through 64, and an integer denominator Q from 1 through 8. The points are (x/Q,y/Q) with x in [0,rows) and y in [0,columns). IDs are `x*columns+y`. This ordering is part of the public contract.

In lattice units, a unit circle has radius Q. Translate a point on it to the origin. Every other point on the circle has integer offset b with squared norm at most 4Q², by the chord bound. The constructor enumerates that finite disk, excluding zero, and all unordered pairs of different offsets b=(bx,by), c=(cx,cy).

Put
`V = 2*(bx*cy-by*cx)`,
`U = (bx²+by²)*cy - (cx²+cy²)*by`,
and
`W = bx*(cx²+cy²) - cx*(bx²+by²)`.
If V=0, the three points are collinear and do not determine a positive-radius circle. Otherwise their circumcenter is (U/V,W/V), and its squared distance from the origin equals Q² exactly when
`U²+W² = Q²*V²`.

All of these determinant and radius operations use BigInt. Valid witnesses retain both offset indices and U,W,V. A center is normalized by dividing its two numerators and common denominator by their joint gcd, with positive denominator. Equal centers are merged exactly; no floating tolerance, square-root approximation or rounding is involved.

For each local center, the union of its witnessed offsets gives every integer lattice point on that circle. Indeed, a positive-radius circle intersects a line in at most two points. If it has at least three lattice points including the origin, every other lattice point can be paired with a different non-origin point to form one of the enumerated noncollinear triples. The origin is implicit in the local row.

The second stage translates every local center to every rectangle anchor. For each exact translated center, it collects the anchor IDs that lie on that circle. These are precisely all its points in the rectangle: each anchor on a circle having at least three lattice points has a corresponding translated kernel center. Filtering the merged memberships at size at least three therefore gives all qualifying circles.

This completeness argument also explains why a local center with only one or two rectangle points may be discarded. Any circle with three rectangle points necessarily has three full-lattice points and appears in the kernel under each of those anchors. Restricting a saved rectangle to a subset cannot create a previously absent qualifying circle.

The constructor is specialized to these lattice rectangles. It does not accept arbitrary rational point clouds, arbitrary radii, algebraic irrational coordinates or a positive-measure planar set.

## Circle and triple conventions

A circle is identified by its center because every retained radius equals one. Its center record `{x,y,denominator}` means (x/denominator,y/denominator), where the fields are decimal integer strings and the common denominator is positive and reduced jointly.

Circles are ordered first by exact center x-coordinate, then y-coordinate. Circle IDs follow that order. Each `members` array contains increasing point IDs. The record also names one anchor and local-kernel row that generated the center.

Every three distinct points on a positive-radius circle are noncollinear, so an m-point membership contributes `binomial(m,3)` determining triples. Three noncollinear points determine exactly one circle. Thus these fibers are disjoint even though different circles may share one or two points.

Global triple order is circle order, then lexicographic order of the three increasing member IDs. Ranks start at zero. Each circle stores its exact `triple_start` and `triple_count`. This ordering is not the global lexicographic order on all triples of grid IDs; the API does not substitute one for the other.

The first circle is centered at (−4/5,3/5), with members [0,6,32]. Circle 418 is centered at (8/5,14/5) and has members [101,127,133,155,163,241,251,329,337,359,365,391]. The last circle is centered at (4,5), with members [460,486,492].

Global rank 25,788 belongs to circle 418, local rank 110, and selects point IDs [133,163,329]. These are (4/5,17/5), (1,18/5) and (11/5,2). The saved inverse-rank query returns the same rank after receiving those IDs in reverse order. The collinear IDs [0,1,2] do not qualify.

## Saved query results

The corrected fresh reader completed 17 requests. They include global first/middle/last triple selection, inverse ranking, three local selections in circle 418, membership intersection, two subset profiles, exact translations and center lookups.

The checkerboard subset with x+y even has 247 points, 422 qualifying circles and 25,816 determining triples. The interior subset 2<=x<=14, 2<=y<=26 has 325 points, 605 qualifying circles and 26,056 determining triples. Complete memberships and histograms for both subsets are retained; these are finite subconfiguration queries, not separate geometric compilations.

The translation requests use T=10^200+183 and the vector (T,−T/7). They return exact rational coordinates for circle 418 and three of its points. A common translation preserves the radius, incidences and circle identities; the query does not generate intervening points or rebuild the geometry.

The continuation counters record 41 combinatorial branches, 20 point-incidence entries read, 11,360 subset-incidence tests and eight translated coordinates. New circumcenter tests, kernel pairs and anchor translations are all zero. The subset queries traverse the saved incidences; this traversal is real query work, not hidden compilation.

## Public reader methods

| Method | Result |
| --- | --- |
| `summary()` | Copy of the finite summary |
| `circlesPage(start=0,limit=32)` | Saved circle rows |
| `kernelPage(start=0,limit=32)` | Saved local centers and full pair witnesses |
| `point(id)` | Integer lattice coordinates and common scale |
| `pointCircles(id)` | Saved incident circle IDs |
| `circle(id)` | One complete circle row |
| `centerLookup({x,y,denominator})` | Exact saved center ID or null |
| `tripleSelect(rank)` | Global ranked triple, coordinates and full branch trace |
| `circleTripleSelect(id,rank)` | Ranked triple within one circle |
| `tripleRank(pointIDs)` | Qualifying circle and both ranks, or `qualifies:false` |
| `intersection(a,b)` | Points of the retained rectangle shared by two circles |
| `subsetProfile(pointIDs)` | All qualifying circles and triple counts for that subset |
| `translateCircle(id,shift)` | Exact center under a common rational translation |
| `translatePoint(id,shift)` | Exact translated point |
| `statistics()` | Opening and query counters |

An intersection query reports retained input points only. It does not solve for other real intersections of the two circles. In particular, neighboring center IDs 418 and 419 share no retained point; that answer is not a claim that their real circles are disjoint.

Input point subsets contain distinct IDs, but need not be sorted; duplicates throw. Triple ranking requires exactly three distinct IDs. Ranks may be decimal strings or nonnegative safe integers. A rank outside the selected family throws. Empty circle families are permitted by the general rectangular input; selection then has no valid rank.

Pages allow start in [0,total] and limits from zero through 128. A zero-sized page can retain its next offset. Rational shifts use `[[xNumerator,xDenominator],[yNumerator,yDenominator]]`, with positive denominators; numerators may be negative. Shift inputs are limited to 1,000 characters, and ordinary rank inputs to 100 digits. Output is exact decimal rational data.

Snapshots supplied as strings are limited to 16,000,000 characters. Construction limits are 500,000 local offset pairs, 2,000,000 anchor translations and 250,000 candidate centers. Exceeding a work cap throws rather than certifying an incomplete family. The API's larger admitted branches were source-inspected; the actual input remains Q=5 and 17×29.

## Source lineage, correction and custody

The geometric constructor ran once under source version 1.0.0, after its source and input were banked. Its complete result was banked in the producing call. Two complete circle shards were then serialized without repeating geometry.

The first reader attempt exposed a type-boundary bug at `tripleSelect("0")`: its internal BigInt residual was passed to a parser accepting decimal strings or safe Numbers. Eleven preceding literal-record query responses existed only inside that failed cell and were not banked. Their values are unavailable and have not been reconstructed or replayed. The disposition lists their method calls, with no invented outputs.

Version 1.0.1 changes that internal residual to a decimal string and allows the reader to open the version-1.0.0 snapshot. The geometric compiler body is unchanged apart from the version constant. The patched source was inspected, syntax-parsed and banked before a fresh reader continued only the unfinished queries. All 17 completed continuation responses were retained progressively and banked together in that call. The source fix was exercised by the actual first/middle/last selections and inverse-rank use, not by a new test suite or constructor replay.

| Item | Git blob identity |
| --- | --- |
| Original executed source, 12,666 bytes | 59c64891a40708c4158fcb5f5264d073ac8396ea |
| Published corrected source, 12,697 bytes | e0fc2bbf6d3f2f5131114cbd83e4a54beb4f2460 |
| Exact input, 418 bytes | 41e12abcc97dfc486c6fa1e2e1eefcbd55ede96a |
| Complete original construction, 577,050 bytes | c1881ab7a8ff1f166f4311a766dad458b562218c |
| First circle shard, 158,679 bytes | 98094459ff2ec16c856649cabd6e8a46d59ec98d |
| Second circle shard, 160,987 bytes | cc158602c701dd658b4cc822f873b2e171de2687 |
| Reader-attempt disposition, 1,386 bytes | df50cbf771eb9ae527de020cd3139f4a9b874d4f |
| Complete corrected continuation, 292,691 bytes | b4c36087107dc8f0ba83efb90828f14232d3fae1 |

The published files contain the complete constructor information, with the circle array split into the two named shards. Opening checks schema, exact center normalization/order, member and point-reference ranges, and the combinatorial triple prefix/count identities. It does not recalculate circumcenters or independently certify a forged kernel, membership table or completeness claim. Those depend on the retained constructor and the argument above.

## Problem statement and attribution

The completely read FormalConjectures statement defines a finite set of distinct real-plane points and counts distinct spheres of radius one containing at least three of them. Its `maxUnitCircleCount(n)` ranges over all n-point configurations, and Erdős 104 asks whether this maximum is o(n²). The source at https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/104.lean has decoded-content identity 8e9e218bbccbe5a82f798e101f8bbeacf739320d. It is annotated research open with a local placeholder; this is the read source's status, not an independent proof or complete literature assessment.

That source cites G. Elekes, *n points in the plane can determine n^(3/2) unit circles*, Combinatorica 4 (1984), 131, and H. Harborth and I. Mengersen, *Point sets with many unit circles*, Discrete Mathematics 60 (1986), 193–197, DOI 10.1016/0012-365X(86)90011-7. The latter's indexed publisher abstract and metadata were available, but the full publisher page returned 403 and was not retried. No result, proof or specific configuration from its unavailable full text is claimed to have been inspected.

OEIS https://oeis.org/A003829 records existing small maxima and cites those geometric sources. Its optional SVG illustration was unsupported by the source reader and remains unavailable; no coordinates were inferred from it and no small maximum was recomputed.

The local circumcenter formula and finite completeness argument are stated explicitly for this implementation, without a mathematical priority claim. This finite input supplies neither an upper bound for arbitrary 493-point configurations nor an answer to the asymptotic question. It does not establish a new unit-circle record or pursue a prize submission.
