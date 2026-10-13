# Direct line navigation in a finite integer rectangle

## What this adds

[rectangular_line_navigation.cjs](./rectangular_line_navigation.cjs) describes every line determined by a full planar integer rectangle through a primitive direction and a canonical boundary start. It supports threshold counts, numerical rank and select, bounded line pages, exact line equations, requested point pages, and the complete set of qualifying lines through a specified point.

The index stores direction and count profiles rather than a table of every line or point pair. Positive and negative versions of a slope share one absolute-direction profile. A saved reader reuses those profiles and counts its new query arithmetic explicitly.

For the recorded **17 by 29** rectangle, one compilation represents **55,126 determined lines** through **556 signed directions**, **279 shared absolute profiles**, **771 profile threshold rows** and **940 global prefix blocks**. A fresh saved reader then made 14 queries, including exact negative-slope navigation and both sides of a direction-block boundary.

The module is a new companion to the existing [integer incidence API](./INTEGER_LINE_INCIDENCE_API.md) and [aggregate grid API](./GRID_LINE_HISTOGRAM_API.md). Those modules and all previous datasets remain unchanged. The arbitrary-point incidence API materializes bounded pair geometry; the aggregate grid API provides histogram counts without individual line addresses. This companion supplies direct planar-rectangle navigation.

## Original problem convention and finite scope

The existing directory documents Erdős's Problem 36 in [*Research problems* (1984)](https://www.renyi.hu/~p_erdos/1984-18.pdf). For fixed k>3, f_k(n) is the largest number of k-point lines in an n-point real-plane set satisfying P_k: no line contains more than k of its points.

That admissibility condition is essential. An at-least-k count from a set with longer lines is not automatically a lower bound for f_k(n). This module reports exact and cumulative multiplicities separately and exposes an assessment that explicitly checks P_k.

A full w by h integer rectangle has maximum collinearity max(w,h). A primitive nonzero direction has at least one nonzero integer component, so a line using it has at most w points when its horizontal component is nonzero, and at most h when its vertical component is nonzero. A horizontal or vertical row attains the larger side. The one-point rectangle has maximum collinearity one and no determined line.

Consequently the actual 493-point rectangle:

- fails P_4, although it has 2004 lines with exactly four points;
- has 1650 overfull lines for that P_4 assessment;
- satisfies P_29 and has exactly 17 lines with 29 points;
- supplies the finite bound f_29(493) >= 17.

These are properties of this one explicit configuration. No global extremal equality, new best-known bound, asymptotic advance or problem-status update is claimed.

The source lookup for FormalConjectures/ErdosProblems/588.lean returned HTTP404 once during this assessment and was left unretried. The existing source-qualified directory conventions were retained; no missing formal source was reconstructed.

## Accepted rectangle custody

The input rectangle comes from the complete accepted artifact:

| Field | Identity |
|---|---|
| Repository | woahwhattheheck/commons |
| Path | research/ppl174_erdos604_pinned_distances/grid17x29_pinned_distances.json |
| Revision | 03a09a629e50409b015f72cf56452ce40b9338bf |
| Git blob | 75dad6ddfd00a0efb2c80bddb12eb4e13405d216 |
| Consumed field | construction.request |
| x coordinates | 0 through 16 |
| y coordinates | 0 through 28 |

