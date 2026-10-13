# Rational circle chords and optimal anchored polygons

This package constructs one finite set of rational-distance points on the unit circle, saves every exact chord length, and indexes all maximum-perimeter polygons of a specified cardinality through a fixed anchor. Its actual input uses reduced rational parameters with denominator at most 10 and eight vertices per polygon.

The resulting 64 points give 2,016 unordered chords in 757 distance classes. Among all 553,270,671 eight-vertex subsets containing anchor 0, the maximum cyclic perimeter is exactly 2308/377. Four subsets attain it. The complete saved dynamic program contains 484 feasible states and 439 optimal arcs. Its separate reader records all four optimal polygons, four rank matches, and 31 complete query responses.

This is an exact finite optimization over the declared circular host with a required anchor. It is not optimization over arbitrary planar point sets, a dense subset of the plane, or a new rational-distance existence theorem.

## Primary attribution and scope

Makhul and Shaffaf, *On uniform boundedness of a rational distance set in the plane*, C. R. Acad. Sci. Paris, Ser. I 350 (2012), 121–124, define a rational-distance set by rational Euclidean distance between every two of its elements. Their introduction expressly states existence of a rational-distance set dense on the unit circle, separately from Ulam's question about density in the plane. The inspected passage supplies these definitions and the distinction; it does not give the literal parameter formula used below. That formula is derived here. Their discussion preserves rational distances under translations, rotations and rational uniform scaling; an arbitrary real scaling is not assumed.

Official primary PDF:
https://comptes-rendus.academie-sciences.fr/mathematique/item/10.1016/j.crma.2012.01.010.pdf

The complete 1,056-byte FormalConjectures file was separately read at content identity `392e05cb45d95707af0a60d6a7d9d003492a8859`:
https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/212.lean

It asks for a dense subset of the complex plane, identified with the real plane, having rational pairwise distances. Its research-open annotation and local placeholder are source metadata, not a proof or an independently audited current literature frontier. Circle-relative density would not imply plane density. This finite calculation proves neither kind of infinite density.

Rational coordinates or rational squared distances alone do not imply rational distances. The exact chord identity below is what supplies rational lengths for this host. No earlier accepted geometry, distance table, field construction or proof was replayed.

## Files and identities

| File | Role |
| --- | --- |
| `rational_circle_polygons.cjs` | Dependency-free CommonJS constructor and saved reader |
| `farey10_anchored8_index.json` | Complete points, chords, distance fibers and optimal suffix table |
| `saved_reader_queries.json` | All 31 reader responses, traces, four inverse comparisons and work |
| `RATIONAL_CIRCLE_POLYGONS_API.md` | Parameter derivation, recurrence, interface and finite scope |
| `README.md` | Entry point |

Executed source: `45c1d755b4ef237d02805419066cd71680d746b4`, 8,050 bytes. Complete input: `fd149fbb22db71fd4a3c807045166465f8e9f244`, 394 bytes; the same input fields are embedded in the snapshot.

The compact snapshot is 122,898 bytes with Git blob identity `230a6cb0c00631b1eccc15d01eaf550fdf343efb`. The full reader packet is 84,892 bytes with identity `95fa8e80b909b476f91419449e7108e7bb10f994`. Both texts include their terminal newline. Source and input were banked before the once-only construction; the complete snapshot was banked before opening the fresh reader. Each reader response was banked before the next query.

## Rational parameter construction

For an integer bound B, enumerate all reduced fractions t=a/b satisfying

- 1 <= b <= B;
- -b <= a < b;
- gcd(a,b)=1.

Sort these fractions by rational order. The half-open domain [-1,1) is essential: including both endpoints would duplicate the same circle point. The reduced-fraction condition gives one record per rational parameter; zero appears only as 0/1.

For each parameter define

U = b²-a², V = 2ab, Q = b²+a²,

u=U/Q, v=V/Q, and

P(t) = (u²-v², 2uv)
     = ((b⁴-6a²b²+a⁴)/Q², 4ab(b²-a²)/Q²).

Since U²+V²=Q², the vector (u,v) is a unit vector and P(t) also lies on the unit circle. All its coordinates are rational. For two parameters, the Euclidean chord length is

d(P(t_i),P(t_j)) = 2 |u_i v_j - v_i u_j|
                = 2 |U_i V_j - V_i U_j| / (Q_i Q_j).

To justify the length rather than only its square, write P_i as the square of the unit complex number u_i+iv_i. Expanding gives |P_i-P_j|²=4(u_i v_j-v_i u_j)²; the displayed nonnegative rational expression is therefore the Euclidean distance.

