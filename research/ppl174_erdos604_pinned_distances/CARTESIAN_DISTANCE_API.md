# Exact Cartesian pinned-distance index

The module compiles all pinned squared-distance profiles of a finite Cartesian product of integer coordinate sets. It shares equal one-dimensional coefficient profiles, retains every convolution term and target reference, and exposes distance and circle-point navigation from a saved index.

The actual input is
\[
P=\{0,\ldots,16\}\times\{0,\ldots,28\},
\qquad |P|=493.
\]
It has **87 distinct distances at its unique center and 293 at each of its four corners, including zero**. The complete coefficient data establishes these finite counts. A separate support argument below identifies all minimizing and maximizing pins for every full rectangular integer grid.

## 1. Problem convention and sources

Jonathan Passant's author presentation, [*Configurations and Erdős-Style Distance Problems*](https://vlasiuk.com/PDseminar/pdf/passant.pdf), Point Distribution Webinar, July 21, 2021, displays on slide 7 the function
\[
f_{\mathrm{pin}}(N)
=\min_{\substack{P\subset\mathbb R^2\\|P|=N}}
  \max_{x\in P}\bigl|\{\,|x-p|:p\in P\,\}\bigr|.
\]
The displayed target set includes \(p=x\), so its distance set includes zero. The module follows that convention. It also reports positive-distance counts and permits callers to omit zero from distance ranking and selection. These two counts always differ by one for a nonempty finite set of distinct real-plane points.

The general problem concerns a large pinned-distance count guaranteed for every finite real-plane configuration. A Cartesian product is a restricted class of configurations. The square-grid example and the general pinned-distance question predate this implementation; the presentation is an author source for the displayed convention, not a claim that it is Erdős's original publication.

[Pham, Senger and Tran, *Distribution of pinned distance trees in the plane \(F_p^2\)*](https://viasm.edu.vn/Cms_Data/Contents/viasm/Media/2022/Tienanpham2022/Preprint_2263.pdf), November 2, 2022, Remark 1.1 on printed page 3, explicitly distinguishes the real-plane pinned problem from the unpinned result. It describes Guth–Katz's unpinned \(N/\log N\) bound and Katz–Tardos's \(N^{0.8641\ldots}\) pinned bound as the then-current real-plane result. That is a dated source statement, not an independently established best bound in October 2026. The paper's positive-characteristic theorems do not supply a theorem about this ordinary Euclidean input.

The bounded source lookup did not establish a solution of the full near-linear pinned target or an exhaustive current frontier. This package makes no such assertion, no new extremal-record claim, and no claim of priority for the elementary Cartesian factorization used below.

## 2. Coefficient factorization

Let \(X,Y\subset\mathbb Z\) be finite nonempty sets, with their coordinates sorted increasingly. For a pin \((x_i,y_j)\), define
\[
A_i(u)=\#\{x\in X:(x-x_i)^2=u\},\qquad
B_j(v)=\#\{y\in Y:(y-y_j)^2=v\}.
\]
All keys \(u,v\) are nonnegative integers. The exact squared-distance multiplicity is
\[
C_{ij}(s)=\#\{(x,y)\in X\times Y:
                 (x-x_i)^2+(y-y_j)^2=s\}
        =\sum_{u+v=s} A_i(u)B_j(v).
\]

To see the identity, place a target point into the unique pair of buckets determined by its two squared coordinate differences. Each bucket pair contains exactly the product of its two axis multiplicities. Distinct bucket pairs are disjoint, and every target belongs to one pair. Grouping those pairs by their sum gives the formula. Therefore
\[
\sum_s C_{ij}(s)=|X||Y|,\qquad C_{ij}(0)=1.
\]
The number of distinct distances is the number of positive coefficients, not the sum of their multiplicities. Squaring preserves both equality and increasing order of nonnegative Euclidean distances, so no square-root approximation is needed.

