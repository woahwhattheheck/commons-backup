# Explicit integer projection with exact incidence preservation

## Delivered result

[integer_plane_projection.cjs](integer_plane_projection.cjs) maps a bounded finite set of integer points in dimensions 1 through 8 to integer points in the plane. It preserves distinct points and every collinear or noncollinear triple in the supplied set. The projection uses a direct coefficient bound; it enumerates no point pairs or triples and performs no random search.

The actual new consumer is
$$
G=\{0,1,2,3\}^3.
$$

For this 64-point input, the map is
$$
(x_0,x_1,x_2)\longmapsto
\bigl(x_0+19x_1+361x_2,\;
      x_0+6859x_1+47045881x_2\bigr).
$$

The projected coordinate maxima are $(1143,141158223)$. The complete planar incidence result is
$$
t_2=1344,\qquad t_3=72,\qquad t_4=76,
$$
with no line containing five points. Thus the projected set has $P_4$ and gives the finite lower bound
$$
f_4(64)\ge76.
$$

All 64 source points, their projected coordinates, the source/planar ID correspondence, all 1,492 determined lines and their point incidences are retained in [projected_cube_64.json](projected_cube_64.json). The result is a finite construction; no optimality or external-frontier claim is made.

## Source and scope

Solymosi and Stojaković's [*Many collinear k-tuples with no k+1 collinear points*](https://arxiv.org/pdf/1107.0327), Discrete & Computational Geometry 50 (2013), 811–820, [DOI 10.1007/s00454-013-9526-9](https://doi.org/10.1007/s00454-013-9526-9), uses structured integer point sets in higher-dimensional space and a generic projection to the plane that preserves the relevant incidence pattern without introducing collinear triples. That projection step belongs to their established construction.

The bounded map here makes a planar projection explicit for a supplied finite set. Its coordinate bound and preservation proof are stated below. This is a finite computational realization of that kind of projection step, with no claim of priority for generic projection or replacement of the paper's asymptotic theorem. The cube consumer does not reproduce the asymptotic construction.

The underlying extremal convention comes from Erdős's Problem 36 in [*Research problems*, Periodica Mathematica Hungarica 15(1) (1984), 101–103](https://www.renyi.hu/~p_erdos/1984-18.pdf). Points are distinct geometric points; $P_k$ means no line contains more than $k$ points. The quantity $f_k(n)$ ranges over all admissible sets of $n$ points in the real plane. Integer-coordinate examples supply valid lower bounds within that larger domain.

The previous 100-point host and 40-point subsets from Commons #31227 and #31232 remain unchanged. This consumer uses a new higher-dimensional input and the existing public incidence API.

## The map

Let $P\subset\mathbb Z^d$ be a finite set, with $d\ge1$. For nonempty $P$, let
$$
m_i=\min_{p\in P}p_i,\qquad
D_i=\max_{p\in P}p_i-m_i,\qquad D=\max_iD_i.
$$

Translate each point to $z_i=p_i-m_i$, so every coordinate lies in $[0,D]$. Define
$$
C=2D^2,\qquad t=\max(2,C+1),
$$
and
$$
\Phi(p)=
\left(\sum_{i=0}^{d-1}z_i t^i,\;
      \sum_{i=0}^{d-1}z_i t^{di}\right).
$$

The same translation and the same base apply to every point in the input set. The function is an affine map on its coordinates. The preservation guarantee below is for the supplied bounded integer input.

### Distinct points remain distinct

If $D>0$, then $t=2D^2+1>D$. Every translated coordinate is a base-$t$ digit in $\{0,\ldots,D\}$. Uniqueness of a finite base-$t$ expansion shows that the first projected coordinate already distinguishes different input vectors.

Equivalently, the difference of two first-coordinate polynomials has integer coefficients of magnitude at most $D$, and a nonzero leading term dominates its lower terms at this base. Thus the projection does not merge distinct points.

When $D=0$, there is at most one distinct input point. Its translated vector and projected point are zero, so distinctness has no nontrivial case to check.

### Collinear triples remain collinear

Translation does not alter differences, and both projected coordinates are linear forms in those differences. If the difference vectors of an input triple are linearly dependent, their images are linearly dependent as well. For distinct input points, the distinctness result prevents an entire determined line from collapsing to one projected point.

### Noncollinear triples remain noncollinear

Take a noncollinear triple and let $u,v\in\mathbb Z^d$ be its two difference vectors from one point. They are linearly independent, and every coordinate of $u$ and $v$ has absolute value at most $D$.

The determinant of the two projected difference vectors is the value at $T=t$ of
$$
F(T)=\sum_{i=0}^{d-1}\sum_{j=0}^{d-1}
       (u_i v_j-v_i u_j)\,T^{i+dj}.
$$