The intermediate vectors trace one half-open semicircle as t increases. Equivalently P(t) has angle 4 arctan(t) in [-π,π), strictly increasing. Thus the circle points are distinct and their parameter order is their cyclic order, starting at P(-1)=(-1,0). Any selected subset of at least three points is in convex position, and joining it in this order gives its inscribed convex polygon. Trigonometric quantities are used only to explain order; the implementation uses integer and rational arithmetic.

This derivation is elementary algebra for the stated interface, not a claim of priority for a rational-distance construction. The source passage cited above is credited for its established circle/plane distinction, not for a formula it did not display.

## Input and saved metric

`buildIndex(input)` requires `max_denominator` to be an integer from 1 through 16 and `vertices_per_polygon` to be an integer from 3 through the smaller of 16 and the constructed point count. A bound too small for that cardinality is rejected. Other input fields are retained as provenance.

Points receive IDs 0 through N-1 in increasing parameter order. ID 0 is always the fixed anchor P(-1)=(-1,0). Every rational is stored as a pair of decimal strings [numerator, denominator], reduced with positive denominator. Coordinates may be negative. Counts and ranks are decimal strings and use BigInt internally.

A point record stores `id`, `parameter`, `half_circle` and `point`. The intermediate unit coordinates in `half_circle` are retained to expose the exact construction. The complete actual points are also returned in the saved reader output.

Each unordered distinct pair i<j has a flat pair rank

i(2N-i-1)/2 + j-i-1.

The chord array follows that order. Equal-length pairs are grouped into `distance_classes`, ordered by exact rational length; each class stores its ID, distance and ascending pair ranks. `pair_class` maps every pair rank to its class. This groups numerical distances only; it does not quotient polygons or vertices by rotations, reflections or graph isomorphism. Self-distance zero is available as a query result but is not an unordered distinct-pair class.

The actual shortest class is 648/26245, with pair ranks 63 and 2015. The largest class is distance 2, containing 19 pairs. Distance from anchor 0 to point 32 is 2; from 0 to 1 it is 38/181.

## Complete anchored-polygon optimization

An admissible k-vertex polygon is an increasing sequence

0 = i_0 < i_1 < ... < i_(k-1) < N,

closed by the final edge back to 0. This represents an unordered vertex subset once in its circular order. It does not represent every ordering of those vertices, a self-intersecting tour, or a polygon whose vertex set omits the anchor. There are binomial(N-1,k-1) such subsets.

For a current vertex i and r further vertices to select, let F(i,r) be the greatest remaining path length, including the eventual closing edge to 0. Its feasible states have 0 <= r <= k-1 and r <= N-1-i. The recurrence is

F(i,0) = d(i,0),

F(i,r) = max over i<j<=N-r of [d(i,j)+F(j,r-1)].

Every increasing completion has one unique next vertex j. The displayed range is exactly the range leaving enough vertices for the remaining choices. These branches are exhaustive and disjoint. Descending evaluation in i makes every suffix state available before use. Exact rational comparison identifies all ties; no floating tolerance is used.

Each feasible state retains its reduced rational `cost`, decimal `count`, and ascending list of all optimal next-vertex `choices`. Its count is the sum of the saved child counts over precisely those choices; a zero-remaining state has count one. Infeasible entries are null. The root is state (0,k-1).

This dynamic program proves both the optimum and completeness of its maximizing family for the finite anchored input. It does not enumerate the binomial number of candidate polygons. The reader later expands only requested optimal selections.

The complete snapshot has format `rational-circle-polygon-index-v1` and fields `input`, `points`, `chords`, `distance_classes`, `pair_class`, `states`, `summary`, and `work`. The state array has N rows of length k, including null entries.

## Saved reader interface

`openIndex(snapshot)` returns `{query, stats}`. It checks the format and outer point/state lengths; it is a reader of trusted identified output, not a complete validator for hostile or independently supplied certificates. It does not reconstruct parameters, coordinates, chords, distance classes or optimal recurrence rows.

Example usage with the saved JSON already parsed:

```javascript
const {openIndex} = require("./rational_circle_polygons.cjs");
const reader = openIndex(snapshot);
reader.query({op: "summary"});
reader.query({op: "select", rank: "2"});
reader.query({op: "neighbors", id: 0, at_most: ["1","1"]});
```

These snippets document the interface; the actual execution evidence is the separate reader file.

| Operation | Fields | Result |
| --- | --- | --- |
| `summary` | none | Saved sizes, candidate count, optimum and number of optima |
| `point` | `id` | One complete saved point record |
| `points` | none | All point records |
| `chord` | `i, j` | Saved rational distance, pair rank and class ID |
| `distance_class` | `id` | One saved distance with every pair rank in its fiber |
| `state` | `i, remaining` | Saved suffix state or null |
| `select` | `rank` | An optimal polygon and complete branch trace |
| `rank` | `vertices` | Optimal-family rank and branch trace |
| `page` | `start, limit` | Requested consecutive optimal selections |
| `evaluate` | `vertices` | Exact perimeter from saved chords, edge list and comparison to saved maximum |
| `neighbors` | `id, at_most` | All other vertices within the inclusive rational chord threshold |

