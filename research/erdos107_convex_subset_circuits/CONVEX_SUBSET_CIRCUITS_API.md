# Convex-subset and empty-polygon circuits

This package gives a complete finite index for one new 15-point rational host. All 455 orientation determinants are nonzero. The 538 triangle-containment circuits classify its 32,768 labelled subsets: 2,589 are convex-independent, and 687 are empty convex polygons of size at least three. The largest convex subset has size nine and is unique; the largest empty polygons have size seven and there are seven of them.

## Sources and precise scope

The complete [FormalConjectures107](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/107.lean) read has blob `d9c5299bf79dfe703f17f41c238421f0a11b0abf` (6,379 bytes). Its main Erdős–Szekeres question asks for the least N forcing a convex n-gon in every N-point real-plane set with no three collinear, and conjectures 2^(n−2)+1 for n≥3. It marks the main assertion research open and records separate existence and quantitative bound variants. Those annotations are not a proof audit or a current literature-frontier claim; no linked external proof was opened and no local proof was executed.

Yatao Du and Ren Ding, *On maximum area polygons in a planar point set*, Elemente der Mathematik 63 (2008), 88–96, give the conventions used here on printed page 88 of the successfully read [publisher PDF](https://ems.press/content/serial-article-files/45346). The host is in general position; a selected set is in convex position when its points are the polygon's vertices. An empty polygon additionally has no host point in the interior of its convex hull. These are different conditions. This definition source supplies no general-position assertion for the new host and no Erdős107 bound.

The index classifies labelled subsets of one fixed host, not all planar configurations, isomorphism classes or extremal values of the unrestricted function. Empty polygons are an additional query family and must not be silently substituted for the ordinary convex polygons in the main problem.

## Exact new host and lineage

The first nine rational coefficient pairs are literal input data retained from [Commons #31686](https://github.com/woahwhattheheck/commons/pull/31686), input blob `e62816dd8b59612f99654f89eb393183e917a3d3`, and `research/erdos97_anisotropic_distances/anisotropic_index.json`, blob `2c13dfc0252f9f8a4d84dd7c8220c4fe1cf7f5f3`, field `index_without_strata.input.points`. That source attributes the nine-point construction to Danzer through Formal97. The six I-labelled pairs below are newly declared input points; they are not attributed to Danzer or Du–Ding.

| Index | Label | u | v |
|---:|---|---|---|
| 0 | A1 | -1 | -1 |
| 1 | A2 | 1 | -1 |
| 2 | A3 | 0 | 2 |
| 3 | B1 | -8991/10927 | -26503/10927 |
| 4 | B2 | 17747/10927 | -235/10927 |
| 5 | B3 | -8756/10927 | 26738/10927 |
| 6 | C1 | -10753/18529 | -44665/18529 |
| 7 | C2 | 27709/18529 | 6203/18529 |
| 8 | C3 | -16956/18529 | 38462/18529 |
| 9 | I1 | 1/10 | 1/7 |
| 10 | I2 | 2/11 | -1/13 |
| 11 | I3 | -3/17 | 1/19 |
| 12 | I4 | 4/23 | -2/29 |
| 13 | I5 | -5/31 | -3/37 |
| 14 | I6 | 6/41 | 4/43 |

The actual host is (u,v). Every positive anisotropic embedding (√λ u,v), including the source λ=3 embedding of the original nine points, has the same orientation signs because every determinant is multiplied by √λ>0. Convexity and full-host emptiness therefore have the same classification throughout this positive family. The determinant values returned by the reader refer to the rational (u,v) host, not to an unstated rescaled area.

The new input blob is `34f9e8522b27c66c48a01ad926619b2bc9f6608a`. The original E97 pair distances, equality events, strata and reader are not used or recomputed. General position is established directly for the extended host rather than inferred from the old nine-point premise.

## Certificate and completeness argument

The compiler clears all coordinate denominators using a positive common L. It saves the integer coordinates and, for every ordered-increasing triple i<j<k, the signed integer determinant numerator. Division by the saved L² gives its rational determinant. None of the 455 numerators is zero.

For each four-point support, the compiler examines each candidate point against the triangle of the other three. A point is strictly inside a triangle exactly when the three oriented-edge signs agree with the triangle's orientation. All signs come from the complete saved triple table. The resulting 538 records specify a point, its containing triangle and their four-point support. General position removes boundary and collinear ambiguity.

An `interior_masks[S]` bit is set at p precisely when some triangle of S contains p. Each circuit's triangle contributes its point bit to every superset of that triangle, whether or not p is selected. This uses 2,203,648 superset bit updates. There are 5,460 candidate point/triangle checks and 16,717 saved-orientation lookups; short-circuit evaluation explains why the lookup count is below four times the candidate count.

For at least three noncollinear selected points, triangulate their convex hull. A host point in its interior lies in a triangle of selected vertices; general position prevents it from lying on a triangulation diagonal. Thus the saved triangle-containment predicate equals interior membership in the selected hull. In particular, a selected point is nonextreme exactly when a triangle of the other selected points contains it.

Consequently a subset S is convex-independent exactly when `S & interior_masks[S]` is zero. It is an empty convex polygon exactly when it is convex, has at least three points, and `interior_masks[S]` itself is zero. A nonzero selected interior bit supplies a nonconvexity witness; a nonselected interior bit supplies a nonempty-polygon witness. These witness roles are retained separately.

Empty, singleton and two-point subsets count as convex-independent in the finite API. They are not polygons and are excluded from the empty-polygon family. The full host is fixed for every emptiness query; excluding a vertex from a candidate polygon does not remove it from the host.

## Exact counts

| Selected size | Convex subsets | Empty convex polygons |
|---:|---:|---:|
| 0 | 1 | 0 |
| 1 | 15 | 0 |
| 2 | 105 | 0 |
| 3 | 455 | 234 |
| 4 | 827 | 249 |
| 5 | 729 | 148 |
| 6 | 352 | 49 |
| 7 | 92 | 7 |
| 8 | 12 | 0 |
| 9 | 1 | 0 |
| 10 | 0 | 0 |
| 11 | 0 | 0 |
| 12 | 0 | 0 |
| 13 | 0 | 0 |
| 14 | 0 | 0 |
| 15 | 0 | 0 |

The unique maximum convex subset has mask 511, the original nine vertices 0 through 8. It contains all six new points in its interior, so it is not empty. The seven maximum empty polygons have masks [1243,2413,10601,13387,16822,17332,29257]. These are finite-host maxima, not new bounds on the Happy Ending function.

## Module and ordering

`convex_subset_circuits.cjs` exports `buildIndex(input)` and `openIndex(snapshot)`. The generic constructor accepts 3 through 17 rational points, with each coordinate supplied as an integer or signed numerator over a positive denominator, at most 512 characters. It rejects any zero triple determinant. The actual run used 15 points and is the only compiler execution recorded here.

`openIndex` checks format and basic array sizes and trusts the saved mathematical certificate. It is not a hostile-input validator or independent proof checker. Keep the snapshot unchanged after opening. Query objects are copied outward.

Subsets use unsigned integer masks: bit i selects labelled point i. Family order is increasing numerical mask, not lexicographic vertex-list order or cyclic polygon order. Counts retain labels and do not quotient rotations, reflections or other isomorphisms.

| Query | Fields | Output |
|---|---|---|
| `summary` | none | Histograms and finite maxima |
| `point` | `index` | Original rational and cleared coordinates |
| `orientation` | three distinct `vertices` | Saved determinant with requested permutation sign |
| `circuit` | `id` | One point-in-triangle certificate |
| `classify` | `mask` | Size, convexity, emptiness, interior points and a witness when needed |
| `count` | optional `condition` | Exact family size under the condition |
| `page` | `condition`, `start`, `limit` | Up to 1,000 increasing masks |
| `select` | `condition`, `rank` | Selected mask and classification |
| `rank` | `condition`, `mask` | Rank, or null when absent |

A condition has `mode:'convex'` or `mode:'empty'`, optional `size`, and integer `include` and `exclude` masks. Defaults are convex mode, all sizes and no fixed bits. Include and exclude must be disjoint. Size may be null for no restriction. Empty mode always refers to polygons empty relative to all 15 host points.

## Actual reader

The separate reader opened the banked snapshot and produced 41 complete outputs, each banked before the next request. They include the full maximum-empty family, three selected maximum empty polygons, the unique maximum convex subset, several orientation permutations, containment witnesses and conditional counts. Four saved select/rank pairs return the same rank.

The empty pentagons that include I1 and exclude I2 number 33. No convex subset contains all six new I vertices. Mask 511 is absent from the empty-heptagon family and therefore has null rank there. The selected empty-heptagon ranks 0,3,6 yield masks 1243,13387,29257.

Reader counters record 35,508 saved-family row scans, 540 circuit-row scans and 20 saved-mask lookups. They are scoped counters, not an accounting of every JavaScript operation: orientation row searches, sign changes, bit decoding and response copying are additional query work. No determinant, containment circuit, superset propagation or all-subset classification is rebuilt. No compiler or reader error occurred.

## Identities and usage

| Artifact | Git blob | Bytes |
|---|---|---:|
| Executed source | `44692ad6fba0457ec39a24dc2c18019698b50938` | 6990 |
| Complete index | `77cadfde0fb42f81a23a744b601467db7b812cc3` | 801332 |
| Complete reader | `6ed28aa7b6aed3abb5756e234cac57bdf57621dd` | 19137 |

```javascript
const fs = require('fs');
const { openIndex } = require('./convex_subset_circuits.cjs');
const index = JSON.parse(fs.readFileSync('fifteen_point_circuits.json', 'utf8'));
const reader = openIndex(index);
reader.query({ op: 'count', condition: { mode: 'empty', size: 5, include: 512, exclude: 1024 } });
reader.query({ op: 'select', condition: { mode: 'empty', size: 7 }, rank: 3 });
```

This documentation example is not a second executed consumer. The retained responses delimit actual reader evidence.

No universal threshold, latest quantitative bound, construction priority or prize claim is made. The result is a reusable exact finite-host index, with distinct convexity and full-host emptiness semantics.