The [pinned source file](https://github.com/woahwhattheheck/commons/blob/03a09a629e50409b015f72cf56452ce40b9338bf/research/ppl174_erdos604_pinned_distances/grid17x29_pinned_distances.json) was read completely. The consumer retained its exact request and checked that each supplied axis is consecutive before selecting the origin and side lengths.

The source's squared differences, pinned-distance profiles, convolutions and previous reader results were not recomputed. This is a new line-navigation calculation on the identified coordinate rectangle.

Point IDs preserve the source convention:

$$
\operatorname{pointId}(i,j)=i\,h+j,
\qquad 0\le i<w,\quad0\le j<h.
$$

The integer indices are local to the rectangle. Actual coordinates are the declared origins plus those indices.

## Direction and start conventions

### Unoriented primitive directions

Each unoriented direction is represented once:

- (u,v) with u>0, allowing either sign of v; or
- the vertical direction (0,1).

The horizontal direction is (1,0). Non-axis directions require gcd(u,|v|)=1. Candidates satisfy u<=w-1 and |v|<=h-1 so they can join distinct grid points.

The compiler examines every positive candidate (a,b) in the corresponding bounded rectangle once. It retains the full Euclidean chain and gcd even for a candidate that is not primitive. Every primitive positive pair supplies one absolute profile used by both (a,b) and (a,-b). Axis profiles are explicit.

Directions are sorted by signed (u,v), first u and then v. Their contiguous IDs survive saved opens. Since each unoriented direction already appears once, the direction sums in this API need **no additional factor of one half**.

The older aggregate grid guide credits Pentti Haukkanen and Jorma K. Merikoski, [*Some formulas for numbers of line segments and lines in a rectangular grid*](https://arxiv.org/pdf/1108.1041), Ars Combinatoria104(2012), for prior segment and line-count identities in general rectangular grids. Its theorem/corollary attribution remains in [GRID_LINE_HISTOGRAM_API.md](./GRID_LINE_HISTOGRAM_API.md), blob47a2e381259e596682bb1a4719fc8f014d906c98. The new capability is direct boundary-start navigation; no formula-priority claim is made.

### Reflect negative slopes

For v<0, replace the local y index by

$$
y'=h-1-y.
$$

Then the step becomes (a,b)=(u,|v|), with nonnegative components. For v>=0 use y'=y.

Every maximal grid line has a unique first point in this step direction. Within a fixed direction, starts are ordered by increasing x, then increasing reflected y'. Thus a negative slope's within-column reflected order corresponds to decreasing original y. This is intentional and part of the public rank contract.

The complete order is:

1. signed direction (u,v);
2. first-point x index;
3. first-point reflected y index.

Ranks are zero-based and depend on the requested minimum multiplicity. A line can have different ranks at different thresholds.

### Stable addresses and threshold ranks

A line address is

```js
{
  source_id: "the original index source identity",
  direction_id: 134,
  start_x: 0,
  start_y_reflected: 0
}
```

The source identity prevents accidental use of an address belonging to a different declared index. It is not cryptographic authentication. A saved open uses its own reader-session identity while preserving the original index identity in line addresses.

An address identifies one line independently of the query threshold. A numerical rank identifies its position in the subset with at least k points.

## Why two boundary rectangles suffice

Every integer point on the real line through an integer point in a primitive integer direction differs from it by an integer multiple of that direction. A Bézout identity for the direction components proves this: if both coordinates of a scalar multiple are integers, the scalar is an integer. Convexity of the rectangular box then makes the present multiples consecutive.

For the nonnegative reflected step (a,b), a first point (x,y') supports at least k consecutive grid points exactly when

$$
0\le x<W_k,\qquad0\le y'<H_k,
$$

where

$$
W_k=\max(w-(k-1)a,0),\qquad
H_k=\max(h-(k-1)b,0).
$$

It is the first point of its maximal line exactly when the preceding primitive step is outside the rectangle. Since a,b are nonnegative, this is

$$
x<a\quad\text{or}\quad y'<b.
$$

Set alpha=min(a,W_k) and beta=min(b,H_k). The qualifying starts are the disjoint union

$$
[0,\alpha)\times[0,H_k)
\quad\cup\quad
[\alpha,W_k)\times[0,\beta).
$$

These two slabs concatenate in the stated x-then-reflected-y order. Each is a small exact rectangle; neither requires enumeration of its starts.

The excluded starts have x>=a and y'>=b. Translation by (-a,-b) places them in the rectangle for one more primitive step. Writing

$$
S_t=\max(w-ta,0)\max(h-tb,0),
$$

the number of maximal lines with at least k points in that direction is therefore

$$
T_k=S_{k-1}-S_k.
$$

The exact-k count is the adjacent difference

$$
t_k=T_k-T_{k+1}.
$$

The compiler retains each step weight once, references adjacent weights from the threshold rows, and retains both slab descriptions and counts. This shares weights between adjacent thresholds as well as profiles between slope signs.

The slab rank/select algorithm applies to **at least k** points. Subtraction gives the exact-k cardinality but does not by itself give an exact-k navigation order. This API does not expose exact-k rank/select.

Geometric line thresholds start at k=2. A singleton point does not determine a unique line or a finite direction family, so k=1 is rejected for line queries.

### Rank and select in a direction

For local rank r, first compare r with the first slab's count alpha*H_k. Select that slab when r is smaller; otherwise subtract its count and select the second slab. Within a selected slab of positive height g,

$$
x=x_{\rm slab}+\lfloor r/g\rfloor,\qquad y'=r-g\lfloor r/g\rfloor.
$$

An empty slab is never used as a divisor. The implementation requires a selected rank to lie below the positive slab count.

The inverse is the preceding slab count plus

$$
(x-x_{\rm slab})g+y'.
$$

At each threshold, the compiler concatenates positive-count direction blocks and stores exact prefix starts and ends. Global select binary-searches those blocks; global rank adds the saved prefix start to the local slab rank.

No individual line list is constructed for that threshold.

### Two-point lookup and exact equations

Given two distinct points in the rectangle, divide their coordinate difference by the gcd of the absolute differences, then normalize its sign to the canonical direction. Reflection is applied according to the normalized signed v.

The number of backward steps to the first point is the minimum of

$$
\lfloor x/a\rfloor,\qquad\lfloor y'/b\rfloor
$$

over nonzero components. The analogous forward minimum, using the remaining horizontal and vertical room, gives one less than the maximal length. Zero direction components are omitted from these divisions.

The line descriptor uses original coordinates, including signed v. Starting from actual (x_0,y_0), its equation is

$$
vX-uY+(u y_0-v x_0)=0.
$$

The coefficient sign is normalized so the first nonzero one of a,b in aX+bY+c=0 is positive. Primitivity of (u,v) makes the coefficient triple primitive; no repeated gcd reduction is needed when a descriptor is materialized.

The descriptor retains its stable address, direction, shared-profile address, maximal length, first and last actual points, exact equation and forward quotient witnesses.

### Complete histogram and pair accounting

Every unordered pair of distinct rectangle points has a unique primitive direction and maximal line. A line containing ell points contributes choose(ell,2) pairs, giving

$$
\sum_{\ell\ge2}\binom{\ell}{2}t_\ell=\binom{wh}{2}.
$$

The constructor accumulates this exact identity from its new complete histogram and retains both sides. It also accumulates the point-line incidence count sum(ell*t_ell). This is new aggregate arithmetic for this rectangle; it does not construct the pair population or repeat the accepted distance calculation.


## Public API

The module uses CommonJS, exact BigInt coordinates and bounded safe-integer indices/counts. It has no imports or I/O.

```js
const {
  compileRectangularLineIndex,
  openRectangularLineIndex
} = require("./rectangular_line_navigation.cjs");

const index = compileRectangularLineIndex({
  source_id: "my-rectangle-index",
  rectangle_source_id: "identified-input-source",
  rectangle: {
    x_origin: "0",
    y_origin: "0",
    width: 17,
    height: 29
  }
});
```

The rectangle is the full Cartesian product of consecutive integer coordinates. The API does not accept an irregular point set, a sparse axis or a higher-dimensional box under this declaration.

Origins accept canonical decimal integer strings, BigInt values or safe integer Numbers. Public coordinates and equation coefficients are canonical decimal strings. Side lengths are positive safe integer Numbers.

### Saved open and provenance boundary

```js
const saved = index.snapshot();
const reader = openRectangularLineIndex(saved, {
  source_id: "my-new-reader-session"
});
```

The snapshot is a complete JSON-compatible restoration format. It includes the rectangle/source identity, all candidate gcd records, shared profiles, directions, prefix views, aggregate totals and per-session work/events.

Opening defensively copies the saved object and validates bounded structure and references. These checks include contiguous IDs, unique candidate/profile addresses, canonical direction order and sign, profile/direction references, threshold/weight addresses, positive prefix blocks and their referenced retained counts, and valid source/rectangle metadata.

Opening does not recompute gcd remainders, regenerate primitive directions, reevaluate step-weight or boundary-count formulas, rebuild the complete prefix family, or re-prove pair accounting. Shape and reference acceptance is not independent mathematical verification of an adversarial snapshot. Correct interpretation requires custody of a snapshot emitted by the stated implementation.

Runtime address maps are rebuilt from retained IDs and references. This indexing is reported as loading, separately from new compiler and query work. Source identity strings bind declared objects but do not authenticate their mathematical contents.

The active reader gets its own zero-initialized new-work counters. Cumulative source work remains inherited. Later query arithmetic is real new work and is counted.

### countLines({minimum_points})

```js
reader.countLines({ minimum_points: 5 });
```

Returns the retained number of lines with at least the threshold, the separate exact-threshold count, the maximum collinearity and rank-order convention. Minimum points must be at least two. Thresholds beyond the maximum return zero counts.

The recorded threshold-five response has at_least_count=1650 and exact_count=684. The API does not turn the latter scalar into an exact-five rank order.

### assess({k})

```js
reader.assess({ k: 4 });
reader.assess({ k: 29 });
```

This follows the source's extremal convention and requires k>=4. It returns P_k, exact-k and at-least-k counts, the count of overfull lines, and an explicit first overfull line when one exists.

The finite lower-bound field is present only when the rectangle satisfies P_k. In the actual consumer, the k=4 result is inadmissible and has no lower-bound field; k=29 returns f_29(493)>=17. The API separately states that no global optimum or asymptotic result is claimed.

### selectLine({minimum_points, rank})

```js
reader.selectLine({ minimum_points: 5, rank: 1546 });
```

Selects a line in the threshold-specific order using a prefix binary search and one local slab quotient. It returns the full line descriptor and the selected direction-block/local-slab addresses.

A nonnegative rank at or beyond the total produces status rank_out_of_range with the total. It does not fabricate a line.

### rankLine({minimum_points, point_a, point_b})

```js
reader.rankLine({
  minimum_points: 5,
  point_a: [0, 28],
  point_b: [16, 0]
});
```

Both points must be distinct and lie in the declared rectangle. The result includes the normalized difference, complete new gcd division chain, backward-start quotient witnesses, line descriptor and its threshold rank.

A valid determined line shorter than the threshold returns below_threshold with rank=null and its descriptor. Coincident or out-of-rectangle points are rejected.

The actual negative-slope query gives direction (4,-7), shared profile66, length5 and rank1546 among1650 lines. The opposite diagonal gives direction (4,7), the same profile66, and rank1649. Their stable addresses differ by direction ID while both use reflected start(0,0).

### pageLines({minimum_points, offset, limit})

```js
reader.pageLines({ minimum_points: 2, offset: 15, limit: 4 });
```

Materializes only the requested bounded sequence of selected line descriptors. Offset is a zero-based threshold rank; limit is at most256. The response includes total, returned and next_offset. A page past the end is empty, with next_offset=null.

The actual page crosses the first direction boundary: ranks15 and16 are the last two vertical lines, and ranks17 and18 are the first two lines in direction(1,-28).

### pageLinePoints({address, offset, limit})

```js
const selected = reader.selectLine({ minimum_points: 29, rank: 8 });

reader.pageLinePoints({
  address: selected.line.address,
  offset: 0,
  limit: 256
});
```

Computes the maximal length directly from the address, then materializes only the requested consecutive primitive-step points. Each point includes its position on the line, source-compatible point ID, local indices and exact original coordinates. The response also supplies the line descriptor.

The actual selected vertical line is x=8. Its complete requested page returns29 points, IDs232 through260, and next_offset=null.

The negative diagonal page returns exactly

$$
(0,28),\ (4,21),\ (8,14),\ (12,7),\ (16,0),
$$

with IDs28,137,246,355,464. Their order follows the canonical signed direction, so original y decreases.

### linesThroughPoint({point, minimum_points})

```js
reader.linesThroughPoint({ point: [8, 14], minimum_points: 4 });
```

Examines each retained direction once for this new point query, derives the unique canonical start and maximal length, and returns all qualifying addresses with their threshold ranks.

It also retains one compact row per examined direction:

```text
[direction_id, start_x, start_y_reflected,
 backward_steps, maximal_length, qualified_rank_or_null]
```

The response declares those column names explicitly. A null rank means that direction's maximal grid intersection through the point does not meet the threshold. These complete rows support review of the query's coverage without enumerating the rectangle's entire line population.

The actual center query examines556 directions and returns42 lines containing at least four points. These are threshold-four ranks: for example, the negative diagonal's rank here is2620, while the same stable line had rank1546 in the threshold-five query. Mixing thresholds would mix different orders.

### summary() and snapshot()

Summary returns complete aggregate counts, the full multiplicity histogram, retained-index sizes, cumulative work and the active session's loading/new-work record. Snapshot returns the complete saved state.

Neither method starts a query event, rebuilds geometry or constructs line descriptors. Summary does assemble/copy its small presentation of already retained records.

Public results and snapshots are defensive copies, and the returned API object and exported constants are frozen. Mutating a caller-held result does not alter the live index.

Every counted query response includes its new_work delta. Successful queries and in-operation failures are retained as bounded session events. A copy-limit failure is recorded as an error rather than both a success and an error.

## Bounds and exact arithmetic

| Bound | Value |
|---|---:|
| Width and height | 1 through512 |
| Positive candidate pairs (w-1)(h-1) | At most4096 |
| Signed directions | At most8194 |
| Retained profile threshold rows | At most50000 |
| Requested line/point page size | At most256 |
| Sessions in a snapshot | At most64 |
| Query events per session | At most256 |
| Source identity length | At most512 characters |
| Origin magnitude | At most128 decimal digits |
| Point-input magnitude | At most129 decimal digits |
| Copied items | At most3000000 |
| Copied string characters | At most32000000 |
| Copy nesting depth | At most32 |

The positive-candidate cap and side caps imply wh<=4096+1023=5119. Counts, ranks and the constructor's weighted pair arithmetic therefore stay within safe integer Number bounds. Coordinates use BigInt, so large exact origins do not affect those local cardinalities.

Adding a bounded nonnegative index can increase a128-digit positive origin to129 digits. The point parser accommodates those outputs. Signed primitive equation coefficients are formed with BigInt, with growth bounded by the origin and direction limits.

Copied state permits JSON-style null, booleans, safe integer numbers, strings, arrays and plain objects. Unsupported object types, unsafe numbers, excessive sizes and reserved prototype-related keys are rejected. No BigInt appears in exported JSON.

The saved reader is structurally conditional even within these bounds: a forged but well-shaped count profile is not mathematically certified by opening it. The guide's derivation and original compiler custody are separate from the loading checks.

## Actual consumer and complete retained evidence

The only new compilation began at **2026-10-04T20:02:49.600Z** with executed implementation blob **1b08067b38964d5c1fd1925710bbc76f1ad56bc2** (39519 UTF-8 bytes). That source was frozen before execution and did not change for the saved reader.

The complete [grid17x29_line_navigation.json](./grid17x29_line_navigation.json) artifact is **763993 UTF-8 bytes**, Git blob **29a3a57204abbc6c43d29250613967780f30bd8c**. Its compact formatting preserves every retained record; no profile, gcd division, prefix block or query row is omitted.

### Complete counts

| Multiplicity | Exact lines | At least this many points |
|---:|---:|---:|
| 2 | 44852 | 55126 |
| 3 | 6620 | 10274 |
| 4 | 2004 | 3654 |
| 5 | 684 | 1650 |
| 6 | 448 | 966 |
| 7 | 126 | 518 |
| 8 | 120 | 392 |
| 9 | 90 | 272 |
| 10 | 44 | 182 |
| 11 | 12 | 138 |
| 12 | 12 | 126 |
| 13 | 12 | 114 |
| 14 | 16 | 102 |
| 15 | 10 | 86 |
| 16 | 4 | 76 |
| 17 | 55 | 72 |
| 18 through28, each | 0 | 17 |
| 29 | 17 | 17 |
| 30, zero endpoint | 0 | 0 |

The complete individual zero rows are retained in JSON. The sum of exact line counts is55126; the point-line incidence sum is129078; and the represented unordered-pair total is121278, equal to choose(493,2).

### Constructor work

| Recorded work | Count |
|---|---:|
| New compiler calls | 1 |
| Positive direction candidates | 448 |
| Candidate Euclidean division steps | 1349 |
| Absolute profiles | 279 |
| Quotients for profile maximum lengths | 556 |
| Shared step-weight rows | 1050 |
| Profile threshold rows | 771 |
| Signed directions | 556 |
| Global direction-prefix blocks | 940 |
| Global threshold views, including zero endpoint | 29 |
| Aggregate pair-accounting terms | 28 |
| Full point-pair enumeration | 0 |
| Full line-population enumeration | 0 |
| Full grid-point enumeration | 0 |

All448 candidate gcd records and their1349 division steps are retained, including nonprimitive candidates. The279 profiles include the two axes and277 primitive positive pairs. Those277 profiles each serve both slope signs, giving556 signed directions.

### Saved-reader work

Opening loaded556 directions,279 profiles,771 profile threshold rows and448 gcd records without regenerating them.

The14 queries comprise four count lookups, two admissibility assessments, two two-point ranks, two selects, two complete selected-point pages, one four-line page and one center-incidence query.

| New reader work | Count |
|---|---:|
| Query calls | 14 |
| Prefix binary-search steps | 53 |
| Tracked quotient operations | 2260 |
| New query gcd steps | 8 |
| Full line descriptors materialized | 11 |
| Point records in requested point pages | 34 |
| Directions examined for center incidences | 556 |
| Count/assessment rows returned | 8 |
| Compiler, direction-candidate and profile construction work | 0 |

The quotient counter covers the explicit gcd, coordinate-step and slab divisions routed through the query helper; binary-search midpoint work is represented by the separate search-step counter. It is not a claim to count every low-level arithmetic instruction.

Each of the11 descriptors additionally contains two endpoint records. The34 page-point count refers specifically to the five negative-diagonal points and29 vertical points returned in the requested point pages. The center query also returns its input-point record and42 qualifying address/length/rank entries, plus all556 compact examined-direction rows. Those address entries are not full line descriptors.

The negative line's equation is7X+4Y-112=0. The positive diagonal is7X-4Y=0. At threshold2, the boundary page gives X=15, X=16, 28X+Y-28=0 and28X+Y-56=0 at ranks15 through18 respectively.

The complete source rectangle, gcd records, profiles, direction order, prefix views and totals compare literally unchanged between the constructor snapshot and final reader snapshot. Those are retained-data identity comparisons, not repeated mathematical proofs.

### Observations and limits of the result

The constructor took one observed3ms, the saved open31ms, and all14 reader queries9ms. These are single execution observations, not benchmarks, speedup ratios or performance guarantees.

No previous point-set, projection, histogram or distance consumer was rerun. The existing arbitrary-point incidence cap of256 distinct points was neither changed nor bypassed: the new full-rectangle API has its own declared representation and bounds.

Exactly three new files and the existing directory README are in this operation's publication scope. All prior implementation and evidence files retain their identities. No new test suite, fixture family, workflow, native probe, outside contact or global research claim accompanies this capability.