The exponents $i+dj$ are distinct for distinct ordered pairs $(i,j)$ in this range. Indeed, equality of two exponents gives $i-i'=d(j'-j)$, while $|i-i'|\le d-1$, forcing both differences to be zero.

Independence of $u,v$ means some coefficient $u_i v_j-v_i u_j$ is nonzero. Every coefficient is an integer and has magnitude at most $2D^2=C$. Hence $F$ is a nonzero integer polynomial.

Let $a_L T^L$ be its leading nonzero term. Then $|a_L|\ge1$. Since a noncollinear triple requires $D>0$, the chosen base satisfies $t=C+1$. The lower terms obey
$$
\left|\sum_{\ell=0}^{L-1}a_\ell t^\ell\right|
\le C\sum_{\ell=0}^{L-1}t^\ell
=C\frac{t^L-1}{t-1}
=t^L-1
<|a_L|t^L.
$$

Therefore $F(t)\ne0$, proving noncollinearity of the projected triple. No root search, determinant sampling or triple enumeration is required.

### Complete line incidence is preserved

A determined line contains at least two distinct input points. Their images are distinct and determine a planar line. Every other input point on the original line maps onto that planar line by collinearity preservation. Every input point outside it stays outside by noncollinearity preservation.

Thus determined lines and all their point incidences correspond exactly. Maximum collinearity, exact multiplicity counts $t_k$ and cumulative counts $T_k$ are preserved.

The finite-input bound is essential to the chosen base and theorem. These guarantees do not assert injectivity or triple preservation for arbitrary additional real vectors.

## Endpoint conventions

The dimension must be an integer from 1 through 8. Dimension zero is outside the API contract.

For $d=1$, both coordinate formulas reduce to $z_0$. The output lies on the diagonal $(z_0,z_0)$; the map preserves the distinct points and the collinearity of the one-dimensional input. There are no noncollinear input triples.

An empty input is allowed when its dimension is supplied. Its recorded coordinate minima, maxima and spans are zero by convention, its base is 2, and its output has no points. The output coordinate extrema are null.

If the input contains one distinct point, including a raw list repeating that point, all spans are zero. The base is again 2 and the output is the singleton $\{(0,0)\}$. Raw duplicates are deduplicated as a set and retained in the input-to-source-ID mapping.

## Public API

The module exports `projectIntegerPointsToPlane` and the immutable `PROJECTION_LIMITS` object. It has no imports or I/O and runs as CommonJS in connected V8.

```javascript
const projected = projectIntegerPointsToPlane({
  dimension: d,
  points: inputPoints
});
```

Every point must be an array of exactly `dimension` coordinates. A coordinate may be a canonical integer string, a BigInt, or a safe integer Number. String inputs permit `"0"` and signed nonzero decimal integers without leading zeros. A leading plus sign and `"-0"` are rejected. Numeric negative zero is normalized to zero. Unsafe Numbers, nonintegers and other value types are rejected.

Input points have set semantics. Distinct vectors receive zero-based source IDs in numerical lexicographic order of their original coordinates. `input_to_source_point_ids` maps every raw input entry, including duplicates, to its source ID.

The result is a JSON-serializable object with:

| Field | Meaning |
|---|---|
| `dimension`, `input_entries`, `distinct_points`, `duplicates_removed` | Exact input shape and set counts. |
| `translation` | Coordinate minima, maxima, spans and $D$, as canonical integer strings. |
| `parameters` | $C$, $t$, both exponent lists and the configured digit limits. |
| `records` | Every source ID with its original, translated and projected coordinates. |
| `points` | Projected integer-string pairs, ready for the planar incidence API. |
| `input_to_source_point_ids` | Raw-input provenance, including repeated points. |
| `output_coordinate_minima`, `output_coordinate_maxima` | Actual projected extrema, or null for an empty set. |
| `guarantee` | The finite-set preservation statement justified by this map and proof. |
| `work` | Actual coordinate and Horner-operation counts, including zero pair/triple enumeration counters. |

The guarantee fields describe outputs produced by this function. They are not a validator for arbitrary or modified serialized objects.

The projected point array follows source-ID order. The incidence API independently assigns point IDs in planar coordinate order. These orders can differ; the actual dataset retains both directions of the complete source/planar correspondence.

## Hard bounds and exact arithmetic

| Bound | Value |
|---|---:|
| Dimension | 1 through 8 |
| Raw input point entries | 512 |
| Distinct input points | 256 |
| Decimal digits per signed input coordinate, excluding its sign | 128 |
| Decimal digits per nonnegative projected coordinate | 128 |

All translations, spans, bases and projected coordinates use BigInt. IDs and bounded counters use safe small Numbers.

