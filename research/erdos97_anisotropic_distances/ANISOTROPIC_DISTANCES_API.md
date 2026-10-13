# Exact anisotropic distance arrangement

This package indexes every positive parameter λ for the nine labelled points p_i(λ)=(u_i√λ,v_i) copied from the identified Formal97 coordinates. It represents squared distances exactly as rational linear functions of λ. The complete result has 107 event values and 215 strata; within this family every vertex has at least two, and likewise at least three, equidistant other vertices exactly when λ=3. No parameter gives that property with four other vertices.

These are statements about this one declared family. The original λ=3 construction is credited prior material, and the four-neighbor question over all convex polygons remains separate.

## Source conventions and boundaries

The complete [FormalConjectures97](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/97.lean) read has blob `ee706b34f8dfd9b07c841d61b873d4fdeb4b60ea` (5,781 bytes). It asks whether every nonempty convex-independent finite set has a vertex without four other vertices at a common positive distance from that vertex. The radius may vary between vertices. The source marks this and its unspecified-k variant research open. It supplies the nine coordinate pairs used here and attributes their three-neighbor property to Danzer, with local placeholder proof. Its distinct solved variants credit Fishburn and Reeds with a 20-point common unit-distance construction and a cut-minimality theorem. None of the linked proofs was opened or reviewed.

