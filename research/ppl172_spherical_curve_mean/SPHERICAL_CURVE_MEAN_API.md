# Certified mean distance for a spherical zigzag curve

## Result and source convention

[Clark Kimberling's section 10](https://faculty.evansville.edu/ck6/integer/unsolved.html) asks for a simple closed curve on the unit sphere, of length exactly \(4\pi\), minimizing the mean of the shortest spherical arclength from a sphere point to the curve. The author does not state an integral measure. This package explicitly adopts normalized uniform surface area:
\[
\mu(C)=\frac1{4\pi}\int_{\mathbb S^2}d(P,C)\,dA(P),
\qquad d(P,C)=\min_{Q\in C}\arccos(P\cdot Q).
\]
The distance is intrinsic spherical distance, in radians. The supplied piecewise-geodesic curve has corners; it is simple, closed and rectifiable, with the required exact length.

For the eight-arc curve \(C_4\) below, the retained calculation gives
\[
\boxed{\frac{2912985\pi}{33554432}
\le \mu(C_4)\le
\frac{3179225\pi}{33554432}}.
\]
The outward decimal enclosure is **[0.272733338, 0.297660527] radians**. The complete index retains 16,384 midpoint samples and 4,097 cosine records, together with the interval and quadrature evidence supporting this bound.

The general swept-cap argument in this guide gives
\[
\mu(C)\ge \arctan(\pi/L)\qquad(L\ge\pi)
\]
for every continuous rectifiable spherical path of length \(L\). Consequently the infimum over admissible length-\(4\pi\) simple closed curves satisfies
\[
\boxed{\arctan(1/4)\le\inf_C\mu(C)
\le\frac{3179225\pi}{33554432}}.
\]
The public reader returns the outward decimal bracket **[0.244978663, 0.297660527]**. Neither endpoint is asserted to be attained. The artifact establishes no global minimizer, equality in the universal bound, solution for every real length \(L>2\pi\), or mathematical priority. The inspected author section is the source of the question, not an exhaustive current-status survey.

## 1. An explicit feasible family

Let \(m\ge3\) be an integer and put
\[
c=\cos(\pi/m),\qquad
a^2=\frac1{1+c},\qquad b^2=\frac c{1+c}=1-a^2,
\qquad a,b>0.
\]
For \(j=0,\ldots,2m-1\), define
\[
v_j=\bigl(a\cos(j\pi/m),\ a\sin(j\pi/m),\ (-1)^j b\bigr),
\]
with indices interpreted modulo \(2m\). Each vertex has unit norm. Consecutive vertices satisfy
\[
v_j\cdot v_{j+1}=a^2\cos(\pi/m)-b^2=0,
\]
including the last-to-first pair. Join them by the minor quarter great-circle arc
\[
\gamma_j(t)=v_j\cos t+v_{j+1}\sin t,\qquad0\le t\le\pi/2.
\]
Orthogonality gives \(\|\gamma_j(t)\|=\|\gamma'_j(t)\|=1\), so each arc has length \(\pi/2\), and the closed curve has exact total length \(m\pi\).

The curve is simple. The planar component of an arc is a positive combination of two nonzero planar vectors whose longitudes differ by \(\pi/m<\pi\). It does not vanish. In the interior, its longitude lies strictly inside that consecutive longitude wedge and increases strictly: the oriented determinant of its planar position and derivative equals \(a^2\sin(\pi/m)>0\). The wedge interiors for distinct arcs are disjoint. Thus different arcs meet only at the common endpoint of consecutive arcs, and the cyclic chain is a simple closed curve. This argument also handles the wedge crossing longitude \(2\pi\) by choosing a continuous lifted longitude.

At \(m=4\),
\[
a^2=2-\sqrt2,\qquad b^2=\sqrt2-1.
\]
There are eight quarter-circle arcs and the total length is exactly \(4\pi\). The family supplies discrete lengths \(m\pi\); it is not a construction or optimizer for every real length in the author's generalization.

## 2. A universal lower bound from swept spherical caps

Let \(C\) be the image of a continuous rectifiable path \(c:[0,L]\to\mathbb S^2\), parametrized by arclength, and let
\[
C_r=\{P:d(P,C)\le r\}.
\]
For \(0<r\le\pi/2\),
\[
\operatorname{area}(C_r)
\le\min\{4\pi,\ 2L\sin r+2\pi(1-\cos r)\}.                 \tag{1}
\]

To see this first for a piecewise smooth path, start with the radius-\(r\) cap centered at \(c(0)\), of area \(2\pi(1-\cos r)\). At a unit-speed point of the center path, let \(v=c'(s)\), and choose a unit tangent vector \(w\) perpendicular to \(v\). The moving cap boundary has the representation
\[
x=\cos r\,c+\sin r(\cos\theta\,v+\sin\theta\,w),
\quad0\le\theta<2\pi.
\]
Its boundary element is \(\sin r\,d\theta\), and its outward unit normal within the sphere is
\[
\nu=(\cos r\,x-c)/\sin r.
\]
Differentiating \(x\cdot c=\cos r\) shows
\(x_s\cdot c=-\sin r\cos\theta\); since \(x_s\cdot x=0\), the outward normal speed is \(x_s\cdot\nu=\cos\theta\). The positive entering flux is therefore
\[
\int_0^{2\pi}\max(\cos\theta,0)\sin r\,d\theta=2\sin r.
\]
Only entering boundary flux can add area to the union of the caps swept so far. The area formula counts boundary crossings with multiplicity; overlaps and revisits can reduce the added union area. Integration along the path gives (1).

For a rectifiable path, use inscribed geodesic polygonal paths with lengths at most \(L\), converging uniformly to an arclength parametrization. If the uniform error is \(\varepsilon\), then \(C_r\) is contained in the polygonal path's \((r+\varepsilon)\)-neighborhood. Applying the polygonal bound and letting \(\varepsilon\downarrow0\) gives (1); the endpoint \(r=\pi/2\) follows by a monotone limit. For a general parametrized path, \(L\) counts retracing. No assertion replaces it with the Hausdorff length of an arbitrary branched set. For the simple closed curves in the source question, \(L\) is their usual length.

Distance layer cake and (1) give
\[
\mu(C)=\int_0^\pi\left(1-\frac{\operatorname{area}(C_r)}{4\pi}\right)\,dr.
\]
Write \(a=L/\pi\). On the relevant half-range a lower integrand is
\[
\max\left(0,\frac{1+\cos r-a\sin r}{2}\right).
\]
Its first positive interval ends at
\[
r_*=2\arctan(1/a).
\]
For \(L\ge\pi\), \(r_*\le\pi/2\), so the half-range bound suffices. Integrating only from zero to \(r_*\), and using
\(\sin r_*=a(1-\cos r_*)\), yields
\[
\mu(C)\ge
\frac{r_*}{2}+\frac{\sin r_*+a(\cos r_*-1)}2
=\arctan(\pi/L).                                      \tag{2}
\]
The original \(L=4\pi\) case and every length \(L>2\pi\) mentioned by the author lie inside this hypothesis. There is no equality or optimality argument here.

## 3. Symmetry and an equal-area integration rectangle

The curve \(C_m\) is invariant under the following sphere isometries:

- rotation \((\theta,z)\mapsto(\theta+2\pi/m,z)\);
- reflection \((\theta,z)\mapsto(-\theta,z)\);
- the combined map \((\theta,z)\mapsto(\theta+\pi/m,-z)\).

They generate a group of order \(4m\). A fundamental domain, up to boundaries of zero area, is
\[
0\le z\le1,\qquad0\le\theta\le\pi/m.
\]
In the parametrization
\[
P(z,\theta)=
(\sqrt{1-z^2}\cos\theta,\sqrt{1-z^2}\sin\theta,z),
\]
the area element is \(d\theta\,dz\). Thus the normalized whole-sphere mean is the normalized average on this rectangle.

Use \(M\) height bands and \(J\) longitude bands, with midpoints
\[
z_i=\frac{2i+1}{2M},\qquad
\theta_j=\frac{(2j+1)\pi}{2mJ},
\quad0\le i<M,\quad0\le j<J.
\]
All \(MJ\) midpoint samples have weight \(1/(MJ)\). The pole is a boundary of zero area; no finite upper bound on the derivative of \(\arcsin z\) near the pole is assumed.

Distance to a fixed nonempty set is 1-Lipschitz in the spherical metric. Within a cell, join the point to its midpoint by a meridian segment and a parallel segment. The spherical distance is at most
\[
|\arcsin z-\arcsin z_i|+|\theta-\theta_j|.
\]
The longitude term is at most \(\pi/(2mJ)\). Bound the height term by the entire latitude span of its height band, then average over the equally weighted bands. Those spans telescope from \(0\) to \(\pi/2\). Therefore
\[
\left|\mu(C_m)-\frac1{MJ}\sum_{i,j}d(P(z_i,\theta_j),C_m)\right|
\le \frac{\pi}{2M}+\frac{\pi}{2mJ}.                    \tag{3}
\]
For \(m=4,M=256,J=64\), this error is exactly \(\pi/256\). It is a proved geometric quadrature bound, not an estimated floating-point integration error.

## 4. Distances without per-sample inverse trigonometry

For orthogonal unit endpoints \(v,w\), write \(A=P\cdot v\) and \(B=P\cdot w\). Along their quarter-circle arc, the dot product is
\(A\cos t+B\sin t\), \(0\le t\le\pi/2\).
When \(A,B\ge0\), its maximum is \(\sqrt{A^2+B^2}\). If only one is positive, the positive endpoint gives the maximum. If both are negative, the maximum is the less negative endpoint.

The sum of all \(2m\) vertices is zero. Consequently at least one vertex dot product is nonnegative, and the whole curve's maximum dot product is nonnegative. The zero introduced by ignoring a fully negative arc cannot exceed this global maximum. Hence
\[
H(P)^2=
\max_j\left((P\cdot v_j)_+^2+(P\cdot v_{j+1})_+^2\right),
\quad x_+=\max(x,0),
\]
is the square of the actual maximum dot product to the curve. The distance is
\[
d(P,C_m)=\arccos H(P)\in[0,\pi/2].                    \tag{4}
\]

The implementation encloses the squared support \(H(P)^2\). It does not compute a new square root or arccosine for each sample. The exact geometry proves the squared support is at most one, so an interval upper endpoint may safely be clipped to one. Coordinate intervals enclose the exact symbolic vertices and points; arbitrary independent selections from those intervals are not being asserted to lie on the unit sphere.

## 5. Directed integer arithmetic and angle certificates

All interval endpoints are integers divided by the common scale
\[
Q=2^{\texttt{fraction\_bits}}.
\]
The sole actual run uses \(Q=2^{48}=281474976710656\). Public precision is bounded to 40 through 64 bits.

Addition, subtraction and integer scaling are exact on endpoints. Products use the minimum and maximum of the four endpoint products, followed by division by \(Q\) rounded down and up. Squaring handles a possible zero crossing. Rational input, division by a positive integer and positive reciprocals use directed floor/ceiling division. Square roots use integer Newton iteration, with a floor square root of \(Q\) times the lower endpoint and a ceiling square root of \(Q\) times the upper endpoint. Negative division is rounded explicitly; truncation toward zero is not substituted for mathematical floor.

### Pi and reciprocal arctangents

The engine retains the complete series records for
\[
\pi=16\arctan(1/5)-4\arctan(1/239).
\]
This identity can be obtained directly from the tangent addition law:
\(\tan(2\arctan(1/5))=5/12\),
\(\tan(4\arctan(1/5))=120/119\), and
\(\tan(4\arctan(1/5)-\arctan(1/239))=1\), with the final angle in \((0,\pi/2)\).

For every reciprocal argument used here, the alternating series
\[
\arctan(1/b)=\sum_{n\ge0}\frac{(-1)^n}{(2n+1)b^{2n+1}}
\]
has decreasing positive term magnitudes. Each rational term receives directed fixed-point endpoints. After a partial sum, the remainder has the sign of the next term and magnitude no greater than that term. The constructor stops when the upward rounded next-term bound is at most one fixed-point unit, subject to the hard term cap.

The actual pi enclosure is
\[
\pi\in
[884279719003464,\ 884279719003640]/Q.
\]
The actual universal-bound enclosure is
\[
\arctan(1/4)\in
[68955363498236,\ 68955363498247]/Q.
\]
All term denominators, signs, rounded term intervals, next denominators and tail bounds are retained. The two Machin series use 12 terms in total; the additional \(\arctan(1/4)\) series uses 11 terms.

### Cosine table

For angles \(x\in[0,\pi/2]\), the engine uses the degree-48 cosine polynomial, with 24 nonconstant terms. Equivalently regard it as the degree-49 Taylor polynomial, whose odd coefficient is zero. Since \(|x|<2\), Taylor's remainder has absolute value at most
\[
2^{50}/50!.
\]
The recurrence for the polynomial terms uses outward interval arithmetic, and the same upward rounded fixed-point remainder is added at the end. The exact endpoint values \(\cos0=1\) and \(\cos(\pi/2)=0\) are inserted directly. Sine is evaluated through \(\sin x=\cos(\pi/2-x)\). A reduced-rational-angle cache reuses values.

For \(K=\texttt{angle\_bins}\), the complete table has entries at
\[
\alpha_i=i\pi/(2K),\quad i=0,\ldots,K.
\]
Each entry stores bounds for cosine and for its square. The squared lower bounds are replaced by tail maxima, and the squared upper bounds by prefix minima. This is valid because the true squared cosine decreases: every later lower bound is also a lower bound for an earlier value, and every earlier upper bound is an upper bound for a later value.

Suppose the squared support of a sample lies in \([L,U]/Q\). Choose the largest lower bin \(l\) with
\[
\underline{\cos^2\alpha_l}\ge U/Q
\]
and the smallest upper bin \(u\) with
\[
\overline{\cos^2\alpha_u}\le L/Q.
\]
Monotonicity and (4) give the explicit witness
\[
l\pi/(2K)\le d(P,C_m)\le u\pi/(2K).                  \tag{5}
\]
Both witness inequalities are saved indirectly through the complete sample and table endpoints and are checked again by the reader. The constructor uses binary searches on the monotone envelopes.

At the actual parameters, all vertex and axis cosine requests are already entries in the 4,097-row table, so the saved extra-cosine array is empty. This is a property of this input, not an assertion about every supported parameter combination.

## 6. The one actual constructor and its retained consumer

The input is:
```json
{
  "m": 4,
  "height_bands": 256,
  "longitude_bands": 64,
  "angle_bins": 4096,
  "fraction_bits": 48
}
```

Every actual sample has adjacent distance bins, of width \(\pi/8192\). The lower and upper bin sums are 12,176,228 and 12,192,612. Dividing by \(2KMJ=134217728\) gives the two coefficients of \(\pi\) bounding the midpoint average. Subtracting/adding (3), with error \(\pi/256\), yields the reduced mean fractions at the start of this guide.

The constructor ran once in the connected JavaScript runtime, with one observed elapsed time of 873 ms. A separate fresh context opened the saved snapshot in 64 ms and answered the 16 retained public queries in 36 ms. These are single execution observations, not a statistical benchmark or a portable latency promise.

| Retained operation or object | Actual count |
| --- | ---: |
| Samples constructed and retained | 16,384 |
| Cosine table rows retained | 4,097 |
| Additional cosine records | 0 |
| Vertex rows retained | 8 |
| Interior cosine polynomials evaluated | 4,095 |
| Nonconstant Taylor terms evaluated | 98,280 |
| Vertex dot products | 131,072 |
| Arc support pairs | 131,072 |
| Interval square roots | 258 |
| Constructor angle-bin comparisons | 393,231 |
| Reader aggregate additions | 32,768 |
| Reader stored bin-witness comparisons | 32,768 |
| Saved public queries | 16 |
| Samples returned by those queries | 32 |
| Cosine rows returned by those queries | 7 |
| Threshold compilations / cache hits | 1 / 4 |

The saved reader made zero new Machin or arctangent series evaluations, cosine polynomials, interval multiplications, interval squares, square roots, sample constructions, vertex dot products, arc support computations or angle-bin searches. Its retained-witness checks and query comparisons are real new reader work and are accounted for separately. The counters describe selected operations, not every processor instruction.

The finite threshold query at distance \(\pi/10\) returns:

| Certified midpoint category | Count | Meaning |
| --- | ---: | --- |
| `at_most` | 9,523 | Saved upper distance bound is at most \(\pi/10\). |
| `greater` | 6,850 | Saved lower distance bound is strictly greater than \(\pi/10\). |
| `unresolved` | 11 | The saved interval does not certify either category. |

Thus the true number of these particular midpoints at distance at most \(\pi/10\) lies between 9,523 and 9,534. These are finite midpoint counts, not certified continuous surface-area proportions. The unresolved category is not a claim of equality to the threshold.

The retained queries include both endpoint sample pages, a terminal cosine page, three individual samples, two category selections, all eleven unresolved records and a category rank. For example, sample 16,383 has \(z=511/512\), \(\theta=127\pi/512\), and distance in \([2159\pi/8192,2160\pi/8192]\); it has rank 6,849 among the certified greater-than-\(\pi/10\) samples. Ranking is by row-major sample index, not by distance.

## 7. Public interface

The module is pure CommonJS, with no I/O, dependencies, random sampling or floating transcendental calls:
```js
const {
  compileOrthogonalZigzagMean,
  openRetainedSphericalMean,
  SPHERICAL_MEAN_LIMITS
} = require("./spherical_curve_mean.cjs");
```

`compileOrthogonalZigzagMean(input)` constructs one bounded family member and returns an index. `openRetainedSphericalMean(snapshot)` opens the saved constructor snapshot and returns the same query interface, with reader work counters. Input objects are not mutated; returned data and snapshots are copies.

In a connected V8 environment where the module and JSON texts have already been obtained:
```js
const module = { exports: {} };
new Function("module", "exports", moduleText)(module, module.exports);

const delivery = JSON.parse(dataText);
const index = module.exports.openRetainedSphericalMean(delivery.snapshot);

index.meanDecimal(9);
// lower: "0.272733338", upper: "0.297660527", unit: "radians"

index.infimumBracket(9);
// lower: "0.244978663", upper: "0.297660527"
// optimum_or_attainment_proved: false

index.thresholdCounts("1", "10");
// counts: { at_most: 9523, greater: 6850, unresolved: 11 }

index.pageThreshold("1", "10", "unresolved", 0, 32);
// all eleven records; next: null
```
These calls are examples of the already retained reader consumer; they are not a request to replay the constructor.

| Method | Contract |
| --- | --- |
| `summary()` | Parameters, sizes, exact mean coefficients and finite scope. |
| `curve()` | Symbolic curve definition, length metadata and saved coordinate enclosures. |
| `meanEnclosure()` | Exact rational multiples of \(\pi\), the pi interval and fixed-point scale. |
| `meanDecimal(digits = 6)` | Outward decimal endpoints in radians; 0 through 18 digits. |
| `infimumBracket(digits = 6)` | Universal lower endpoint and this feasible curve's upper endpoint, with no optimum/attainment assertion. |
| `sample(i, j)` | One sample by zero-based height and longitude indices. |
| `page(start = 0, count = 64)` | Sample records in row-major order, with total and next offset. |
| `cosinePage(start = 0, count = 64)` | Consecutive cosine-table records, including their rational angles. |
| `thresholdCounts(n, d)` | Counts in the three certified categories for threshold \(\pi n/d\). |
| `selectThreshold(n, d, type, rank)` | Sample at zero-based rank within one category. |
| `rankThreshold(n, d, type, sampleIndex)` | Membership, rank when present, and insertion rank otherwise. |
| `pageThreshold(n, d, type, start = 0, count = 64)` | A page within one category, ordered by sample index. |
| `snapshot()` | A complete copied snapshot. |
| `work()` | A copied counter record for this index instance. |

Threshold numerators and denominators accept safe nonnegative integer Numbers, nonnegative BigInts, or canonical nonnegative decimal strings with at most 128 digits. Require \(d>0\) and \(0\le n/d\le1/2\). The fraction is reduced before caching. The exact category names are `at_most`, `greater` and `unresolved`.

Page offsets and category ranks accept the same bounded nonnegative integer formats. A page may start at the family size and then returns an empty terminal page; selection requires rank strictly below the family size. A missing category membership returns `rank: null` and an insertion rank. Individual sample coordinates and `sampleIndex` must be safe integer Numbers in range. A page count is an integer from 1 through 256. At most 16 threshold classifications are cached; the oldest cache entry is evicted when a new distinct threshold would exceed that bound.

| Constructor parameter | Supported range |
| --- | --- |
| `m` | Integer 3 through 16 |
| `height_bands` | Integer 1 through 512 |
| `longitude_bands` | Integer 1 through 512 |
| Product of the two band counts | At most 16,384 |
| `angle_bins` | Integer 64 through 4,096 |
| `fraction_bits` | Integer 40 through 64 |

All constructor parameters must be safe integer Numbers. There are hard caps of 128 terms per reciprocal-arctangent series and 24 nonconstant cosine Taylor terms. Unsupported sizes and malformed input are rejected. These bounds are implementation limits, not mathematical restrictions on the family or the source question.

## 8. Complete saved representation and reader trust boundary

The delivery wrapper has schema `commons.kimberling10.eight_arc_mean_delivery.v1`. Its `snapshot` has schema `commons.orthogonal_spherical_zigzag_mean.v1`. The complete JSON also retains source provenance, the exact input, the constructor observation, all reader requests and responses, their separate counters, and the execution-scope statement.

To avoid a large repeated-key object for every sample, the snapshot uses fixed-width lowercase hexadecimal strings. Let
\[
w=\lceil(\texttt{fraction\_bits}+1)/4\rceil,\qquad
b=\text{number of hexadecimal digits of }K.
\]
The extra bit in \(w\) permits the exact value \(Q\), representing one.

| Encoded row | Fields in order |
| --- | --- |
| Sample | support-square lower [\(w\)], support-square upper [\(w\)], lower angle bin [\(b\)], upper angle bin [\(b\)] |
| Cosine | cosine lower [\(w\)], cosine upper [\(w\)], monotone cosine-square lower [\(w\)], monotone cosine-square upper [\(w\)] |

For the actual data, \(w=13\), \(b=4\); sample strings have 34 characters and cosine strings 52. The sample index is implicit: \(iJ+j\). The cosine index is its array index \(i\), corresponding to \(i\pi/(2K)\). No sample, table row or actual query response has been omitted.

The snapshot separately retains all eight vertex interval triples; the \(a,b,a^2,b^2,\cos(\pi/m)\) boxes; height and longitude nodes; the symmetry and exact length descriptions; the Machin and universal-arctangent records; the common Taylor remainder; any extra cosine records; the sample aggregate; and the constructor work record.

The reader checks the complete array lengths, parameter/scale bindings, hexadecimal widths and ranges, interval order, monotone cosine-square envelopes and exact endpoints. For every sample it checks both saved angle-bin witness inequalities against the table. It sums all lower and upper bin indices and checks the mean aggregation and quadrature coefficients. It also checks the shapes and bindings of the pi and universal intervals, curve size and length metadata, coordinate boxes, grid centers, symmetry size, extra-angle records, and source/work objects.

Those are structural and retained-bound checks. The reader does **not** recompute the Machin, Taylor or arctangent series; establish mathematical truth from an arbitrary pi field; prove arbitrary saved vertices orthogonal or their loop simple; recalculate coordinate radicals, dot products or arc maxima; or authenticate a Git source identity. Its mathematical interpretation relies on the identified constructor output and the derivations above. A fabricated snapshot is not independently certified merely because it passes this loader.

The distinction makes reuse possible: opening the actual saved index performs no trigonometric or sample geometry reconstruction. A new threshold requires a bounded scan of the saved intervals; later queries for that threshold use its cached, ordered index. Mean and curve queries use retained values, sample and cosine pages decode only requested records, and category rank uses binary search within the saved threshold group.

## 9. Source identity and execution boundary

The exact executed module is `spherical_curve_mean.cjs`, 26,315 UTF-8 bytes, Git blob **6044152becaa47a9763a441f3913a1e3f0551e24**. It was unchanged between the single constructor run and the fresh reader run. The complete data file `eight_arc_mean_grid256x64.json` is 924,868 UTF-8 bytes, Git blob **e4c40f0ec160b07f53f3d873ab20afc909d5a8b1**. The mathematical payload contains its own executed-source identity.

The actual consumer is only \(m=4,M=256,J=64,K=4096,\texttt{bits}=48\), followed by the 16 saved-reader queries. The other allowed \(m\), grid sizes, bin counts and precisions, extra-cosine paths, cache eviction, malformed/size-rejection branches, empty/end pages and further threshold values were source-inspected rather than executed. The actual terminal pages in the retained consumer were executed; the distinct empty-at-end branch was not.

No earlier geometry, published enumeration, accepted prime basis, or predecessor computation was replayed for this artifact. No native process, external package, random sample or floating transcendental result is used. The guide supplies a feasible exact-length construction, a universal analytic lower bound, and the finite interval evaluation; it does not turn a finite sample into proof of a globally minimizing curve.

Original narrow claim: `C0C3MEWHTR6 / 1789714992.581159 / 1791149251.958419`.