In one dimension, a positive squared distance from a fixed coordinate has at most two target coordinates. Axis coefficients consequently lie in \(\{1,2\}\), except that absent keys are omitted, and the zero coefficient is exactly one. Convolution term weights are at most four. These bounds also explain the small exact multiplicity fields in the retained format.

### Sharing profiles without losing point identities

For each axis the compiler computes \((x_j-x_i)^2\) once for every unordered coordinate pair \(i<j\). It retains that value with both endpoint indices and supplies the corresponding target reference to each endpoint's buckets. Self references supply the zero buckets.

Two pins share an axis profile only when their entire ordered lists of squared-distance/multiplicity pairs agree. The implementation uses an exact serialized list as a map key; it does not identify profiles by a probabilistic hash or merely by their support. Per-pin target lists remain separate. Thus pins with the same coefficient vector can share convolution work while circle queries still return their own target points.

If there are \(r_X\) distinct x-axis profiles and \(r_Y\) distinct y-axis profiles, only \(r_Xr_Y\) profile-pair convolutions are compiled. This package does not additionally merge different profile pairs whose final two-dimensional coefficient vectors happen to agree. Every pair retains its own provenance.

## 3. Exact extrema for full rectangles

For positive integers \(m,n\), consider
\[
P_{m,n}=\{0,\ldots,m-1\}\times\{0,\ldots,n-1\}.
\]
At pin \((i,j)\), put
\[
U_i=\max(i,m-1-i),\qquad
V_j=\max(j,n-1-j).
\]
The squared-distance support is exactly
\[
S(U_i,V_j)=
\{u^2+v^2:0\le u\le U_i,\ 0\le v\le V_j,\ u,v\in\mathbb Z\}.
\]

Indeed, the absolute differences on the first axis fill every integer from zero through \(U_i\), and the second axis similarly fills zero through \(V_j\). The Cartesian product permits every combination.

The supports satisfy
\[
U\le U',\ V\le V'
\quad\Longrightarrow\quad S(U,V)\subseteq S(U',V').
\]
Their largest elements are \(U^2+V^2\). If at least one of the two coordinate inequalities is strict, this largest element strictly increases; the inclusion is then proper. Hence the number of distinct distances strictly increases under a strict coordinatewise enlargement.

Every corner has \((U_i,V_j)=(m-1,n-1)\), which dominates every pin. A noncorner has at least one strictly smaller coordinate maximum. **Exactly the corners maximize the distinct-distance count.**

The minimum possible coordinate maxima are
\[
U_{\min}=\left\lceil\frac{m-1}{2}\right\rceil,\qquad
V_{\min}=\left\lceil\frac{n-1}{2}\right\rceil.
\]
They are attained exactly at central coordinate choices
\[
i\in\left\{
\left\lfloor\frac{m-1}{2}\right\rfloor,
\left\lceil\frac{m-1}{2}\right\rceil
\right\},
\]
and the analogous choices for \(j\), treating these as sets. Any other pin strictly enlarges at least one maximum. **Exactly those central pins minimize the distinct-distance count.**

The set interpretation removes duplicate endpoint or center choices when a side has length one or when a center coordinate is unique. It also permits the corner and central sets to coincide, as they do for a \(2\times2\) rectangle. This proof covers degenerate rectangular sides without an exception. Omitting zero subtracts one from every pin count and leaves the extremizing pins unchanged.

This corollary uses full consecutive integer axes. The public coefficient API also accepts sparse and signed integer axes; no corner/center conclusion is asserted for that broader class.

## 4. Complete new finite input and result

The input identifier is `ERDOS604-CARTESIAN-20261004-7CA6/grid17x29`. Its two supplied coordinate arrays are retained literally. No point set, pair ledger, cube, projection, or grid histogram from the earlier rich-line work was consumed.