Vertex and class IDs are bounded integers. The state remaining count is an integer from 0 through k-1. Ranks and page starts are nonnegative canonical decimal strings of at most 4,096 characters. Page limits range from 0 through 1,000. A page starting exactly at the family count is empty; larger starts and out-of-family selection ranks are rejected.

For `rank` and `evaluate`, the vertices must have exactly k entries, start with 0, and strictly increase. Ranking additionally requires that each next vertex belongs to the corresponding saved optimal choices. A feasible nonoptimal polygon may be evaluated but has no rank in the optimal family.

Ranks are zero-based lexicographic ranks of the increasing optimal vertex-ID sequences. At each step selection subtracts saved child counts in ascending choice order. The traces record the current vertex, remaining cardinality, next vertex and skipped count; selection also records residual rank.

The `evaluate` operation performs fresh rational additions of saved chord values. Its comparison to the saved maximum is likewise fresh query arithmetic; it does not execute the optimal recurrence. `neighbors` scans saved chords with exact rational comparisons and excludes the vertex itself. Thresholds are pairs of integer strings with positive denominator, normalized by the reader; a negative threshold returns no neighbors.

For `chord(i,i)`, distance is zero and pair/class IDs are null. The saved metric classes themselves contain only positive distances between distinct points.

## Actual optimal family

The maximum perimeter is 2308/377 for all four listed vertex sets.

| Rank | Increasing vertex IDs |
| ---: | --- |
| 0 | [0,11,18,26,32,38,45,53] |
| 1 | [0,11,18,26,32,38,46,53] |
| 2 | [0,11,19,26,32,38,45,53] |
| 3 | [0,11,19,26,32,38,46,53] |

The optional positions are two distinct bottom points and two distinct top points:

| ID | Parameter | Circle coordinates |
| ---: | --- | --- |
| 0 | -1 | (-1,0) |
| 11 | -2/3 | (-119/169,-120/169) |
| 18 | -3/7 | (-41/841,-840/841) |
| 19 | -2/5 | (41/841,-840/841) |
| 26 | -1/5 | (119/169,-120/169) |
| 32 | 0 | (1,0) |
| 38 | 1/5 | (119/169,120/169) |
| 45 | 2/5 | (41/841,840/841) |
| 46 | 3/7 | (-41/841,840/841) |
| 53 | 2/3 | (-119/169,120/169) |

The saved root has choice [11]. Its next state (11,6) has cost 2018/377 and choices [18,19]. State (32,3) has cost 1154/377 and two completions. The terminal state (63,0) has cost 38/181; (63,1) is infeasible.

The reader independently summed saved chord values for all four optimal polygons and obtained equality to the saved optimum. It also evaluated [0,1,2,3,4,5,6,7], obtaining 324331436360/327839275777, and [0,8,16,24,32,40,48,56], obtaining 12972/2125. Both compare strictly below the maximum.

Inclusive distance-one neighborhoods contain 26 other points at anchor 0 and 16 at point 32. Threshold zero gives no other point at anchor 0; threshold two gives all 63. These are exact finite-host neighborhoods, not statements about the whole circle.

## Actual work and evidence boundary

The constructor's measured counters were:

| Counter | Value |
| --- | ---: |
| parameter_candidates | 110 |
| gcd_checks | 110 |
| points | 64 |
| chords | 2,016 |
| distance_sort_comparisons | 17,980 |
| states | 484 |
| candidate_extensions | 12,824 |
| rational_additions | 12,824 |
| objective_comparisons | 12,404 |
| optimal_arcs | 439 |

The separate reader retained 31 responses, all four optimal polygons and four exact selection/rank comparisons. It performed six requested perimeter evaluations, including the two nonoptimal examples.

| Reader counter | Value |
| --- | ---: |
| queries | 31 |
| state_reads | 127 |
| choice_visits | 80 |
| chord_reads | 304 |
| point_reads | 64 |
| distance_comparisons | 258 |
| rational_additions | 48 |
| selection_steps | 42 |
| rank_steps | 28 |

Counters refer to the named instrumented paths, not every arithmetic instruction, allocation or copy. Rational normalization, table copying and some input checks are not separately counted. The reader file retains `outputs`, `comparisons`, final `work`, source/snapshot pins and the explicit no-reconstruction declaration.

The once-only construction and saved queries establish this finite metric and anchored optimum. They supply no infinite density, unrestricted planar extremality, unrestricted anchor optimum, current global solution or mathematical priority claim.
