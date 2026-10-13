# Element-bubble residual lift

Issue: https://github.com/woahwhattheheck/commons/issues/14999

`cell_bubble_lift.py` constructs the exact last, element-local part of a
degree-four or degree-five divergence lift. On a positive Kuhn tetrahedron it
maps every pressure polynomial with zero vertex/edge Bernstein coefficients
and zero cell mean to a velocity whose trace is zero on all four faces.

The inverse is explicit. Its source dimension is three at degree four and
twelve at degree five. The constructor covers all six positively ordered
tetrahedra returned by `kuhn.py`, using exact rational arithmetic and the
existing native Bernstein order. Each output contains the sparse inverse,
complete pressure source basis, physical coefficient nodes, full divergence
identities and a conservative bound in the pressure L2 norm.

This component can be extended by zero to other elements. Complete mesh
assembly, the compatibility of its preceding stages and the full uniform
inf-sup theorem remain separate work.

## Run and reuse

Python 3.10+, standard library only. The runtime imports only
`kuhn.py` and the index/cross-product definitions in
`p4_mean_repair.py`; it does not run a mean-repair elimination or load a
retained mean basis.

```sh
python research/ridgway_freudenthal/cell_bubble_lift.py \
  --degree 4 --all-cells --origin=-2,1/3,5/2 --scale 3/2 \
  --output quartic-cell-bubbles.json

python research/ridgway_freudenthal/cell_bubble_lift.py \
  --degree 5 --all-cells --origin=2/7,-3,5/2 --scale 2/3 \
  --output quintic-cell-bubbles.json

python research/ridgway_freudenthal/cell_bubble_lift.py \
  --degree 4 --cell 0 --free-trace=1,-2,3
```

Numbers are integers or rational strings. The origin and pressure arguments
use comma-separated values; using `--origin=...` or
`--free-trace=...` also keeps negative fractions unambiguous to the
argument parser. Scale must be positive. `--trace` accepts all 20 cubic or
35 quartic pressure coefficients, including their required zero entries.
`--free-trace` accepts the three or twelve independent coefficients
listed below. Explicit data requires a single `--cell`; a batch builds
all six operators and applies the displayed alternating independent example
`1,-2,3,...` to each one. Without an output path, JSON goes to stdout.
A specified output path must be new; failures exit nonzero with a clear
message, and incompatible pressure is rejected before an output is opened.

For a caller that already holds per-cell residuals:

```python
from research.ridgway_freudenthal.cell_bubble_lift import (
    construct, construct_reference, transport, trace_from_free, apply,
)

operator = construct(5, cell_index=4, origin=("2/7", "-3", "5/2"),
                     scale="2/3")
pressure = trace_from_free(operator, [
    "1/2", "-2/3", "3/4", "-4/5", "5/6", "-6/7",
    "7/8", "-8/9", "9/10", "-10/11", "11/12", "-12/13",
])
velocity = apply(operator, pressure)
```

`apply` also consumes an operator loaded from its saved JSON.
`construct_reference(k, cell_index)` returns the unit-cell map;
`transport(reference, origin, scale)` places it without modifying the
reference. Transport accepts a unit reference loaded from JSON. Repeated
transport of an already translated/scaled map is rejected.

## Coefficients and full source image

Write a positively oriented tetrahedron as
\(T=[v_0,v_1,v_2,v_3]\), with barycentric coordinates \(\lambda_i\) and
gradients \(g_i=\nabla\lambda_i\). The normalized degree-\(n\) Bernstein basis is

\[
B_\alpha^n=\frac{n!}{\alpha_0!\alpha_1!\alpha_2!\alpha_3!}
\prod_{i=0}^3\lambda_i^{\alpha_i},\qquad |\alpha|=n.
\]

The output coefficients multiply these polynomials; they are not values of
the polynomial at coefficient nodes. For
\(v=\sum_{|\alpha|=k}c_\alpha B_\alpha^k\),

\[
(\operatorname{div}v)_\beta
=k\sum_{i=0}^3g_i\cdot c_{\beta+e_i}.
\]

A velocity with zero trace on every tetrahedron face has only coefficients
whose four alpha entries are positive. Conversely, those coefficients
define a polynomial vanishing on every face. At degrees four and five this
space has dimensions \(3\) and \(12\), respectively.

