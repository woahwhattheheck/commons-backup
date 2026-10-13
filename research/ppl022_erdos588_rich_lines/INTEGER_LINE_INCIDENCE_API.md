# Exact integer-line incidence and reusable subset views

## Delivered result

The public module [integer_line_incidence.cjs](integer_line_incidence.cjs) builds a complete exact incidence index for a bounded finite set of integer-plane points. It supports full line and point export, multiplicity profiles, the $P_k$ admissibility check required by Erdős problem 588, and subset views that reuse the original line records.

The actual consumer starts with the retained set

$$
S=\{0,1,9,14,24,35,41,53,57,60\}.
$$

It compiles $S\times S$ once, serializes the complete result, restores that certificate in a fresh connected V8 call, and constructs the 40-point subset

$$
P=\{(s_i,s_{(i+j)\bmod10}):0\le i<10,\ j\in\{1,2,3,4\}\},
$$

where $s_0<\cdots<s_9$ enumerate $S$.

The complete computation gives

$$
t_2(P)=642,\qquad t_3(P)=6,\qquad t_4(P)=20,
$$

and no line contains five points. Thus $P$ has property $P_4$ and supplies the finite bound

$$
f_4(40)\ge20,\qquad \frac{t_4(P)}{40^2}=\frac1{80}.
$$

This is a finite construction, without an extremality or priority claim. Every point and every determined line of both the original 100-point set and its 40-point subset is retained in [sidon_grid_and_cyclic_subset.json](sidon_grid_and_cyclic_subset.json).

## Sources and mathematical scope

Erdős's Problem 36 in [*Research problems*, Periodica Mathematica Hungarica 15(1) (1984), 101–103](https://www.renyi.hu/~p_erdos/1984-18.pdf), [DOI 10.1007/BF02109375](https://doi.org/10.1007/BF02109375), considers $n$ distinct points in the real plane. Its property $P_k$ requires that no line contain more than $k$ points. The quantity $f_k(n)$ maximizes the number of $k$-point lines among configurations with that property. For fixed $k>3$, the stated asymptotic question asks whether $f_k(n)/n^2$ tends to zero.

For a finite set $P$, write $t_k(P)$ for the number of lines containing exactly $k$ points and $T_k(P)$ for the number containing at least $k$. They agree under $P_k$. For unrestricted input they can differ, so checking the cap requires the complete larger-incidence counts. Points and geometric lines are counted once, regardless of duplicate input records or how many pairs generate a line.

Integer-coordinate configurations are a valid subclass of the real-plane domain. A valid finite configuration supplies a lower bound on $f_k(n)$; its count does not establish the extremal value over all real configurations.

