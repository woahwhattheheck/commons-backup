# Exact finite Lagrange interpolation and Lebesgue bounds

This package compiles a finite interpolation operator from strictly increasing integer coordinates, affinely normalizes its nodes to [-1,1], and encloses its uniform operator norm with exact rational arithmetic. It retains cardinal polynomials, every sign-fixed Lebesgue piece, a complete Bernstein subdivision tree and all query outputs. The saved reader evaluates new data without rebuilding the constructor.

For the actual thirteen-node input, the norm lies in the outward decimal interval
\[
\boxed{672.216472773058\ \le \|P\|_\infty
       \ \le 672.216472987746}.
\]
The exact rational gap is below 10^-6. Only 14 subdivisions were needed, against the fixed budget of 128. The sampled lower-bound point is x*=365241/2136064; it is not claimed to be a global maximizer.

## Source and problem boundaries

[Berrut and Trefethen, *Barycentric Lagrange Interpolation*, SIAM Review 46(3) (2004), 501–517](https://people.maths.ox.ac.uk/trefethen/barycentric.pdf), DOI 10.1137/S0036144502417715, define cardinal Lagrange interpolation at distinct real nodes. Section 9.1 identifies the uniform interpolation-operator norm with the maximum of the sum of absolute cardinal values. Their paper is also a source for the distinction between interpolation conditioning and floating-point evaluation methods; this package does not claim a new interpolation formula or general numerical-stability result.

[Garloff, *The Bernstein Algorithm*, Interval Computations (1993), No. 2, 154–168](https://interval.louisiana.edu/reliable-computing-journal/1993/interval-computations-1993-2-pp-154-168.pdf), Sections 1.1–1.2, supplies the established Bernstein coefficient range bounds and subdivision context. The present univariate rational implementation and complete finite tree apply that classical method. It uses maximum coefficients for upper bounds and attained sample values for lower bounds.

The [PPL128 catalogue card](https://prizeproblems.org/problems/128/) describes two questions associated with Erdős 671. For rows of n distinct nodes in [-1,1], write L_n f for interpolation and lambda_n(x) for the sum of absolute cardinal values. The first asks for a row sequence such that every continuous f has some x where lambda_n(x) has infinite limsup while L_n f(x) converges to f(x). The second requires infinite limsup at every x, while still asking that every continuous f have some convergence point.

Those are infinite-row assertions with quantifiers over all continuous functions. One finite operator and two concrete nodal data vectors establish neither assertion. The exact FormalConjectures671 contents route returned 404 and the canonical671 web page returned 403, each once; both remain held without retry. No original problem statement was recovered through those routes, and this guide makes no independently verified current-status assertion. The card's dated status is not promoted to primary mathematical evidence.

## Input and normalization

The one actual input is
\[
b=[1,13,32,66,169,174,396,416,756,858,915,1016,1044].
\]
These numbers were already retained at:

- repository: woahwhattheheck/commons;
- commit: 32ff6fc62fc7f43f5b424b0d0c78b5d7e7a1618c;
- path: research/ppl009_erdos241_b3/prime13_saved_triple_decoding.json;
- blob: 43aa8d6f6599221292acba0e57b488642c4c3598;
- JSON member: opened_summary.positive_values.

Only the coordinate values are used. Their B3 property, finite-field construction, affine-orbit result and decoder are irrelevant to the interpolation argument and are not replayed.

For general supplied coordinates b0<...<b_(n-1), set
\[
x_i=\frac{2b_i-b_0-b_{n-1}}{b_{n-1}-b_0},\qquad
z=\frac{(b_{n-1}-b_0)x+b_0+b_{n-1}}2.
\]
The first and last normalized nodes are -1 and 1. A polynomial's uniform range and the interpolation norm are unchanged by this bijective affine coordinate change. The compiler stores power coefficients in z, which keeps the input factors integral. The actual normalized nodes are (2b_i−1045)/1043, and every reduced rational node is saved.

No optimization over possible node sets is performed. The relatively large norm describes this specified node distribution, not a best or worst value over all thirteen-node configurations.

## Exact polynomial construction

With d=n−1, the ith cardinal polynomial is
\[
\ell_i(z)=\frac{\prod_{j\ne i}(z-b_j)}
                 {\prod_{j\ne i}(b_i-b_j)}.
\]
It has degree at most d, equals one at b_i and zero at every other node. A degree-at-most-d interpolant with supplied values v_i is therefore P_v(z)=sum_i v_i ell_i(z). Uniqueness follows because the difference of two such interpolants has n distinct roots.

The constructor retains the integer numerator coefficients and a positive denominator for every cardinal polynomial. If the product denominator is negative, it changes the sign of all numerator coefficients. It does not sample or numerically invert a Vandermonde matrix.

The Lebesgue function is
\[
\lambda(z)=\sum_i|\ell_i(z)|.
\]
On an open knot interval (b_k,b_(k+1)), no cardinal polynomial has an interior root, so its sign is constant. In the implementation's zero-based indexing,
\[
s_{k,i}=(-1)^{k+i+\mathbf 1_{i>k}}.
\]
This follows by counting the negative factors in the numerator and denominator. Hence lambda equals the single polynomial
\[
Q_k(z)=\sum_i s_{k,i}\ell_i(z)
\]
throughout that interval. Continuity extends the identity to both endpoints. The n−1 closed pieces cover the entire node interval, meeting only at endpoints. The construction stores each sign vector and the exact integer-coefficient/common-denominator representation of Q_k.

For this input there are thirteen cardinal polynomials of degree at most twelve and twelve Lebesgue pieces. No assertion that lambda itself is one global polynomial is made.

## Bernstein bounds and the retained subdivision tree

For one piece with z=a+w t, 0<=t<=1 and w>0, expand
\[
Q(a+wt)=\sum_{j=0}^d A_j t^j
       =\sum_{i=0}^d \beta_i {d\choose i}t^i(1-t)^{d-i}.
\]
The exact transformation used is
\[
A_j=w^j\sum_{q=j}^d {q\choose j}c_q a^{q-j},\qquad
\beta_i=\sum_{j=0}^i A_j\frac{{i\choose j}}{{d\choose j}},
\]
with the polynomial's common denominator carried separately.

The power-to-Bernstein identity is elementary: substituting the formula for beta and using
\[
{d\choose i}{i\choose j}={d\choose j}{d-j\choose i-j}
\]
reduces the coefficient of A_j to t^j by the binomial theorem. The Bernstein basis functions are nonnegative on [0,1] and sum to one. Thus Q is a convex combination of the beta_i at every point and never exceeds max_i beta_i. The endpoint values are exactly beta_0 and beta_d.

The compiler begins with one interval for each sign-fixed piece. It repeatedly chooses a current leaf with greatest upper bound, keeping the first encountered in a tie, and bisects that interval. Exact de Casteljau averaging gives the Bernstein coefficients of both halves. At averaging level r, the integer numerator row has implicit denominator 2^r D. Scaling boundary entries to the common denominator 2^d D gives the two child rows, after a common gcd reduction.

Every child replaces its parent interval, so the current leaves still cover the full domain. The maximum of all leaf coefficient upper bounds is a global upper bound U. Endpoints of the initial and newly created intervals are actual sample points; their largest polynomial value is a lower bound L. A full rational comparison checks U−L against the requested tolerance. Each step retains its selected parent, two children, global bounds, best sample and upper-bound leaf.

The loop stops with:

- TOLERANCE_MET when U−L is at most the positive requested tolerance;
- SPLIT_BUDGET when the fixed number of subdivisions is exhausted;
- DEPTH_BUDGET when the leaf controlling the upper bound reaches the fixed maximum depth.

All three outcomes retain valid finite bounds and a complete tree. A budget stop is not silently converted into tolerance success, and no input in this package was rerun with a larger budget.

## Operator norm and an explicit continuous witness

For any f in C[-1,1],
\[
|Pf(x)|\le \|f\|_\infty\sum_i|\ell_i(x)|
          \le \|f\|_\infty\max_x\lambda(x).
\]
Conversely, fix any point x*. Set v_i=-1 if ell_i(x*)<0 and v_i=1 otherwise, including zeros. Linearly interpolate these nodal values between consecutive normalized nodes. This defines a continuous piecewise-linear function f with ||f||_infinity=1, since each segment remains between its endpoints and every nodal value is either -1 or 1. At x*,
\[
Pf(x^*)=\sum_i v_i\ell_i(x^*)=\lambda(x^*).
\]

At the retained sample point this gives the exact attained lower bound L. It does not assert that ||Pf|| is exactly L, or that x* maximizes lambda. The saved global upper bound U applies to this witness as it does to every unit-norm input. Abstractly, continuity of lambda supplies a maximizing point; applying the same reasoning there proves ||P||=max lambda, consistent with the cited literature.

The reader returns the exact nodal signs, all cardinal values at the sampled point, and the slope/intercept of each continuous linear segment. It also evaluates the interpolants of the separate source function |x|. These are actual data-vector computations; no convergence conclusion is extrapolated.

## Public CommonJS interface

lagrange_lebesgue.cjs has no dependencies, file I/O, network calls or process execution. It works in a CommonJS host or a connected JavaScript isolate.

~~~js
const { compileLebesgue, openLebesgue } = require("./lagrange_lebesgue.cjs");

// For a new finite row:
const snapshot = compileLebesgue(integerCoordinates, {
  source_id: "coordinate provenance",
  max_splits: 128,
  tolerance: ["1", "1000000"]
});

// Reuse the published result without constructing it again:
const api = openLebesgue(savedRecord.snapshot);
const bounds = api.bounds(12);
const witness = api.nodalWitness(bounds.best_x);
const value = api.interpolate(["0", "1"], witness.nodal_values);
~~~

The published saved record is thirteen_node_lebesgue.json. The caller supplies its parsed contents; the module itself does not load files.

### Input and output contracts

compileLebesgue requires 2 through 16 strictly increasing safe-integer Number coordinates, each with absolute value at most 1,000,000. They are automatically mapped to [-1,1]. A single-node row, duplicate coordinates and arbitrary unsorted inputs are outside this constructor contract. Rational node families with a common affine integer representation can be supplied through those integer coordinates when they meet the bounds.

Rational API arguments are pairs [numerator,denominator]. Each component may be a safe integer Number, BigInt or canonical signed decimal string. Denominators must be positive. Fractions are normalized by gcd for arithmetic; all returned rational components are decimal strings. Queries accept only x in [-1,1]. There is no floating-point approximation inside polynomial or range arithmetic.

| Method | Result |
| --- | --- |
| summary() | Input nodes, normalized coordinates, degree, tree sizes and saved exact result |
| bounds(places=8) | Saved rational bounds and outward-rounded decimal strings |
| evaluate(x) | Every exact cardinal value and their absolute-value sum |
| interpolate(x,values) | Exact interpolation of one supplied rational nodal data vector |
| nodalWitness(x) | Signs, cardinal values, exact continuous linear segments and sampled amplification |
| nodePage(start=0,count=32) | Saved tree-node records |
| piecePage(start=0,count=32) | Saved sign vectors and power coefficients |
| stepPage(start=0,count=32) | Saved subdivision history and global bounds |
| leafPage(start=0,count=32) | Final partition leaves in retained order |
| stats() | Current reader arithmetic and construction counters |
| snapshot() | An outward deep copy of the saved certificate |

Page starts are zero-based indices, and counts are at most 64. The polynomial degree is n−1 for n nodes, even when a particular coefficient vanishes. A cardinal query at a knot is handled by exact polynomial evaluation, with no division by x−x_i.

Saved evaluation uses Horner's rule in the integer coordinate z. It is fresh query arithmetic, not construction replay. Up to 256 distinct query points are cached, using their reduced rational key; the oldest inserted point is removed when that capacity is reached. Reusing a point for another nodal vector avoids reevaluating the cardinal polynomials.

bounds rounds the lower endpoint down and upper endpoint up using integer quotient/remainder arithmetic. Its decimal strings are enclosing bounds, not rounded-to-nearest estimates. It accepts at most 100 decimal places.

Returned records and arrays are copies or fresh output. openLebesgue deep-copies its input, so changing an input object or later output does not mutate its private certificate.

### Saved-reader validation boundary

The loader checks schema, bounded integer-node order, row dimensions, signed-integer formats, positive denominators, basic tree identities and index ranges, unique listed leaves, leaf child-null status and lower/upper order. It reads all stored Bernstein numerator rows structurally.

It does not re-form cardinal factors, rederive sign pieces, transform powers, subdivide, prove partition completeness, recheck every saved arithmetic relation or authenticate arbitrary externally edited data. In particular, valid array dimensions and references do not establish the mathematical meaning of coefficients or bounds. Accurate answers require the retained authentic constructor result. Structural loading is not a second proof or independent certificate verifier.

The piece table and historical step records are exposed as retained data; they are not used to rebuild the active arithmetic. Runtime input validation and finite resource limits describe the contract only.

## Actual computation

The one constructor used the retained thirteen coordinates, 128 permitted subdivisions and tolerance 1/1,000,000. It stopped at TOLERANCE_MET after 14 subdivisions.

| Quantity | Actual value |
| --- | ---: |
| Cardinal polynomials | 13 |
| Root-factor coefficient updates | 1014 |
| Sign-fixed pieces | 12 |
| Power-to-Bernstein summands | 1092 |
| Subdivision calls | 14 |
| Subdivision additions | 1092 |
| Total tree nodes | 40 |
| Final leaves | 26 |
| Recorded global-bound stages | 15 |
| Leaf-upper comparisons | 270 |
| Constructor gcd calls | 1109 |

The best integer-coordinate sample is z*=2505401/4096, corresponding to normalized x*=365241/2136064. The exact rational lower, upper and gap are stored in snapshot.result. The outward 12-place interval is [672.216472773058,672.216472987746]; its width is below 10^-6.

The fresh saved reader made thirteen actual queries:

1. summary and outward bounds;
2. all cardinal values at x* and the continuous sign witness there;
3. that witness's interpolant at zero;
4. cardinal values at zero and the actual seventh knot;
5. the interpolant to |x| at zero and at 1/3;
6. complete piece, leaf and stage pages, plus the last fourteen tree nodes.

The witness signs, in knot order, are
[-1,1,-1,1,-1,1,-1,1,1,-1,1,-1,1].
Its computed value at x* is exactly the retained constructor lower fraction. This comparison is part of producing the requested finite witness, not an independent replay of the entire polynomial construction.

There were four new cardinal evaluations, 624 Horner steps and three cache hits. Reader arithmetic performed 2321 gcd operations, 743 rational additions, 679 multiplications and 68 divisions. Cardinal construction, root-factor updates, sign-piece construction, power-to-Bernstein conversion and subdivision counters were all zero. All forty tree nodes were structurally read.

The |x| interpolant's exact value at zero is retained as
\[
\frac{174528012814173155494502917871471472820161067010699420886005383817}
{3034427372856089123687596047415271583403629283071778888384512000000}.
\]
This is a finite interpolation value for that continuous function and row; it is not a convergence estimate for a sequence of rows.

The observed constructor time was 12 ms and the fresh reader opening time 1 ms in this one connected V8 execution. No benchmark, alternative-input trial or test suite was run. Unused budget/error branches, larger node counts and cache eviction were inspected as source only.

## Complete storage and limits

The frozen executed source is e04ba0da15fb4760d263d58fe7becd28b92c68df, 15353 UTF-8 bytes. It was checkpointed before the actual construction. The complete initial packet is 1c52ab68b1251465b10931a46a69363833bac9ca, 87828 bytes.

thirteen_node_lebesgue.json contains the complete input/source record, all cardinal and piece coefficients, all forty tree nodes, every global-bound stage, the final partition, all thirteen reader outputs and their arithmetic counters. Its compact JSON is 184144 bytes, blob e7c402bc1f80391f429c19a51446db3b678c15a9. The full tree is retained even though only its leaves are needed for the final global upper bound.

Hard limits are: 16 nodes, coordinate magnitude 1,000,000, 512 requested splits, depth 48, 4096 digits in reduced fractions/coefficient groups, 1024 digits in external rational components, 16,000,000 snapshot characters, 64 records per page and 256 cached points. The actual request used 128 splits; the package does not silently escalate that budget. Costs include BigInt operand length and gcd work, not just a count of arithmetic operations.

For n nodes, factor expansion takes O(n^3) scalar coefficient work, there are n−1 pieces of degree at most n−1, each subdivision takes O(n^2) additions, and the simple selection policy scans the current leaves. The saved reader evaluates n degree-(n−1) polynomials in O(n^2) rational arithmetic operations at a new point, then reuses them for new nodal vectors. These are implementation costs, not claimed optimal complexity.

This is a finite numerical-analysis capability with exact arithmetic and classical source attribution. It makes no assertion about the infinite Erdős 671 row schemes, a globally optimal node set, new mathematical priority, a prize or a sponsor submission.