A pressure vanishes on every tetrahedron edge exactly when all its
coefficients with at most two positive beta entries vanish. Every normalized
degree-\(n\) basis polynomial has cell average
\(1/\binom{n+3}{3}\). Thus the remaining mean condition is exactly the sum of
all pressure coefficients equal to zero, separately on each cell.

The native order from `indices(n)` increments alpha0, then alpha1, then
alpha2; alpha3 is the remainder. Every row number below is zero-based.

| Velocity degree | Full pressure rows | Surviving pressure rows | Dependent row | Free pressure rows |
| --- | ---: | --- | ---: | --- |
| 4 | 20 | 5, 11, 13, 14 | 5 | 11, 13, 14 |
| 5 | 35 | 6, 7, 10, 16, 17, 19, 20, 21, 22, 23, 26, 28, 29 | 20 | 6, 7, 10, 16, 17, 19, 21, 22, 23, 26, 28, 29 |

Each column of `source_basis` is the full pressure vector
\(e_{\text{free row}}-e_{\text{dependent row}}\). The other 16 or 22
vertex/edge rows are zero. A caller cannot supply nonzero edge data or
replace the cell-wise zero-mean condition with a global zero-sum condition.

## Quartic inverse

The only positive velocity multi-index is \(\alpha=(1,1,1,1)\), row 20 in
the complete degree-four index array. Its vector coefficient is \(c\).
Let \(q_j\) denote the pressure coefficient at \(\beta=\mathbf1-e_j\).
The four rows in the table above are \(j=0,1,2,3\), in that order.

\[
q_j=4g_j\cdot c,\qquad \sum_{j=0}^3q_j=0.
\]

Choose the three free values \(q_1,q_2,q_3\). The unique inverse is

\[
c=\frac14\sum_{j=1}^3q_j(v_j-v_0),\qquad
q_0=-q_1-q_2-q_3.
\]

The identity
\(g_i\cdot(v_j-v_s)=\delta_{ij}-\delta_{is}\)
proves every divergence row directly. Independence follows from the three
linearly independent vectors \(v_j-v_0\). The single displayed coefficient
node has coordinate \(N=\sum_i v_i\), where the actual node is \(N/4\).
The physical polynomial is \(24c\lambda_0\lambda_1\lambda_2\lambda_3\).

## Quintic inverse

The four positive velocity multi-indices are
\(\alpha=\mathbf1+e_s\). Denote their vector coefficients by \(c_s\).
For each \(j\ne s\), set
\(q_{j,s}=q_{\mathbf1+e_s-e_j}\); these are the twelve free face-interior
pressure coefficients. Let \(q_*=q_{\mathbf1}\) be the remaining interior
pressure coefficient.

\[
q_{j,s}=5g_j\cdot c_s,\qquad
c_s=\frac15\sum_{j\ne s}q_{j,s}(v_j-v_s),
\]

\[
q_*=5\sum_s g_s\cdot c_s
=-\sum_s\sum_{j\ne s}q_{j,s}.
\]

The same barycentric identity proves the twelve free rows and the dependent
row. For each fixed \(s\), the three vectors \(v_j-v_s\) are independent,
so this is the unique inverse on the complete zero-face-trace velocity
space.

The output follows native order, not s-major order:

| Free pressure row | beta | Missing j | Doubled s |
| ---: | --- | ---: | ---: |
| 6 | (0,1,1,2) | 0 | 3 |
| 7 | (0,1,2,1) | 0 | 2 |
| 10 | (0,2,1,1) | 0 | 1 |
| 16 | (1,0,1,2) | 1 | 3 |
| 17 | (1,0,2,1) | 1 | 2 |
| 19 | (1,1,0,2) | 2 | 3 |
| 21 | (1,1,2,0) | 3 | 2 |
| 22 | (1,2,0,1) | 2 | 1 |
| 23 | (1,2,1,0) | 3 | 1 |
| 26 | (2,0,1,1) | 1 | 0 |
| 28 | (2,1,0,1) | 2 | 0 |
| 29 | (2,1,1,0) | 3 | 0 |

The four velocity index rows are 27, 28, 31 and 41, with alpha values
\((1,1,1,2),(1,1,2,1),(1,2,1,1),(2,1,1,1)\), hence
\(s=3,2,1,0\). Each output node has three scalar rows in x,y,z order.
Its coordinate multiplied by five is \(N_s=\sum_i v_i+v_s\).
The physical polynomial is
\(60\lambda_0\lambda_1\lambda_2\lambda_3\sum_s\lambda_s c_s\).

## All six Kuhn cells and physical transport