| Quantity | Actual retained result |
| --- | ---: |
| Distinct points | 493 |
| Axis pins | 17 + 29 |
| Distinct axis profiles | 9 + 15 |
| Equal axis profiles reused | 22 |
| Unordered one-dimensional squared differences | 542 |
| Axis target references, including self references | 1,130 |
| Profile-pair convolutions | 135 |
| Complete squared-distance coefficient rows | 23,764 |
| Complete convolution term records | 38,610 |
| Minimum distinct distances, including zero | 87 |
| Minimum positive distances | 86 |
| Maximum distinct distances, including zero | 293 |
| Maximum positive distances | 292 |

The only minimizing pin is \((8,14)\), point ID 246. Its maximum squared radius is 260. The maximizing pins are \((0,0),(0,28),(16,0),(16,28)\), with point IDs 0, 28, 464 and 492; their maximum squared radius is 1,040. The saved summary retains all extremal pins, their source profile-pair IDs, and the full histogram of pin counts by number of distinct distances.

The extremal-function direction matters. Because \(f_{\mathrm{pin}}\) minimizes over all configurations, this particular configuration establishes
\[
f_{\mathrm{pin}}(493)\le293
\]
under the displayed convention including zero. With zero omitted, the corresponding upper bound is 292. Neither number is asserted to be the global minimum, a record, or a lower bound valid for every 493-point configuration.

### Queries from the saved index

A fresh module context opened the retained snapshot and made eight public query calls. It did not call the compiler.

| Query | Result |
| --- | --- |
| Center pin summary | 87 distances including zero, 86 positive |
| Corner pin summary | 293 distances including zero, 292 positive |
| Center positive-distance rank 43 | Squared distance 101, multiplicity 4 |
| Rank of that squared distance | 43 with zero excluded |
| Center disk through squared radius 65 | 213 points including the pin |
| Center circle at squared radius 65 | All 16 points returned |
| Corner circle at squared radius 65 | All 4 points returned |
| Center positive-distance page, ranks 40–51 | Twelve exact rows retained |

The positive-distance selection uses the upper middle zero-based rank, \(\lfloor86/2\rfloor=43\). The accompanying page has squared distances
\[
97,98,100,101,104,106,109,113,116,117,121,122.
\]
Their multiplicities are respectively
\[
4,4,10,4,4,4,4,8,4,4,2,4.
\]

The center circle consists of the signed coordinate displacements obtained from \((1,8)\), \((8,1)\), \((4,7)\), and \((7,4)\). The data retains all 16 actual target coordinates in increasing point-ID order, together with their saved convolution and axis-term references. The corner query returns \((1,8),(4,7),(7,4),(8,1)\), again with complete references. These point pages materialize saved incidences; they are not a second coordinate-distance computation.

## 5. Public API

The dependency-free CommonJS module exports:

- `compileCartesianDistanceIndex(request)`;
- `openRetainedCartesianDistanceIndex(snapshot)`;
- the frozen `CARTESIAN_DISTANCE_LIMITS` object.

A compile request contains `source_id`, `x_coordinates`, and `y_coordinates`. Coordinates may be canonical signed decimal strings, BigInts, or safe integer Numbers. Strings with leading zeros, plus signs, decimal fractions, or a noncanonical negative zero are rejected. Numeric negative zero normalizes to zero. Each axis is sorted and deduplicated; input-record multiplicity does not create repeated points.

A successful compile returns `{status: "COMPLETE", index}`. The index is an immutable method object, and returned records are copied or freshly constructed so callers do not receive mutable references to the stored index.

Pins use two zero-based indices into the normalized coordinate arrays, not raw coordinate values. If the y-axis has length \(n\), the point ID is `x_index * n + y_index`. Numeric increasing point-ID order is also the order of circle-point pages.

