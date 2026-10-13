# Protected interior axial-edge lifts

This construction continues [the Freudenthal research lane](https://github.com/woahwhattheheck/commons/issues/14999)
using the accepted [protected-map construction](FACE_DIAGONAL_LIFT.md),
[rectangular-grid quartic mean repair](P4_GRID_MEAN_REPAIR.md), and
[coordinate-transport argument](FACE_DIAGONAL_TRANSPORT.md). The implemented
`axial_edge_lift.py` constructs a continuous quartic or quintic velocity for every
endpoint-zero target trace in one interior axial-edge class. It preserves zero
divergence on all other edges, zero target endpoint values, zero divergence mean
on every tetrahedron, and zero patch-boundary velocity trace.

The target source image is full: all twelve quartic or eighteen quintic target
coordinates are independently realizable. The final reference matrices have 381
and 2,298 nonzero coefficients. Exact rational coordinate transport supplies all
three cyclic axial directions, translations, and positive isotropic scales.

## Reference geometry and target coordinates

The reference patch and ordered target edge are
$$
\widehat\Omega=[0,1]\times[0,2]^2,
\qquad
\widehat e=[(0,1,1),(1,1,1)].
$$
The standard Kuhn triangulation has four cubes and 24 tetrahedra. Cubes are
ordered lexicographically as $(x,y,z)$ with $z$ changing fastest; each cube uses
the unchanged six-cell order of `kuhn.py`.

The six incident target cells are **3, 5, 8, 16, 18, 19**. Targets are cell-major.
Within each cell the high-endpoint powers are $1,\ldots,k-2$ in the
degree-$(k-1)$ Bernstein trace of the divergence. Thus the complete target vector
$y$ has twelve coordinates at degree four and eighteen at degree five. These are
Bernstein coefficients, not values sampled at edge nodes.

Both endpoint divergence values are protected at zero. Every other
edge-supported divergence coefficient on every patch tetrahedron is protected
at zero too. The velocity uses shared continuous Bernstein coefficients with all
patch-boundary coefficients omitted and equal to zero.

| Reference quantity | Degree four | Degree five |
|---|---:|---:|
| Tetrahedra | 24 | 24 |
| Incident target cells | 6 | 6 |
| Scalar velocity unknowns | 441 | 972 |
| Target coordinates | 12 | 18 |
| All edge rows | 384 | 528 |
| Protected edge rows | 372 | 510 |
| Cell-average divergence rows | 24 | 24 |

An open segment of the target edge lies in the patch interior, while its two
endpoints lie on the patch boundary. The endpoint-zero target space is therefore
part of this construction's statement. It does not prescribe arbitrary vertex
divergence values.

## Protected right inverse and full target source image

Let $V_0^k(\widehat\Omega)$ be the continuous piecewise degree-$k$ vector space
with zero patch-boundary trace. In its shared Bernstein coefficient coordinates,
let $P$ collect all protected edge rows, $T$ collect the ordered target rows, and
$M$ collect the 24 cell-average divergence rows.

The exact protected-map solve constructs a rational matrix $R_{\rm raw}$ satisfying
$$
P R_{\rm raw}=0,
\qquad
T R_{\rm raw}=I_t,
\qquad t=6(k-2).
$$
These rational matrix identities also hold over the real target space.
Then $w=R_{\rm raw}y$ is a genuine continuous finite-element velocity for every
$y\in\mathbb R^t$, with the requested target trace, zero other-edge and endpoint
traces, and zero patch-boundary velocity trace. Its cell means may still be
nonzero.

This full target identity proves sufficiency on the actual continuous source
space. Let $S$ map an unrestricted continuous degree-$k$ velocity on the complete
six-tetrahedron target star to these same interior target coefficients.
Restrictions of the constructed patch fields are members of that source space.
Consequently
$$
\mathbb R^t
 =\operatorname{range}(T R_{\rm raw})
 \subseteq \operatorname{range}S
 \subseteq \mathbb R^t.
$$
Thus $\operatorname{range}S=\mathbb R^t$: every target vector is realizable and
there is no nonzero linear compatibility relation on these target coordinates.
A constructed patch field also extends continuously by zero across the patch
boundary when this patch is embedded in a larger conforming mesh.

The assertion concerns these endpoint-zero interior edge coordinates. It is not
a characterization of all divergence polynomial coefficients on the star or of
the complete global space $\operatorname{div}V_h^k$.

### Scope of the rank criterion

The image of the target map restricted by the protected conditions has dimension
$$
\dim T(\ker P)
 =\operatorname{rank}\begin{bmatrix}P\\T\end{bmatrix}
  -\operatorname{rank}P.
$$
Here the exact rank increments are $270-258=12$ and $384-366=18$, the full
target dimensions. The returned right-inverse identities establish the result
constructively.

As a methodological limit, a smaller rank increment on some other protected
patch would constrain that restricted patch space. It would not alone establish
a relation on the unrestricted source-star map or a global source restriction.
The conclusion for the present patch is successful full target surjectivity.

## Removing all cell means without changing any edge trace

For $w=R_{\rm raw}y$, set $m=Mw$. Each reference tetrahedron has volume $1/6$,
so the divergence theorem and zero exterior velocity trace give
$$
\frac16\sum_{K=1}^{24}m_K
 =\int_{\widehat\Omega}\operatorname{div}w\,dx
 =\int_{\partial\widehat\Omega}w\cdot n\,dS
 =0.
$$
The continuity of $w$ cancels the interior face fluxes. Hence the 24 requested
means lie in the zero-sum domain of the accepted rectangular-grid repair on
shape `[1,2,2]`.

Let $B_{\rm grid}$ denote that quartic repair. It returns a continuous
boundary-zero quartic velocity with the prescribed cell means and zero
divergence on **every** tetrahedral edge, including the target. Its fixed
face-adjacency assembly is linear; constructing each mean column separately
therefore defines the same linear correction map.

For degree four use the repair directly. For degree five use its exact
Bernstein degree elevation $E_5$; write $E_4$ for the identity representation.
The final operator is
$$
R
 =R_{\rm raw}
  -E_k B_{\rm grid}M R_{\rm raw}.
$$
Since the correction has zero divergence on every edge and exactly the raw cell
means,
$$
P R=0,\qquad T R=I_t,\qquad M R=0.
$$
It also preserves the zero patch-boundary velocity trace. Thus the mean repair
adds no target compatibility requirement and removes none of the target image.

For clarity, the componentwise quartic-to-quintic Bernstein coefficient formula
on a cell is
$$
(E_5 b)_\alpha
 =\sum_{\substack{0\le i\le3\\\alpha_i>0}}
     \frac{\alpha_i}{5}\,b_{\alpha-e_i},
\qquad |\alpha|=5.
$$
This is an identity of polynomial fields, obtained from
$\sum_i\lambda_i=1$. It preserves continuity, boundary trace, divergence, every
edge trace, and all cell means exactly. It applies to every column of the
four-cube correction; it does not depend on the number of mean-repair columns.

## A finite-degree Bernstein coefficient bound

Let $R$ be the final scalar coefficient matrix acting on the complete target
vector, including zero rows where appropriate, and define
$$
\rho_k=\max_r\sum_{j=1}^{t}R_{rj}^2.
$$
For every scalar coefficient row, Cauchy–Schwarz gives
$|(Ry)_r|^2\le\rho_k\|y\|_2^2$. A vector Bernstein coefficient $c_\alpha$ has
three scalar components, so
$$
|c_\alpha|^2\le3\rho_k\|y\|_2^2.
$$

On each cell, using the Frobenius norm for the velocity gradient,
$$
\nabla v
 =k\sum_{|\beta|=k-1}B_\beta^{k-1}
      \sum_{i=0}^3 c_{\beta+e_i}\otimes\nabla\lambda_i.
$$
The nonnegative Bernstein polynomials form a partition of unity. Jensen's
inequality bounds the squared norm of their combination by the corresponding
combination of squared norms. For each inner sum, Cauchy–Schwarz gives
$$
\left|\sum_{i=0}^3
 c_{\beta+e_i}\otimes\nabla\lambda_i\right|_F^2
 \le
 \left(\sum_{i=0}^3|c_{\beta+e_i}|^2\right)
 \left(\sum_{i=0}^3|\nabla\lambda_i|^2\right).
$$
For a coordinate-ordered unit Kuhn tetrahedron the barycentric gradients are
$-e_0$, $e_0-e_1$, $e_1-e_2$, and $e_2$, up to coordinate and vertex permutation.
Their squared norms sum to $1+2+2+1=6$. Thus the second factor is $6$ and the
first is at most $4\cdot3\rho_k\|y\|_2^2$. Summing the cell integrals over the volume-four patch
therefore proves
$$
|Ry|_{H^1(\widehat\Omega)}^2
 \le 4\cdot3\cdot k^2\cdot6\cdot4\cdot\rho_k\|y\|_2^2
 =288k^2\rho_k\|y\|_2^2.
$$
The constructed final matrices have
$$
\rho_4=\frac{41}{36},
\qquad
\rho_5=\frac{1363}{4900},
$$
so the reference bounds are
$$
|R_4y|_{H^1(\widehat\Omega)}^2\le5248\|y\|_2^2,
\qquad
|R_5y|_{H^1(\widehat\Omega)}^2
 \le\frac{98136}{49}\|y\|_2^2.
$$
The bound uses the **final combined matrix**, so it includes the actual mean
correction. It is a conservative finite-patch estimate in target-coefficient
norm; it does not assert an optimized constant or a pressure-$L^2$ estimate.

## Coordinate orientations and isotropic transport

Use the three cyclic coordinate permutations
$$
P_x=(0,1,2),\qquad P_y=(1,2,0),\qquad P_z=(2,0,1),
$$
with $Qe_i=e_{P[i]}$: reference component $i$ maps to physical component $P[i]$.
For $a\in\mathbb Q^3$ and $h\in\mathbb Q,\ h>0$, set
$$
F(\xi)=a+hQ\xi,
\qquad
(\mathcal T\widehat v)(F(\xi))=hQ\widehat v(\xi).
$$
The reference axial direction is component 0. The physical patch has length $h$
along its transported axial direction and $2h$ in the other directions. Its
ordered target endpoints are
$$
a+h\bigl((1,1,1)-e_{P[0]}\bigr),
\qquad a+h(1,1,1).
$$

As in the [face-diagonal transport derivation](FACE_DIAGONAL_TRANSPORT.md),
coordinate permutations send Kuhn vertex chains to Kuhn vertex chains, and the
cell, local vertex, shared Bernstein-node, and target-coordinate order can be
inherited without re-sorting. The chain rule gives
$$
\nabla(\mathcal T\widehat v)(F(\xi))
 =Q\nabla\widehat v(\xi)Q^T,
\qquad
\operatorname{div}(\mathcal T\widehat v)(F(\xi))
 =\operatorname{div}\widehat v(\xi).
$$
All target coefficients and zero protected traces remain unchanged. Cell-average
divergences remain unchanged; their integrals acquire the common volume factor
$h^3$. Zero patch-boundary velocity trace is preserved.

The inverse $h^{-1}Q^T w(F(\xi))$ makes this transport a bijection on the
unrestricted continuous source star as well as on the boundary-zero patch space.
Thus a full reference target image remains full in each transported orientation;
transport cannot introduce an additional compatibility condition.

Finally,
$$
|\mathcal T\widehat v|_{H^1(F(\widehat\Omega))}^2
 =h^3|\widehat v|_{H^1(\widehat\Omega)}^2,
$$
so the transported coefficient bound is $288k^2\rho_k h^3\|y\|_2^2$.
This is an H¹ seminorm statement. The squared velocity-$L^2$ norm instead scales
by $h^5$.

## Sparse output and physical certificate

The reference operator has schema `freudenthal-axial-edge-lift/v1` and status
`CONSTRUCTED`. Its `source_basis` is the full identity matrix,
`source_dimension` equals `target_coordinate_count`, and
`free_coordinate_indices` lists every target coordinate. Each sparse
`basis` entry `[row,column,value]` acts directly on the complete target vector.
There is no additional checkerboard gate on this axial class.

The physical operator uses schema `freudenthal-axial-edge-transport/v1` and
status `TRANSPORTED_AND_CHECKED`. A scalar component row `3*n+c` maps to
`3*n+P[c]` and its coefficient is multiplied by $h$. Node and target column
indices are inherited. The physical `nodes_times_degree` label is the exact
rational triple
$$
k\,a+hQ\widehat n,
$$
where $\widehat n$ is the reference degree-multiplied Bernstein node. Divide by
$k$ for its physical geometric location. Physical `cells` and `target_edge`
coordinates are rational strings too. Velocity entries are Bernstein control
coefficients, not point samples; omitted boundary coefficients are zero.

`reference_shape` retains `[1,2,2]`. The physical-axis cube counts in `shape`
are `[1,2,2]`, `[2,1,2]`, or `[2,2,1]` for axial directions `x`, `y`, or `z`.
Physical side lengths are these counts multiplied by `scale`.

The maximum squared coefficient-row norm scales by $h^2$, because the rows are
permuted and multiplied by $h$. The squared H¹ seminorm bound scales by $h^3$.
The output keeps both pairs of quantities explicitly:

- `reference_maximum_squared_coefficient_row_norm` and
  `maximum_squared_coefficient_row_norm`;
- `reference_h1_squared_bound_from_target_l2` and
  `h1_squared_bound_from_target_l2`.

The unit-patch bound uses the reference row norm. Equivalently, with
$\rho_{\rm phys}=h^2\rho_k$, the physical bound is
$288k^2h\,\rho_{\rm phys}\|y\|_2^2$; physical barycentric gradients and volumes
account for the remaining factor of $h$.

The existing generic physical identity helper reconstructs divergence rows from
the actual rational tetrahedra, using their determinants in the barycentric
gradients. It checks every basis column against the target identity and all zero
protected rows, checks all 24 cell-average rows, and confirms that boundary
velocity coefficients are omitted. Each `physical_identity_check` records
`basis_columns`, `edge_rows`, `target_rows`, `protected_rows`,
`zero_mean_rows`, and `boundary_trace`. Its exact residual fields
`edge_residual_max` and `mean_residual_max` are the rational string `"0"`.
The final reference field is checked, and each physical transport is checked
again using its physical coordinates.

## Run or reuse

Python 3.10+, standard library only. Each `--all-axes` invocation constructs the
reference once and returns all three physical orientations.

```sh
python research/ridgway_freudenthal/axial_edge_lift.py \
  --degree 4 --all-axes --origin=-1/3,2/5,-7/2 --scale 2/3 \
  --trace 1,2,3,4,5,6,7,8,9,10,11,12 \
  --output /tmp/quartic-axial-lifts.json

python research/ridgway_freudenthal/axial_edge_lift.py \
  --degree 5 --all-axes --origin=1/4,-5/3,2 --scale 3/2 \
  --trace 1/2,1,3/2,2,5/2,3,7/2,4,9/2,5,11/2,6,13/2,7,15/2,8,17/2,9 \
  --output /tmp/quintic-axial-lifts.json
```

`--trace` takes one comma-separated vector of twelve or eighteen exact
coefficients. Every such vector is admissible. Use the equals form when an
argument begins with a minus sign, as in `--origin=-1/3,2/5,-7/2` or
`--trace=-1/2,...`.

| Option | Meaning |
|---|---|
| `--degree 4\|5` | Quartic or quintic velocity degree; default `4`. |
| `--axis x\|y\|z` | One axial direction; default `x`. |
| `--all-axes` | All three cyclic directions; mutually exclusive with `--axis`. |
| `--origin X,Y,Z` | Exact rational translation triple; default `0,0,0`. |
| `--scale H` | Strictly positive exact rational isotropic scale; default `1`. |
| `--trace Y` | Optional complete comma-separated target vector; omit it to return a reusable operator. |
| `--output PATH` | Create a new JSON output path; omit it to write to standard output. |

A single-axis CLI result is the physical operator, even for the default identity
transform. With `--all-axes`, schema `freudenthal-axial-edge-batch/v1` contains
an `operators` dictionary with keys `x`, `y`, and `z`. When a trace is supplied,
each operator also includes canonical rational `requested_trace` and physical
`velocity_coefficients`.

The reusable API is:

```python
construct_reference(degree=4)
transport(operator, axis="x", origin=(0, 0, 0), scale=1)
construct(degree=4, axis="x", origin=(0, 0, 0), scale=1)
apply(operator, trace)
```

`construct_reference` returns the reusable reference operator. `transport`
accepts that reference schema, leaves the input unchanged, and returns a reusable
physical operator. Any saved `requested_trace` and `velocity_coefficients`
are removed from that reusable result. `construct` builds the reference and its
requested transport. `apply` accepts the complete target list of exact integers,
rational strings, or `Fraction` values and returns physical Bernstein
coefficients for a physical operator.

## Actual construction

The two parameter sets above completed on Python 3.12.14 with exit 0, using
local output files `quartic-axial-lifts.json` and `quintic-axial-lifts.json`.
Both returned all three axes with exact physical edge and mean residuals `"0"`.
The protected right inverse has the full target identity in both degrees.

| Constructed reference quantity | Degree four | Degree five |
|---|---:|---:|
| Protected rank | 258 | 366 |
| Combined protected+target rank | 270 | 384 |
| Final matrix shape | `441 × 12` | `972 × 18` |
| Nonzero final coefficients | 381 | 2,298 |
| Raw mean columns repaired | 12 | 18 |
| Total two-cube repair applications | 25 | 35 |
| Maximum squared coefficient-row norm | `41/36` | `1363/4900` |
| Reference H¹ seminorm-squared bound | `5248` | `98136/49` |

The executed quartic scale `2/3` gives physical maximum squared row norm `41/81` and
seminorm-squared bound `41984/27`. The executed quintic scale `3/2` gives
physical maximum squared row norm `12267/19600` and seminorm-squared bound `331209/49`.
These values hold for each of the three coordinate orientations.

The construction reuses the accepted geometry, sparse mean-repair basis and
grid assembler, and generic physical identity helper. The new degree-elevation
step handles all columns of the four-cube correction. No earlier proof replay,
new test suite, fixtures, workflow, or dependency is part of this construction.

## Scope of the analytical conclusion

The constructed full protected right inverse establishes one interior axial-edge
class for the endpoint-zero target coordinates in degrees four and five, with
the stated cyclic orientations, exact translations, and positive isotropic scaling. It does not complete the
boundary-star census, all vertex/source compatibility, global assembly, or the
mesh-uniform Scott–Vogelius theorem.

The accepted Kuhn geometry, protected-map solver, local and rectangular-grid mean
repair, degree-elevation identity, and earlier face-diagonal construction retain
their source and review attribution. No sponsor contact, new paper, current
prize availability, eligibility, submission, acceptance, or payment claim follows.