Fishburn and Reeds, *Unit distances between vertices of a convex polygon*, Computational Geometry 2(2) (1992), 81–91, DOI [10.1016/0925-7721(92)90026-O](https://doi.org/10.1016/0925-7721(92)90026-O), distinguish Danzer's per-vertex replicated distance from their common distance one. That distinction and bibliography were read in the indexed primary abstract. The direct [publisher page](https://www.sciencedirect.com/science/article/pii/092577219290026O) returned 403 and remains held; no full-text, coordinate, proof or visual review is attributed to that paper. The full Formal97 read is the exact coordinate and four-neighbor statement authority.

## Literal input

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

The source parameter is λ=3. For every λ>0, this family is the image of those source points under the invertible affine map diag(√(λ/3),1). Such a map preserves convex independence. Thus the family inherits the source's convexity premise without recomputing a hull or validating the placeholder proof. The exact distance classification itself is a calculation on the literal coordinates and does not need that convexity premise. λ=0 is excluded because the affine map becomes singular; negative λ is outside this real-coordinate model.

The actual input blob is `e62816dd8b59612f99654f89eb393183e917a3d3`. The one executed source blob is `ba393907e4a7f21e41d1fbac844bee1dcaf09d8a` (7921 bytes). No prior accepted geometry table is an input, and no separate source-example proof run was performed. The original λ=3 appears as one event in the new arrangement rather than as an additional validation computation.

## Why finitely many strata cover all positive real parameters

For each unordered distinct pair {i,j}, the compiler stores

    F_ij(λ) = (u_i−u_j)^2 λ + (v_i−v_j)^2.

This is the positive squared Euclidean distance for λ>0. Distinct points remain distinct under the invertible scaling, so the self point never enters a positive-distance group. Squaring preserves equality of the nonnegative distances.

Two neighbors j,k have equal distance from a vertex i exactly when F_ij−F_ik is zero. This difference is linear with rational coefficients. It is either identically zero, constantly nonzero, or has exactly one rational root. The compiler retains all 252 such comparisons, including persistent, parallel and nonpositive-root cases; it does not discard a comparison merely because it creates no positive event.

The 135 positive root occurrences collapse to 107 distinct event values. Between consecutive events no nonpersistent equality can change. Grouping the eight distance values at one exact rational sample therefore determines all equal-distance fibers throughout that open real interval. Every event point is grouped separately, and the intervals adjacent to zero and positive infinity are included. This proves coverage of all positive real λ, even though the reader accepts rational parameter strings for concrete evaluation.

One equality is persistent: vertex A3 is equidistant from A1 and A2 for all λ. There are 36 unordered pair forms, 252 comparison records, 215 strata and 15,480 star-form evaluations in the one compiler run. No floating-point square root, approximate root, tolerance or numerical hull test is used.

## Exact finite result

Let m_i(λ) be the largest number of other vertices at one distance from vertex i, and let m(λ)=min_i m_i(λ). The saved superlevel sets are:

| Condition | Positive parameter locus |
|---|---|
| m(λ) ≥ 1 | (0,∞) |
| m(λ) ≥ 2 | {3} |
| m(λ) ≥ 3 | {3} |
| m(λ) ≥ 4,5,6,7 or 8 | empty |

Consequently m(λ)=3 at λ=3 and m(λ)=1 elsewhere in this family. This does not say every vertex has all distances distinct away from 3; the persistent A3 equality and individual event fibers are retained. It says at least one vertex has maximum multiplicity one there.

The known Danzer parameter is stratum 87, an event. Its nine maximum multiplicities are all three. At λ=1 and λ=4, the recorded maxima are [1,1,2,1,1,1,1,1,1]. The λ=3 groups have squared radii 12 on the A vertices, 259428/10927 on the B vertices and 379164/18529 on the C vertices. These values illustrate the varying-radius convention; they are not a common unit radius or a new Danzer construction.

## Saved representation and exact reassembly

The original complete snapshot has blob `7701fd784fd4d4b1d03ede8ca560f7ef2ee953ab` and 3980920 UTF-8 bytes. It is preserved losslessly by the manifest plus eleven consecutive stratum shards, rather than stored as a redundant monolithic file.

The manifest `anisotropic_index.json` has blob `2c13dfc0252f9f8a4d84dd7c8220c4fe1cf7f5f3`. It retains all input, forms, pair IDs, comparison certificates, events, superlevels and counters in `index_without_strata`, with an empty stratum array. Its shard directory fixes order, starting ID, count, bytes and blob for every shard.

| Shard | First stratum | Count | Blob |
|---|---:|---:|---|
| `strata_00.json` | 0 | 20 | `92b41a835adfdc9d3d3bfe4df1471c38ae3c017c` |
| `strata_01.json` | 20 | 20 | `022b2b9c9708d1f9be8c38dd8c67e92dce2a494a` |
| `strata_02.json` | 40 | 20 | `8af51d75d06be9b0b692ed1777817e52b98e9d65` |
| `strata_03.json` | 60 | 20 | `a1ce2ab11c0ed641b3ce61996973637b09a828ea` |
| `strata_04.json` | 80 | 20 | `ed5a1fdcb233c29b8ce673f09aa3a124b7364bee` |
| `strata_05.json` | 100 | 20 | `360543ea36920d88cc6f4cd96f724598c7895322` |
| `strata_06.json` | 120 | 20 | `47fc529748f1cc8ae328da644e5775a2f0d13fec` |
| `strata_07.json` | 140 | 20 | `af23667175c9c6512676ec5be86fab0781404e6a` |
| `strata_08.json` | 160 | 20 | `49bfb0fa70e95371dd54b10f3a1a5eaa86c07212` |
| `strata_09.json` | 180 | 20 | `31a4c7dcc748e01e44184813968396092941bd90` |
| `strata_10.json` | 200 | 15 | `bb518126da6ea80e031779220c961e0b7651c752` |

Concatenate the eleven literal `strata` arrays in manifest order and replace the empty array. The fresh reader did exactly this and obtained the original complete snapshot's text/blob identity; this was byte reassembly and identity checking, not geometry or classification replay.

## API

`anisotropic_distances.cjs` exports `buildIndex(input)` and `openIndex(snapshot)`. A constructor input contains 2 through 32 distinct coefficient pairs with rational-string coordinates. A rational string is an integer or signed integer numerator over a positive denominator, at most 4,096 characters; normalization uses BigInt gcd. Names are display metadata. The constructor does not check convexity or claim that arbitrary supplied points satisfy a source theorem.

`openIndex` checks the format and stratum count shape and trusts the saved certificate. It is not a hostile-file validator or a formal proof checker. Preserve the snapshot unchanged after opening. Queries use zero-based point, form, event and stratum IDs. Outward objects are copied.

| Operation | Request | Output |
|---|---|---|
| `summary` | none | Construction counts and global superlevel components |
| `locate` | `parameter` | Canonical rational and containing stratum |
| `event` | `index` | Event value and every creating equality ID |
| `eventsPage` | `start`, `limit` | Up to 1,000 event records |
| `stratum` | `id` | Complete saved sample profile and boundaries |
| `form` | `id` | Exact linear squared-distance coefficients |
| `comparison` | `id` | One complete equality comparison certificate |
| `distance` | `parameter`, `i`, `j` | Exact squared distance, including zero for self |
| `star` | `parameter`, `vertex` | All neighbor fibers and their evaluated squared distances |
| `profile` | `parameter` | All stars and the minimum of their maxima |
| `superlevel` | `threshold` | Saved all-vertex parameter locus for threshold 1 through n−1 |
| `condition` | distinct nonempty `vertices`, `threshold` | Parameter locus for those selected vertices |
| `witness` | `parameter`, `vertex` | One maximum fiber and its squared radius |

Concrete parameter queries require λ>0. Open intervals have `left_closed:false`, `right_closed:false`; a null right endpoint means positive infinity. Event singletons have equal endpoints and both closed. A component beginning at zero remains open. `condition` joins consecutive accepted strata and reports exact boundary inclusion; it scans saved records without recomputing equality events.

On an open stratum, the saved `sample_squared_distance` is a value at its sample only. It must not be treated as the distance at every λ in that interval. A `star`, `profile`, `distance` or `witness` query evaluates the stored linear form at the requested parameter. Group membership remains the saved one. A witness is selected in saved group order; no separate optimization or hull computation occurs.

## Actual saved-reader use

The fresh reader answered 44 queries after the manifest and every shard had been banked. Each response was banked before the next query. Its complete aggregate `saved_reader_queries.json` has blob `02c3cce34396140456a0060dd25432c458a43222` (187781 bytes). No compiler or reader error occurred.

The retained outputs include all 107 event records, profiles at 1,3,4, five selected strata, all nine λ=3 witnesses, three global superlevel queries and five selected-vertex conditions. Parameters 3−10^−80 and 3+10^−80 locate in strata 86 and 88, while 3 itself is in 87. The tiny parameter 10^−1000 lies in the first stratum. A witness at λ=10^1000 returns an exact rational squared radius using the saved coefficient form.

Vertex A3 has at least two equal-distance neighbors at every positive parameter. Its three-neighbor locus is exactly {3, 9897609/1965115, 22885/1452, 7180713/219098}. Requiring three neighbors at both A1 and A2 leaves only {3}; requiring four at all nine gives the empty set. These are selected-vertex family queries, not a statement about arbitrary convex point sets.

Fresh reader work comprises 139 event comparisons, 215 linear-form evaluations, 1,075 saved-stratum scans and 213 group-record reads. It performs no new pair-coefficient, comparison, root, event, stratum or source-coordinate construction. Query arithmetic is explicitly counted; reuse is not described as zero work.

## Usage

```javascript
const fs = require('fs');
const { openIndex } = require('./anisotropic_distances.cjs');
const manifest = JSON.parse(fs.readFileSync('anisotropic_index.json', 'utf8'));
const shards = manifest.shards.map(s => JSON.parse(fs.readFileSync(s.path, 'utf8')));
const snapshot = { ...manifest.index_without_strata, strata: shards.flatMap(s => s.strata) };
const reader = openIndex(snapshot);
reader.query({ op: 'condition', vertices: [2], threshold: 3 });
reader.query({ op: 'witness', parameter: '3', vertex: 0 });
```

This snippet is documentation, not another executed consumer. The actual 44 outputs delimit the reader evidence.

## Limits

The whole positive real parameter line is classified for these nine fixed coefficient pairs. This restricted infinite family is not the set of all convex polygons, does not resolve Erdős97, and does not reproduce the separate Fishburn–Reeds unit-distance construction. Convexity remains the explicitly identified source premise. No proof of an external theorem, present literature frontier, new extremal record, sponsor submission or novelty claim is made.