The existing positive order always has \(v_0=(0,0,0)\) and
\(v_3=(1,1,1)\). It supplies:

| Cell index | v1 | v2 |
| ---: | --- | --- |
| 0 | (1,0,0) | (1,1,0) |
| 1 | (1,0,1) | (1,0,0) |
| 2 | (1,1,0) | (0,1,0) |
| 3 | (0,1,0) | (0,1,1) |
| 4 | (0,0,1) | (1,0,1) |
| 5 | (0,1,1) | (0,0,1) |

No separate coefficient inverse is needed for those shapes. The formulas
use their actual ordered vertices. Each reference scalar matrix has shape
\(3\times3\) with six nonzeros at degree four, or \(12\times12\) with
twenty nonzeros at degree five.

For \(x=a+h\xi\), \(h>0\), transport maps the cell vertices to \(a+hv_i\),
a degree-k coefficient node \(N\) to \(ka+hN\), and velocity coefficients
to \(h c_\alpha\). Pressure coordinates remain unchanged, because the
factor h in velocity cancels the factor \(h^{-1}\) in barycentric
gradients. The squared H1 seminorm and the squared pressure L2 norm both
scale by \(h^3\).

The constructor rebuilds every physical pressure row for every inverse
column. It includes face-interior and element-interior rows, as well as
the protected vertex/edge rows. It also checks the zero cell mean and that
the only velocity nodes correspond to strictly positive alpha. It does
not substitute an edge-only reconstruction for the full residual identity.

## Explicit pressure-norm bound

Let z be the independent pressure-coordinate vector and let \(R\) be the
returned reference velocity matrix. Put

\[
M=\max_{\text{scalar rows }r}\sum_jR_{rj}^2.
\]

For each of the six unit Kuhn shapes,
\(\sum_i|g_i|^2=6\), and the explicit inverse gives \(M=3/k^2\).
For each velocity component, its gradient is a convex combination of
the degree-\((k-1)\) Bernstein derivative coefficients. Jensen's
inequality, Cauchy-Schwarz over the four barycentric gradients, and
\(|T|=1/6\) therefore give

\[
|v|_{H^1(T)}^2
\le \frac16\,3k^2\,4\,6\,M\,|z|^2
=36|z|^2.
\]

To replace coordinates by the pressure L2 norm, the constructor integrates
the pressure source basis exactly. For two degree-n Bernstein indices,

\[
\int_{T_{\rm ref}}B_\alpha^n B_\beta^n
=\frac{(n!)^2}{(2n+3)!}
\prod_{i=0}^3\frac{(\alpha_i+\beta_i)!}{\alpha_i!\beta_i!}.
\]

If d is the dependent row and \(f_i\) are the free rows, the independent
Gram matrix is

\[
G_{ij}=\int_T
(B_{\beta_{f_i}}^n-B_{\beta_d}^n)
(B_{\beta_{f_j}}^n-B_{\beta_d}^n).
\]

The independent basis functions are linearly independent, so G is
positive definite. The symmetric matrix \(G^{-1}\) has largest eigenvalue
at most its maximum absolute row sum \(\gamma\). Hence

\[
|z|^2\le\gamma\,z^\top Gz
=\gamma\|q\|_{L^2(T_{\rm ref})}^2.
\]

The exact matrices and their inverses are included in the output. Their
values yield:

| Velocity degree | M | Reference coefficient bound | gamma | Squared pressure-norm bound C |
| ---: | --- | ---: | --- | --- |
| 4 | 3/16 | 36 | 3150 | 113400 |
| 5 | 3/25 | 36 | 895725/17 | 32246100/17 |

For degree four, \(G=(I+J_3)/2520\), so
\(G^{-1}=2520I-630J_3\). For degree five the displayed exact 12-by-12
matrix inverse has the same absolute row sum \(895725/17\) in every row.

After transport, the coordinate bound becomes \(36h^3\), while the
inverse-Gram bound becomes \(\gamma/h^3\). Their factors cancel:

\[
|v|_{H^1(T)}^2\le C\|q\|_{L^2(T)}^2.
\]

These constants are conservative; no optimal eigenvalue is asserted.
Because distinct element interiors are disjoint and each velocity vanishes
on the entire cell boundary, summing these element-local lifts retains the
same pressure-norm bound for residuals satisfying the displayed conditions
on every cell. This conclusion concerns that residual subspace. The
preceding mean, vertex and edge stages still need their own complete
assembly and norm argument.
