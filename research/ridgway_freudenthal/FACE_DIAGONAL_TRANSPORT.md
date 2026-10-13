# Exact coordinate transport of the interior face-diagonal lift

This construction extends the accepted [reference face-diagonal lift](FACE_DIAGONAL_LIFT.md)
from [PR #30041](https://github.com/woahwhattheheck/commons/pull/30041) under
[the Freudenthal research issue](https://github.com/woahwhattheheck/commons/issues/14999).
The reference operator and source-space characterization in
[`face_diagonal_lift.py`](face_diagonal_lift.py) are the foundation. The argument
below transports that result to the three coordinate-normal orientations of the
same interior face-diagonal class, with exact translation and positive isotropic
scale.

## Geometry and ordering

Let the reference patch be
$$
\widehat\Omega=[0,2]\times[0,1]^2,
\qquad
\widehat e=[(1,0,0),(1,1,1)].
$$
Each of its two cubes has the standard six-tetrahedron Freudenthal/Kuhn
triangulation.

Write a coordinate permutation as a tuple `P`, with **reference component `i`
mapping to physical component `P[i]`**. Let $Q$ be its permutation matrix:
$Qe_i=e_{P[i]}$. This convention distinguishes the destination of a reference
component from the order in which physical components are read.

| `normal_axis` | `P` | $Q(\xi_0,\xi_1,\xi_2)$ | Shared physical face |
|---|---|---|---|
| `x` | `(0,1,2)` | $(\xi_0,\xi_1,\xi_2)$ | $x_0=a_0+h$ |
| `y` | `(1,2,0)` | $(\xi_2,\xi_0,\xi_1)$ | $x_1=a_1+h$ |
| `z` | `(2,0,1)` | $(\xi_1,\xi_2,\xi_0)$ | $x_2=a_2+h$ |

For an exact rational origin $a\in\mathbb Q^3$ and scale
$h\in\mathbb Q,\ h>0$, define
$$
F(\xi)=a+hQ\xi,\qquad
\Omega=F(\widehat\Omega),\qquad e=F(\widehat e).
$$
The patch has length $2h$ in the selected normal direction and length $h$ in
the other two directions. The ordered target endpoints are
$$
a+h\,e_{P[0]},
\qquad
a+h(1,1,1).
$$
The endpoint order is inherited, so every high-endpoint Bernstein power retains
its meaning.

A unit-cube Kuhn tetrahedron has a vertex chain
$$
0,\quad e_{\sigma(0)},\quad
e_{\sigma(0)}+e_{\sigma(1)},\quad (1,1,1),
\qquad \sigma\in S_3.
$$
A coordinate permutation maps this chain to the chain indexed by
$P\circ\sigma$. Since all six chains occur in each cube, coordinate
permutations preserve the underlying Kuhn triangulation. The three permutations
implemented here are cyclic, hence have determinant $+1$; translation and
positive scaling preserve the inherited tetrahedron orientation as well.

The implementation retains cell order, local vertex/barycentric order, shared
Bernstein-node order, and target-coordinate order. It does not sort the physical
cells or nodes again. Consequently the reference target cell labels **0, 1, 9,
11** still index the four incident physical tetrahedra, even when their
coordinate-lexicographic order would differ.

## Velocity and divergence transport

For a reference velocity $\widehat v$, set
$$
(\mathcal T\widehat v)(x)
  =hQ\,\widehat v\!\left(Q^T(x-a)/h\right).
$$
This maps continuous piecewise degree-$k$ vector fields on the reference patch
bijectively to such fields on the physical patch. Its inverse is
$$
(\mathcal T^{-1}w)(\xi)=h^{-1}Q^T w(a+hQ\xi).
$$
An affine map preserves polynomial degree and face sharing. The same formulas
also give a bijection of the spaces with zero patch-boundary trace.

Use the gradient convention $(\nabla v)_{ij}=\partial_j v_i$. The chain rule
gives, at $x=F(\xi)$,
$$
\nabla_x(\mathcal T\widehat v)(F(\xi))
   =hQ\,(\nabla_\xi\widehat v)(\xi)\,h^{-1}Q^T
   =Q(\nabla_\xi\widehat v)(\xi)Q^T.
$$
Taking the matrix trace proves the exact commutation identity
$$
\operatorname{div}_x(\mathcal T\widehat v)(F(\xi))
   =\operatorname{div}_\xi\widehat v(\xi).
$$
Thus divergence is transported as a scalar pullback, with no amplitude factor.
The factor $h$ in the velocity cancels the inverse length factor in its
derivatives.

In Bernstein coordinates the same identity follows from
$$
\lambda_i^{\rm phys}(F(\xi))=\widehat\lambda_i(\xi),
\qquad
\nabla_x\lambda_i^{\rm phys}=h^{-1}Q\nabla_\xi\widehat\lambda_i.
$$
For each cell and multi-index $\beta$, the divergence coefficient is
$$
d_{K,\beta}
   =k\sum_{i=0}^{3}\nabla\lambda_i\cdot v_{\beta+e_i}.
$$
Replacing each velocity coefficient by $hQv_{\beta+e_i}$ and each gradient by
$h^{-1}Q\nabla\widehat\lambda_i$ leaves this coefficient unchanged. These
identities apply to Bernstein coefficients, not sampled point values.

## Protected traces, means, and source compatibility

The target vector $y$ contains the interior coefficients of the
degree-$k-1$ divergence trace, in cell-major order **0, 1, 9, 11**. Within each
cell the high-endpoint powers are $1,\ldots,k-2$. There are eight coordinates
for degree four and twelve for degree five.

Because the scalar polynomial on every transported edge has the same Bernstein
coefficients, the target vector is still $y$. All other-edge divergence
coefficients and both target endpoint values remain zero. Zero velocity trace on
the patch boundary is preserved by $\mathcal T$.

For each physical tetrahedron $K=F(\widehat K)$,
$$
\int_K \operatorname{div}(\mathcal T\widehat v)\,dx
   =h^3\int_{\widehat K}\operatorname{div}\widehat v\,d\xi.
$$
Since $|K|=h^3|\widehat K|$, the **cell-average divergence is unchanged**.
The zero-cell-mean condition used by the reference operator therefore transports
exactly. Its unnormalized integral is also zero.

For each interior mode $m$, retain the checkerboard signs
$(1,-1,-1,1)$, and write the relation as
$$
y_{1,m}-y_{2,m}-y_{3,m}+y_{4,m}=0.
$$
Here subscripts $1,2,3,4$ denote the inherited incident-cell blocks, not a newly
sorted physical ordering. Let $H$ collect these $k-2$ relations.

The [reference source argument](FACE_DIAGONAL_LIFT.md#actual-source-space-characterization)
establishes $\operatorname{range}\widehat S=\ker H$, where $\widehat S$
takes the target trace of an unrestricted continuous velocity on the complete
four-tetrahedron source star. Its outer-boundary coefficients are included.
The coordinate transport is a bijection on this unrestricted source space too.

More explicitly, let $A$ be the invertible transport of those source
coefficients and $S_{\rm phys}$ the physical target-row map in the inherited
ordering. Divergence commutation gives
$$
S_{\rm phys}A=\widehat S.
$$
Because $A$ is invertible,
$$
\operatorname{range}S_{\rm phys}
 =\operatorname{range}\widehat S
 =\ker H.
$$

This proves both directions of source compatibility:

- **Necessity.** Any continuous physical source velocity pulls back by
  $\mathcal T^{-1}$ to an admissible unrestricted reference source velocity
  with the same target coefficients. Its trace must satisfy $Hy=0$.
  Restrictions inherited from a global continuous velocity are included.
- **Sufficiency.** If $Hy=0$, the accepted reference lift
  $\widehat L_k y$ exists. The physical field
  $L_{k,a,h,P}y=\mathcal T\widehat L_k y$ realizes $y$, preserves every
  protected edge condition and zero cell mean, and has zero patch-boundary
  velocity trace.

The source dimensions therefore remain six and nine. The reference
`source_basis`, `free_coordinate_indices`, checkerboard signs, and target
labels remain unchanged. In particular, the sparse velocity basis still acts on
the first three incident-cell blocks; `apply` accepts the complete compatible
vector and extracts those free coordinates.

## Exact H¹ seminorm scaling

Orthogonal conjugation preserves the Frobenius inner product of matrices, and
the volume Jacobian is $h^3$. Hence
$$
\begin{aligned}
|\mathcal T\widehat v|_{H^1(\Omega)}^2
 &=\int_\Omega |\nabla(\mathcal T\widehat v)|_F^2\,dx\\
 &=h^3\int_{\widehat\Omega}
       |Q(\nabla\widehat v)Q^T|_F^2\,d\xi\\
 &=h^3|\widehat v|_{H^1(\widehat\Omega)}^2.
\end{aligned}
$$
The same calculation for two different fields shows that the entire energy
Gram matrix of the transported basis equals $h^3$ times the reference Gram
matrix.

Applying the accepted conservative reference bounds gives
$$
|L_{4,a,h,P}y|_{H^1(\Omega)}^2
 \le 576h^3\|y\|_2^2,
\qquad
|L_{5,a,h,P}y|_{H^1(\Omega)}^2
 \le 1008h^3\|y\|_2^2.
$$
The norm on the right is the Euclidean norm of the **complete compatible
Bernstein trace vector**. These are the transported reference estimates, without
an additional optimization claim or conversion to a pressure-$L^2$ bound.

The formula concerns the H¹ **seminorm**. The squared $L^2$ norm of the
velocity has the separate scaling
$\|\mathcal T\widehat v\|_{L^2(\Omega)}^2
 =h^5\|\widehat v\|_{L^2(\widehat\Omega)}^2$.
Consequently the full squared H¹ norm does not have a single $h^3$ scaling
factor.

## Exact coefficient representation and physical certificate

The sparse reference entry `[3*n+c, j, r]` transports to
`[3*n+P[c], j, h*r]`. The shared node index `n` and free-coordinate column
`j` are retained. Since $h\ne0$ and the component permutation is bijective,
the number of nonzero basis entries remains 34 for degree four and 174 for
degree five.

The geometric label `nodes_times_degree[n]` is stored as a triple of exact
rational strings. If the reference label is $\widehat n$, then
$$
n_{\rm phys}=k\,a+hQ\widehat n.
$$
Dividing this label by $k$ gives the associated physical Bernstein node. The
coefficients indexed by these nodes are Bernstein control coefficients, not
interpolatory values of the velocity at those locations. Physical cell vertices
and target endpoints are likewise represented by exact rational coordinates.

The constructor reconstructs the physical divergence rows from the physical
tetrahedra. Barycentric gradients use the generic rational determinant formula;
the reference helper's unit-determinant shortcut cannot be used unchanged after
scaling. Inherited local vertex order makes the coefficient identity above
directly applicable.

For every free basis column, the physical edge rows must equal `source_basis`
on the target rows and zero on all protected rows. Every physical cell-average
row must be zero. The output's `physical_identity_check` records the checked
`basis_columns`, `edge_rows`, `target_rows`, `protected_rows` and
`zero_mean_rows`. Its exact residual fields `edge_residual_max` and
`mean_residual_max` are both the rational string `"0"`; `boundary_trace` records
that all boundary velocity coefficients are omitted and zero. These checks concern the
new physical coefficient construction. The analytical source-image and energy
arguments above use the accepted reference result.

## Run or reuse

Python 3.10+, standard library only. The command constructs a transported
operator, or includes the velocity for a supplied compatible trace. Use a new
output path.

```sh
python research/ridgway_freudenthal/face_diagonal_transport.py \
  --degree 4 --all-axes --origin=-2,1/3,0 --scale 3/2 \
  --trace 1,2,3,4,5,6,7,8 \
  --output /tmp/quartic-face-transport.json

python research/ridgway_freudenthal/face_diagonal_transport.py \
  --degree 5 --all-axes --origin=2/7,-3,5/2 --scale 2/3 \
  --trace 1/2,1,3/2,2,5/2,3,7/2,4,9/2,5,11/2,6 \
  --output /tmp/quintic-face-transport.json
```

Both example vectors satisfy the checkerboard relation in every mode. The
transport command's `--trace` takes **one comma-separated vector**. This differs
from the reference lift command's space-separated trace arguments. Use the
equals form for a value beginning with a minus sign, for example
`--trace=-1/2,...` or `--origin=-2,1/3,0`.

| Option | Meaning |
|---|---|
| `--degree 4\|5` | Select the accepted quartic or quintic reference lift. |
| `--normal-axis x\|y\|z` | Select one cyclic coordinate-normal orientation; the default is `x`. |
| `--all-axes` | Return all three orientations; mutually exclusive with `--normal-axis`. The reference operator is constructed once and reused. |
| `--origin X,Y,Z` | Three exact rational translation components; default `0,0,0`. |
| `--scale H` | A strictly positive exact rational isotropic scale; default `1`. |
| `--trace Y` | Optional complete compatible vector of eight or twelve comma-separated exact coefficients. |
| `--output PATH` | Create a new JSON output file; omit it to write to standard output. |

The reusable API is:

```python
transport(operator, normal_axis="x", origin=(0, 0, 0), scale=1)
construct(degree=4, normal_axis="x", origin=(0, 0, 0), scale=1)
apply(operator, trace)
```

`transport` accepts an already constructed reference `freudenthal-face-diagonal-lift/v1`
operator and returns a reusable physical operator without modifying the reference.
If the saved reference contains `requested_trace` or `velocity_coefficients`,
those old application fields are removed from the reusable result. `construct`
constructs the reference and transports it. `apply` consumes a list of exact
integers, rational strings, or `Fraction` values in the inherited complete
target ordering and returns the physical Bernstein velocity coefficients.
Translations and scales are exact rational data. A nonpositive scale or
incompatible trace is rejected.

A single-axis result uses schema `freudenthal-face-diagonal-transport/v1` and
status `TRANSPORTED_AND_CHECKED`. With `--all-axes`, the batch schema is
`freudenthal-face-diagonal-transport-batch/v1`; its `operators` dictionary has
keys `x`, `y`, and `z`, each holding a complete physical operator and certificate.
When `--trace` is supplied, each operator also contains the canonical rational
`requested_trace` and its physical `velocity_coefficients`.

The physical operator records `normal_axis`,
`reference_to_physical_component`, `origin`, and `scale`. Its
`reference_h1_squared_bound_from_target_l2` retains the reference constant;
`h1_squared_bound_from_target_l2` contains the bound multiplied by $h^3$.
The unchanged `basis_shape`, `source_basis`, and `free_coordinate_indices`
describe the same free trace coordinates.

## Executed construction

The two parameter sets shown above completed on Python 3.12.14 with exit 0,
using local output files `quartic-face-transports.json` and
`quintic-face-transports.json`. Each constructed the reference once and returned
all three physical orientations. Every physical operator reported exact edge and cell-mean
residuals `"0"`.

| Degree | Scale | Basis columns per orientation | Edge rows | Target rows | Protected rows | Zero-mean rows | Physical seminorm-squared bound |
|---|---:|---:|---:|---:|---:|---:|---:|
| 4 | `3/2` | 6 | 192 | 8 | 184 | 12 | `1944` |
| 5 | `2/3` | 9 | 264 | 12 | 252 | 12 | `896/3` |

The checks reconstruct the physical rows and evaluate every returned free basis
column. The source-compatibility equivalence and H¹ scaling are the analytical
arguments given above.

## Coverage

The result covers exactly the **three coordinate-normal orientations of this
one interior shared-face diagonal Kuhn class**, together with rational
translations and positive isotropic scaling. It does not classify axial or
body-diagonal classes, boundary-truncated stars, or all singular-edge geometries.
It supplies neither a general patch-selection/global-assembly argument nor a
mesh-uniform inf-sup theorem.

Existing reference geometry, source characterization, protected lifting, mean
repair, degree elevation, and bounds retain their source and review attribution.
This document adds the coordinate-transport argument; it makes no claim about a
new paper, current prize availability, sponsor acceptance, submission, or payment.