The module evaluates each nonnegative coordinate polynomial by Horner's rule. Before multiplication by $t$, it compares the accumulator with $\lfloor M/t\rfloor$, where $M=10^{128}-1$; before addition it checks the remaining budget. This rejects an oversized image before constructing an out-of-contract accumulator.

Translated coordinates are nonnegative, and $t\ge2$, so subsequent Horner steps cannot decrease an oversized accumulator. The rejection therefore does not discard a point whose final image would fit. Similarly, if $D>M$, some projected first coordinate must exceed $M$, permitting an exact early rejection.

A RangeError terminates an out-of-contract projection without returning a partial point set. The base and coefficient-bound metadata can have more digits than an output coordinate, especially for dimension one; the 128-digit output cap applies to the two image coordinates.

For each distinct point, projection uses $d^2-1$ bounded multiplications and $2(d-1)$ additions after two accumulator initializations. Input parsing and translation inspect coordinates directly, and source IDs require lexicographic sorting. The method avoids a cubic triple loop; arithmetic cost still depends on the bounded integer sizes.

## A finite grid family

For integers $k\ge2$ and $d\ge1$, consider
$$
G_{k,d}=\{0,\ldots,k-1\}^d.
$$

Every line contains at most $k$ grid points: some coordinate varies along a determined line, and the line parameter is injective in that coordinate, whose possible values number only $k$.

A line with exactly $k$ grid points must use all values $0,\ldots,k-1$ in a varying coordinate. They give equally spaced parameter values. Every other coordinate then changes by a fixed integer step. Its total change lies between $-(k-1)$ and $k-1$, so that step is $-1$, 0 or 1.

If the direction has $r$ nonzero coordinates, choose their positions in $\binom{d}{r}$ ways and their signs up to reversing the whole line in $2^{r-1}$ ways. A varying coordinate must start at 0 for a positive step or at $k-1$ for a negative step. Each remaining fixed coordinate has $k$ choices. Different choices specify different geometric lines, with reversal already identified.

Thus the exact number of $k$-point lines in this grid is
$$
\sum_{r=1}^d {d\choose r}2^{r-1}k^{d-r}
=\frac{(k+2)^d-k^d}{2}.
$$

The explicit projection theorem preserves every such line and introduces no larger collinear subset. For the Erdős range $k\ge4$, it follows that
$$
f_k(k^d)\ge\frac{(k+2)^d-k^d}{2}.
$$

This is a constructive finite-family lower bound arising from the ordinary grid and the incidence-preserving projection. It is not an extremal equality, a new-priority claim for the grid/generic-projection method, or a replacement for the stronger asymptotic construction already credited above.

The algebraic projection proof and this counting argument apply to every finite integer $d$ and $k$ in their stated ranges. The shipped API imposes its separate dimension, point-count and output-digit caps. A family member outside those implementation limits is not claimed as an executed API input.

### The actual 64-point consumer

For $k=4$ and $d=3$, the support-size contributions are
$$
48+24+4=76.
$$

The new actual API call returns precisely 76 four-point lines and no five collinear points. Its full planar profile also includes 72 three-point lines and 1,344 two-point lines. Pair accounting is
$$
1344+3(72)+6(76)=2016={64\choose2}.
$$

The exact ratio is $76/64^2=19/1024$. The complete data therefore gives $f_4(64)\ge76$, without an extremal equality. The family corollary uses the direct counting proof; no additional grid enumeration or second cube computation was run.

## Actual execution and saved-result reuse

One connected V8 call projected the 64 points and passed the result once to the unchanged [integer_line_incidence.cjs](integer_line_incidence.cjs), blob **c9ecc841f6d5b2470e3619206682d3ea8c360449**, originally released in Commons #31227.

Projection read and translated 192 coordinates, using 128 Horner initializations, 512 multiplications and 256 additions. It enumerated zero pairs and zero triples. The new planar index then enumerated its 2,016 unordered pairs once, retained 1,492 lines and 3,208 point-line incidences, and returned a successful $P_4$ assessment.

Three public API pages contain 512, 512 and 468 line records. Their concatenation matches the complete saved incidence snapshot. Single-run timing observations are retained without a comparative or statistical benchmark claim.

To consume the saved planar geometry without projecting or enumerating its pairs again, parse `projected_cube_64.json` as `saved` and load the unchanged incidence module text as `incidenceModuleText`:

```javascript
const m = { exports: {} };
new Function("module", "exports", incidenceModuleText)(m, m.exports);

const view = m.exports.createIntegerLineIncidenceIndex({
  snapshot: saved.incidence.snapshot
});
const assessment = view.assess({ k: 4 });
const richLines = view.linePage({
  min_points: 4,
  max_points: 4,
  offset: 0,
  limit: 1000
});
```

The complete source/projected inputs and both ID maps remain in the same dataset. All prior host and subset computations remain in their existing files and were not repeated for this delivery.