| Method | Meaning |
| --- | --- |
| `summary()` | Saved global summary, coordinate arrays, source ID and extrema |
| `pinSummary([i,j])` | That pin's profile ID, distinct counts, point count and maximum squared distance |
| `selectDistance(pin, rank, options)` | Exact distinct-distance row at a zero-based rank |
| `rankDistance(pin, squaredDistance, options)` | Rank of an exact squared-distance value |
| `pageDistances(pin, startRank, limit, options)` | Bounded page in increasing distinct-distance order |
| `countPointsThrough(pin, squaredDistance)` | Number of target points within the inclusive squared radius, including the pin |
| `pagePointsAtDistance(pin, squaredDistance, startRank, limit)` | Target-point page on one exact circle, with retained term references |
| `sourceProfile(pin)` | Complete copied coefficient vector and convolution terms for the pin's profile pair |
| `snapshot()` | Complete JSON-compatible index state |
| `work()` | Copied construction, structural-read and query counters |

For distance navigation, `options.include_zero` defaults to `true`. Setting it to `false` changes only the ranked sequence by omitting its first entry. Circle and disk queries retain their ordinary geometric meaning; the disk always includes the pin for a nonnegative radius. All squared-distance arguments are exact nonnegative integers, never unsquared radius approximations.

Selection returns `FOUND` or `OUT_OF_RANGE`. Ranking returns `FOUND`, `ABSENT`, or `EXCLUDED_ZERO`. A circle with an absent squared distance returns `ABSENT` with no points. Pages include their next rank and whether more entries remain; a start beyond the end produces an empty page. Rank inputs accept exact integer forms under the documented digit cap. Found distance ranks and multiplicities are small Number integers; page cursors are decimal strings.

### Direct saved-data use

The complete consumer file is `grid17x29_pinned_distances.json`. Its index state is at `construction.snapshot`.

```js
const {
  openRetainedCartesianDistanceIndex
} = require("./cartesian_distance_index.cjs");
const saved = require("./grid17x29_pinned_distances.json");

const index = openRetainedCartesianDistanceIndex(
  saved.construction.snapshot
);

const result = index.pagePointsAtDistance([8, 14], "65", "0", 128);
const selected = index.selectDistance(
  [8, 14], "43", { include_zero: false }
);
```

This is also directly usable in the connected V8 runtime: evaluate the supplied CommonJS source with a fresh `module.exports` object, parse the retained JSON, and call the same public methods. The actual run used that route; the displayed CommonJS file-loading example is usage documentation, not a claimed native-process execution.

## 6. Retained format and structural loader

The index schema is `commons.erdos604.cartesian_distance_index/v1`. It contains:

- each normalized coordinate array;
- every unordered axis pair `[first_index, second_index, squared_difference]`;
- each distinct axis profile's `[squared_difference, multiplicity]` rows and all pins that use it;
- for every axis pin, the complete target-index list for each profile term;
- every ordered x-profile/y-profile pair, its represented pin count, full coefficient vector, and complete convolution terms;
- the saved summary, including all extremal pins and the distribution of distinct-distance counts.

A profile pair's `terms_flat` array has stride four:
`[x_term_index, y_term_index, coefficient_row_index, product_weight]`.
Terms occur in lexicographic x-term/y-term order, covering every pair exactly once. The referenced coefficient row stores the summed squared distance and final multiplicity. The complete file has 38,610 such records, represented by 154,440 small integers; no sampled or truncated term list is substituted.

The loader copies the supplied state and checks bounded structural consistency. This includes canonical and sorted integer fields; complete lexicographic axis-pair reference coverage; profile/pin membership; target partitions and self references; complete profile-pair and convolution-term index coverage; positive multiplicity ranges and total coefficient mass; and summary dimensions and extremal-pin identities.

Those checks have an explicit limit. The loader does **not** recompute a squared coordinate difference, prove equality of shared coordinate profiles, verify every convolution sum or product-weight identity, accumulate each bin again, or recalculate the saved extrema. It does not authenticate the source or certify that arbitrary caller-supplied records are mathematically correct. The retained file and its implementation identity are the premise for read-only use.