Prior construction credit belongs to [József Solymosi and Miloš Stojaković, *Many collinear k-tuples with no k+1 collinear points*](https://arxiv.org/pdf/1107.0327), Discrete & Computational Geometry 50 (2013), 811–820, [DOI 10.1007/s00454-013-9526-9](https://doi.org/10.1007/s00454-013-9526-9). Their theorem gives large configurations for each fixed $k\ge4$ with nearly quadratic numbers of $k$-point lines and no larger collinear subset. It uses higher-dimensional integer sets and generic planar projection; the counted tuples form arithmetic progressions. The finite input below is defined independently, with no new asymptotic or external-frontier claim.


## Input provenance and the actual counts

The integer values of $S$ come from the first normalized family in the accepted [Commons #31157](https://github.com/woahwhattheheck/commons/pull/31157) data, at

`research/conjectures_erdos153_exact_values/n10_finite_premises.json`,

blob **60a1aabeb9b1e04e4dba9423ff0f57933d9e82ae**, JSON path `search.minimizer_families[0].normalized_values`. The accepted merge is **c8c12c19ba5733c7ad7314c6590c2135afad673f**.

This computation consumes the same retained values through [Commons #31177](https://github.com/woahwhattheheck/commons/pull/31177), `research/conjectures_erdos1192_firstpiece/r20_retained_set_representations.json`, blob **c16c65271b04e3ee9e82ded0372a7919c150fe31**. The earlier Sidon search, optimality statements and ordered-representation counts are not recomputed. Their authorship and conclusions remain with those sources; only the ten integer values are used here.

The Cartesian product has 100 distinct points and 3,970 determined lines. Its complete nonzero multiplicities are:

| Points on a line | Number of distinct lines |
|---:|---:|
| 2 | 3,921 |
| 3 | 28 |
| 10 | 21 |

Multiplicities 4 through 9 are zero. The 21 ten-point lines are the ten vertical lines, ten horizontal lines and the diagonal $x=y$. In particular, the original grid has $T_4=21$ but $t_4=0$, and it fails $P_4$. Its admissible $k=10$ interpretation is $f_{10}(100)\ge21$.

The cyclic-offset subset has four points on each of the ten selected rows and ten selected columns, and excludes the diagonal $x=y$. Row and column counts alone would not establish $P_4$; the full incidence calculation supplies the check for every other direction. Its profile is:

| Points on a line | Number of distinct lines |
|---:|---:|
| 2 | 642 |
| 3 | 6 |
| 4 | 20 |

The 20 four-point lines are exactly those rows and columns. All six three-point lines are also retained with their canonical coefficients and point IDs.

The accounting identities are exact:

$$
3921+3(28)+45(21)=4950={100\choose2},
$$

$$
642+3(6)+6(20)=780={40\choose2}.
$$

The dataset includes both the rejected $k=4$ assessment of the full grid and the admissible $k=4$ assessment of the subset. An assessment supplies a finite extremal lower bound only when its collinearity cap holds.

## Public interface

The module exports `createIntegerLineIncidenceIndex` and the immutable `LIMITS` object. It uses CommonJS syntax, has no imports or I/O, and runs in the connected V8 runtime.

Choose one construction form:

```javascript
const view = createIntegerLineIncidenceIndex({
  points: [[x0, y0], [x1, y1] /* ... */]
});
```

or restore a complete exported certificate:

```javascript
const view = createIntegerLineIncidenceIndex({
  snapshot: savedSnapshot
});
```

Supplying both `points` and `snapshot` is rejected. Coordinate inputs may be canonical integer strings, BigInt values or safe integer Numbers. Strings have no leading plus sign or leading zeros; `"-0"` is rejected. Numeric negative zero is normalized to zero. Unsafe Numbers and nonintegers are rejected before geometric work.

Repeated coordinates describe one point. The raw-entry count and number of duplicates removed are reported. Unique points receive zero-based IDs in numerical lexicographic order by $x$, then $y$.

Every view exposes the following operations:

| Operation | Result |
|---|---|
| `describe()` | Point/line counts, maximum collinearity, exact pair and incidence accounting, source ID-space sizes and actual work counters. |
| `profile()` | Exact and cumulative line counts for every multiplicity from 2 through the maximum. |
| `pointPage({offset, limit})` | A page of the view's points, with original point IDs and canonical integer coordinates. |
| `linePage({offset, limit, min_points, max_points})` | A page of lines satisfying the inclusive multiplicity filter, with coefficients and every incident point ID. |
| `assess({k})` | For integer $k\ge4$, checks $P_k$, returns $t_k$, $T_k$, all-overfull-line count, one complete violating-line witness if needed, and an exact reduced ratio $t_k/n^2$. |
| `subset({point_ids})` | A new view of selected points, obtained solely by intersecting the current line-incidence lists with those IDs. |
| `snapshot()` | Complete serializable point/line records and recomputed aggregate information for the current view. |

Page defaults are `offset=0` and `limit=100`. Each page reports `total`, `returned` and `next_offset`, which is null at the end. A line page defaults to every determined line. Its offset is a position in the filtered list, not a line ID.

Line IDs follow numerical lexicographic order of the canonical coefficient triples $(a,b,c)$. Subsets preserve source point and line IDs, so gaps in their ID sequences are expected. Repeated subset IDs are deduplicated. A child view can only select points already present in its parent; an ID outside that view is rejected. Adding a new coordinate requires a new compilation or a complete new certificate.

For `assess`, `finite_extremal_lower_bound` is null when $P_k$ fails or the point set is empty. A ratio may still be returned for an ineligible nonempty input as a descriptive statistic. It does not make that input an admissible extremal construction. The exact and cumulative counts refer only to lines determined by at least two distinct points.

## Canonical lines and complete incidence recovery

For distinct points $(x_1,y_1),(x_2,y_2)$, compute

$$
a=y_1-y_2,\qquad b=x_2-x_1,\qquad
c=x_1y_2-x_2y_1.
$$

The line is $ax+by+c=0$. Divide the triple by $\gcd(|a|,|b|,|c|)$ and choose the sign so $a>0$, or $a=0$ and $b>0$. Because the points are distinct, $a,b$ are not both zero. The result is a unique primitive integer representation of their geometric line, including vertical and horizontal lines.

Compilation visits each unordered point pair once and groups it by this canonical triple. A record collects the distinct endpoints of all its pairs. Every point on a determined line appears in a pair on that line, so the resulting incidence list is complete. The observed pair count for a line with $m$ points must equal $\binom m2$; compilation enforces that invariant.

This distinguishes a geometric line from the many point pairs that can determine it. All coordinate differences, products, greatest common divisors and line equations use BigInt. The bounded counts and IDs use exact small Numbers.

## Restoring a complete certificate

The snapshot constructor does not reconstruct or normalize all point pairs. It checks the retained certificate directly:

1. Points have valid integer coordinates, increasing IDs and distinct lexicographic order.
2. Line triples are primitive, sign-normalized, distinct and ordered, with valid increasing IDs.
3. Every listed incident point is present in the view and satisfies its stated line equation.
4. Each line lists at least two distinct points and has the corresponding exact multiplicity and pair count.
5. The sum of those line pair counts equals $\binom n2$ for the listed point set.

These conditions prove completeness. Two distinct geometric lines cannot contain the same unordered pair of distinct points. Thus the valid listed lines account for disjoint sets of pairs. Equality with $\binom n2$ means every pair is represented. Every determined line is consequently listed, and its entire incidence list is present; omitting a point on it would leave a pair unrepresented.

The restorer recomputes profiles and counts from these checked records. It does not trust a saved aggregate profile. The point and line IDs remain labels in the recorded source namespaces. A snapshot of a subset certifies the points listed in that snapshot; it does not recreate absent points from its original source. Source provenance is separately pinned by the published record and Git identities.

The empty set and a singleton have no determined lines. Their maximum collinearity values are zero and one respectively. These endpoints permit ordinary finite-set manipulation; the empty assessment supplies no positive-$n$ extremal interpretation.

## Subsets reuse the original geometry

A subset cannot create a new line containing two of its points: that pair already belonged to the parent point set. Each child incidence list is therefore the intersection of a parent line's point IDs with the selected IDs. Lists with fewer than two remaining points are omitted.

This operation uses membership checks and bounded integer counts. It performs no coordinate arithmetic, greatest common divisor computation or point-pair construction. The same $\sum_\ell\binom{m_\ell}{2}=\binom n2$ accounting invariant is enforced for the subset.

The actual computation used two connected V8 calls. The first compiled the 100-point grid and retained its complete snapshot. The second parsed that 434,237-character snapshot, checked it, and created the 40-point subset. All restored point records, line records and profile entries matched the saved data exactly.

| Actual operation | Point-pair constructions | Additional work retained |
|---|---:|---|
| Compile 100-point grid | 4,950 | 9,900 gcd calls; 24,049 Euclidean remainder steps. |
| Restore full saved snapshot | 0 | 3,970 line records validated; 8,136 point-line checks; 7,940 gcd calls. |
| Form 40-point subset | 0 | 3,970 parent line records and 8,136 memberships inspected; no gcd calls. |

All 668 subset lines were also exported through two public API pages of 512 and 156 records. Their concatenation matches the complete subset snapshot. Single-run timing observations are retained in the data without a benchmark or comparative performance claim.

## Use the saved result in connected V8

After obtaining the module's complete text as `moduleText` and parsing the published JSON as `saved`, the following uses the public restore/subset interface:

```javascript
const m = { exports: {} };
new Function("module", "exports", moduleText)(m, m.exports);

const original = m.exports.createIntegerLineIncidenceIndex({
  snapshot: saved.base.snapshot
});
const selected = original.subset({
  point_ids: saved.subset.request.point_ids
});
const assessment = selected.assess({ k: 4 });
const richLines = selected.linePage({
  min_points: 4,
  max_points: 4,
  offset: 0,
  limit: 1000
});
```

The record contains the complete inputs and results of the already completed consumer, including every original/subset line, the exact selected IDs, assessments, snapshot-restoration evidence and paged export. No source enumeration or earlier representation computation is required to consume these saved inputs.

## Hard bounds

| Bound | Value |
|---|---:|
| Raw point entries or subset-ID entries | 512 |
| Distinct source points | 256 |
| Decimal digits per coordinate, excluding a minus sign | 128 |
| Decimal digits per saved normalized line coefficient | 257 |
| Unordered point pairs / saved line records | 32,640 |
| Records returned in one page | 1,000 |

The coefficient limit includes the possible difference of two products of 128-digit signed coordinates. The distinct-point cap is checked before the quadratic pair loop. Snapshot arrays and identifier namespaces are also bounded.

The module returns complete results within these limits and rejects inputs outside its contract. It does not silently truncate point sets, line lists or collinearity checks. All geometric arithmetic is exact; no floating-point slope tolerance is used.

The completed result concerns these finite integer configurations and this public bounded API. It supplies no exhaustive census, current-status census, optimal real-plane configuration, asymptotic conclusion, formal-kernel result or sponsor submission. The earlier accepted computations and the published construction literature retain their original credit.