The reader lazily builds an increasing BigInt key array, cumulative coefficient counts, and bin-to-term references for a requested profile. A circle query expands only the target lists referenced by that bin and sorts the resulting point IDs. It also checks that the materialized point count agrees with the stored coefficient. This is a local structural consistency check; it is not a fresh evaluation of coordinate-distance equations.

## 7. Bounds and work accounting

The public limits are:

| Resource | Bound |
| --- | ---: |
| Raw entries per axis | 64 |
| Distinct coordinates per normalized axis | 32 |
| Decimal digits per coordinate, excluding sign | 32 |
| Decimal digits per squared-distance argument or saved key | 66 |
| Profile pairs | 1,024 |
| Total convolution terms | 131,072 |
| Page size | 128 |
| Decimal digits in query rank inputs | 16 |
| Source-ID characters | 512 |

Both normalized axes must be nonempty. Thus a complete input has at most 1,024 points. A coordinate difference has magnitude below \(2\cdot10^{32}\), and the sum of two squares is below \(8\cdot10^{64}\), within the squared-distance field cap. BigInt carries the coordinate and squared-distance arithmetic. Axis multiplicities are at most two, term weights at most four, and coefficient counts at most 1,024; their Number arithmetic is exact.

After compiling the axes, the compiler computes the required number of profile pairs and terms. If the convolution budget would be exceeded, it returns `CAP_STOP` with the reason, required counts, complete retained axes, work counters, and a null index. It performs no two-dimensional convolution in that case. A cap stop is an unfinished computation under this implementation budget, not a mathematical impossibility or a zero-distance result.

For axes of lengths \(m,n\), axis construction uses
\(\binom m2+\binom n2\) squared differences and retains \(m^2+n^2\) target references. If distinct x-axis profiles have term counts \(a_1,\ldots,a_{r_X}\) and y-axis profiles have counts \(b_1,\ldots,b_{r_Y}\), the convolution term count is exactly
\[
T=\left(\sum_i a_i\right)\left(\sum_j b_j\right).
\]
Coefficient bins are then sorted within each profile pair. This is shared-axis work, not a claim of a general subquadratic algorithm on arbitrary planar point sets. The module has no loop evaluating all planar point pairs.

For the actual rectangle, the distinct x-profile term counts sum to 117 and the y-profile term counts to 330, giving \(T=38{,}610\). The single compile took 50 ms in the observed connected runtime.

Opening its snapshot took 35 ms and structurally read 542 axis-pair rows, 1,130 target references, 447 axis-profile terms, 23,764 coefficient rows and 38,610 convolution terms. The eight-query batch took 1 ms. It lazily indexed two profiles containing 380 coefficient rows and 628 convolution terms, used 27 binary-search steps, and materialized the 20 returned circle-point records. Its compiler, squared-difference and convolution-construction counters remained zero. Index construction and prefix addition are real reader work; zero geometry recomputation does not mean zero arithmetic.

These times are individual environment observations, not a statistical benchmark or a measured comparison against an alternative implementation. No alternative planar-pair evaluator was run.

## 8. Execution boundary

The retained execution consists of one new geometry compile, one fresh saved-index opening and the eight stated query calls. Complete output is retained. No predecessor geometry, published source example, or accepted enumeration was rerun.

Other public branches—signed or sparse axes, duplicate normalization, singleton axes, cap stops, malformed inputs, absent radii, the `EXCLUDED_ZERO` response, out-of-range ranks, cache reuse and source-profile export—were inspected in the source where not exercised by the actual consumer. There was no synthetic verification suite and no claim that every branch ran.

The source file is the exact implementation used for both recorded stages; the data binds it by its Git blob identity. No post-consumer source change is folded into the runtime claim. All mathematical claims are restricted either to the proved rectangular support statement or to the specified finite data. The full Erdős pinned-distance question remains outside the delivered conclusion.
