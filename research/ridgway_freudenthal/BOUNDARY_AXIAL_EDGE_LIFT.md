# Protected boundary axial-edge lifts

`boundary_axial_edge_lift.py` constructs continuous quartic and quintic
velocities for one axial edge in a Dirichlet boundary face. Every endpoint-zero
target trace is realizable: the three incident cells supply six independent
coordinates at degree four and nine at degree five. The returned fields have
the requested target divergence, zero divergence on every other edge and both
target endpoints, zero mean divergence on every tetrahedron, and zero velocity
trace on the entire patch boundary.

The final reference matrices have 150 and 916 nonzero scalar coefficients,
with conservative seminorm-squared bounds $1500$ and $25632/49$ in complete
target-coefficient norm. Exact coordinate transport covers all six ordered
distinct tangent/normal axis pairs and both boundary sides.

This is a further finite class under [the existing research issue](https://github.com/woahwhattheheck/commons/issues/14999).
It reuses the accepted [protected-map solver](P4_BODY_DIAGONAL_LIFT.md),
[two-cube mean repair](P4_MEAN_REPAIR.md),
[quintic elevation](P5_BODY_DIAGONAL_LIFT.md), and
[physical coordinate checker](FACE_DIAGONAL_TRANSPORT.md).
The [boundary face-diagonal construction](BOUNDARY_FACE_DIAGONAL_LIFT.md)
and its source attribution remain unchanged.

## Reference geometry and target coordinates

The patch, physical Dirichlet plane, and ordered target edge are
$$
\widehat\Omega=[0,2]\times[0,1]^2,\qquad
\widehat\Gamma=\{z=0\},\qquad
\widehat e=[(1,0,0),(1,1,0)].
$$
The patch consists of two Kuhn cubes and twelve positively oriented
tetrahedra. The first six cells use the existing `kuhn.py` order, followed
by the same six cells translated by $(1,0,0)$.

The actual incident cells are **0, 8, and 9**:
$$
K_0=((0,0,0),(1,0,0),(1,1,0),(1,1,1)),
$$
$$
K_8=((1,0,0),(2,1,0),(1,1,0),(2,1,1)),
$$
$$
K_9=((1,0,0),(1,1,0),(1,1,1),(2,1,1)).
$$
The open edge lies in the relative interior of the boundary face; it is
not a box edge where two Dirichlet planes meet.

Set $m=k-2$, with $k\in\{4,5\}$. The degree-$(k-1)$ divergence trace has
interior Bernstein modes $j=1,\ldots,m$, where $j$ is the power at the
ordered second endpoint. Their cell-local multi-indices are
$$
\beta^{(0)}_j=(0,k-1-j,j,0),\qquad
\beta^{(8)}_j=(k-1-j,0,j,0),\qquad
\beta^{(9)}_j=(k-1-j,j,0,0).
$$
The complete input is cell-major:
$$
y=(y_{0,1},\ldots,y_{0,m},
   y_{8,1},\ldots,y_{8,m},
   y_{9,1},\ldots,y_{9,m})\in\mathbb R^{3m}.
$$
These are Bernstein coefficients, not point samples. Both endpoint
coefficients are protected at zero, together with every edge-supported
divergence coefficient outside this target list.

## The actual continuous Dirichlet source map

Let $S$ map the continuous vector degree-$k$ coefficients on the complete
three-cell star to the target coordinates. Only coefficients on $z=0$ are
removed. Other source-star boundary coefficients remain available, and no
source endpoint condition is imposed. This source space contains every
restriction of a continuous velocity satisfying the physical Dirichlet
condition.

Continuity is encoded by shared degree-scaled geometric Bernstein nodes.
For a cell $K$, the exact divergence coefficient is
$$
d_{K,\beta}
 =k\sum_{i=0}^3\nabla\lambda_i\cdot c_{K,\beta+e_i}.
$$
Define the two shared nodes
$$
C_j=(k,j+1,1),\qquad D_j=(k+1,j+1,1).
$$
The coordinates are multiplied by $k$; the physical reference nodes are
$C_j/k$ and $D_j/k$. Write $C_{j,x},C_{j,z},D_{j,x},D_{j,z}$ below for
components of the velocity **coefficients** at those nodes.

In $K_0$, all vertices except $(1,1,1)$ lie on $z=0$. The surviving target
coefficient uses $C_j$, and the corresponding barycentric gradient is
$(0,0,1)$. In $K_8$, the analogous surviving coefficient uses $D_j$, also
with gradient $(0,0,1)$.

Cell $K_9$ meets the Dirichlet plane only along the target edge. Its two
off-plane vertices have barycentric gradients $(-1,0,1)$ and $(1,0,0)$.
Continuity identifies their target-adjacent coefficients with $C_j$ and
$D_j$ from the other cells. Consequently the actual source rows are
$$
\begin{aligned}
y_{0,j}&=kC_{j,z},\\
y_{8,j}&=kD_{j,z},\\
y_{9,j}&=k(-C_{j,x}+C_{j,z}+D_{j,x}).
\end{aligned}
$$
The program reconstructs these rows from all shared source coefficients.
It records the sparse terms as `reference_source_rows` and solves their
exact full right inverse. This establishes the source map directly from
the velocity space, without prescribing an independent pressure space.

### Full source image

Every $C_j$ and $D_j$ is off the Dirichlet plane, and all these nodes are
distinct. For arbitrary target values, choose
$$
C_{j,z}=\frac{y_{0,j}}k,\qquad
D_{j,z}=\frac{y_{8,j}}k,\qquad
C_{j,x}=0,\qquad
D_{j,x}=\frac{y_{9,j}-y_{0,j}}k,
$$
with the remaining source coefficient components zero. The three displayed
source equations then hold for every mode independently.

Equivalently, restricting to the three scalar variables
$(C_{j,z},D_{j,z},D_{j,x})$ with $C_{j,x}=0$ gives the block
$$
k\begin{bmatrix}
1&0&0\\
0&1&0\\
1&0&1
\end{bmatrix},
$$
whose determinant is $k^3\ne0$. Thus
$$
\operatorname{range}S=\mathbb R^{3m}.
$$
There is no nonzero linear compatibility relation on these complete
interior target coordinates. The explicit source assignment proves this
algebraically; the native exact right-inverse calculation gives ranks
six and nine.

The shared source-node count is
$$
3\binom{k+3}{3}-4\binom{k+2}{2}+(k+1).
$$
To see the count, the three tetrahedra contribute
$3\binom{k+3}{3}-2\binom{k+2}{2}$ distinct nodes after shared-face
identification; their Dirichlet part is two triangular faces sharing the
target edge, with $2\binom{k+2}{2}-(k+1)$ nodes. The retained counts are
50 and 90 nodes, or 150 and 270 scalar vector-component unknowns.

This source right inverse need not preserve other edge traces or cell
means. Those additional conditions are supplied by the patch construction.

## Protected patch right inverse

Let $V_0^k(\widehat\Omega)$ be the continuous piecewise degree-$k$ vector
space with zero trace on the entire patch boundary. This imposes additional
conditions beyond the one-plane source-star Dirichlet restriction.
In shared Bernstein coordinates, let $P$ collect the protected edge rows,
$T$ collect the ordered target rows, and $M$ collect the twelve
cell-average divergence rows.

The new exact protected solve returns
$$
PR_{\rm raw}=0,\qquad TR_{\rm raw}=I_{3m}.
$$
Each column is a genuine patch-boundary-zero finite-element field.
Hence every complete target vector can be realized while protecting all
other edge and endpoint coefficients. The source image established above
is retained in this smaller output space.

| Reference quantity | Degree four | Degree five |
|---|---:|---:|
| Patch tetrahedra | 12 | 12 |
| Source-star retained Bernstein nodes | 50 | 90 |
| Source-star scalar coefficient unknowns | 150 | 270 |
| Complete target dimension / source rank | 6 / 6 | 9 / 9 |
| Patch scalar coefficient unknowns | 189 | 432 |
| Protected edge rows / rank | 186 / 116 | 255 / 166 |
| Combined protected-and-target rank | 122 | 175 |
| Final operator shape | 189 × 6 | 432 × 9 |
| Final nonzero scalar coefficients | 150 | 916 |
| Checked edge rows | 192 | 264 |
| Checked cell-mean rows | 12 | 12 |

The protected rank increments are $122-116=6$ and $175-166=9$.
They equal the full target dimensions. The constructed identities provide
the right inverses, rather than only a numerical rank indication.
All rational identities also hold over the real target space.

For another patch, the formula
$$
\dim T(\ker P)
 =\operatorname{rank}\begin{bmatrix}P\\T\end{bmatrix}
  -\operatorname{rank}P
$$
would describe that restricted patch image. A smaller increment would
not by itself imply a relation on the unrestricted Dirichlet source star.
For the present patch, both protected solves succeed with the full image.

## Removing cell means while preserving every edge trace

For $w=R_{\rm raw}y$, set $q=Mw$. Each reference tetrahedron has volume
$1/6$, and the exterior velocity trace is zero. Continuity cancels the
interior face fluxes, giving
$$
\frac16\sum_{K=0}^{11}q_K
 =\int_{\widehat\Omega}\operatorname{div}w\,dx
 =\int_{\partial\widehat\Omega}w\cdot n\,dS
 =0.
$$
Thus the raw means belong to the zero-sum domain of the accepted two-cube
quartic mean repair.

Let $C_4$ denote that existing repair acting on twelve zero-sum means.
The stored `p4_mean_repair_basis.json` has eleven columns acting on the
first eleven means; the twelfth is determined by their negative sum.
Its velocity has the requested means, zero divergence on every
tetrahedral edge, and zero patch-boundary trace.

For $k=4$, use this quartic representation directly. For $k=5$, the
existing `elevate` helper expresses the same eleven-column correction
as a quintic. Its componentwise Bernstein formula is
$$
(E_5b)_\alpha
 =\sum_{\substack{0\le i\le3\\\alpha_i>0}}
    \frac{\alpha_i}{5}\,b_{\alpha-e_i},
\qquad |\alpha|=5.
$$
This preserves the polynomial itself, including continuity, boundary
values, all divergence edge traces, and means. Write $E_4=I$.

The final operator is
$$
R=R_{\rm raw}-E_kC_4MR_{\rm raw}.
$$
It satisfies
$$
PR=0,\qquad TR=I_{3m},\qquad MR=0.
$$
The boundary velocity trace remains zero. The repair changes neither the
target coordinates nor their full source image.

In the actual construction, all six quartic and all nine quintic raw
target columns had a nonzero cell-mean vector. The exported
`raw_mean_columns_nonzero` values record those counts. The final mean
identities are zero for every basis column. The accepted basis is loaded
and composed; its earlier construction is not rerun.

## Explicit finite-patch seminorm bound

Let $R$ be the final, mean-corrected coefficient matrix and define
$$
\rho_k=\max_r\sum_{\ell=1}^{3m}R_{r\ell}^2.
$$
Every scalar coefficient obeys
$|c_r|^2\le\rho_k\|y\|_2^2$; each vector coefficient therefore has
$\|c\|_2^2\le3\rho_k\|y\|_2^2$.

For a unit Kuhn tetrahedron, the sum of the squared barycentric gradient
norms is $1+2+2+1=6$. The Bernstein derivative identity gives
$$
\nabla v
 =k\sum_{|\beta|=k-1}B_\beta^{k-1}
       \sum_{i=0}^3c_{\beta+e_i}\otimes\nabla\lambda_i.
$$
The Bernstein weights are nonnegative and sum to one. Jensen's inequality
and Cauchy–Schwarz for the four derivative terms imply
$$
|\nabla v|_F^2
 \le k^2\cdot6\cdot4\cdot3\,\rho_k\|y\|_2^2.
$$
Integrating over the volume-two patch yields
$$
|Ry|_{H^1(\widehat\Omega)}^2
 \le144\,k^2\rho_k\|y\|_2^2.
$$

| Final reference bound | Degree four | Degree five |
|---|---:|---:|
| Maximum squared scalar row norm $\rho_k$ | $125/192$ | $178/1225$ |
| Seminorm-squared coefficient $144k^2\rho_k$ | $1500$ | $25632/49$ |

The norm on $y$ is the Euclidean norm of the complete target Bernstein
coefficients. No compatibility projection or extraction changes that
norm. These conservative bounds concern the velocity seminorm squared;
they are not optimized constants or estimates in pressure $L^2$ norm.

## Twelve signed coordinate transports

Choose distinct physical tangent and normal axes $t,n\in\{x,y,z\}$, and
let $r$ be the remaining axis. Let $Q$ map reference component $i$ to
physical component $P[i]$, with
$$
P=(r,t,n).
$$
Choose $s=+1$ for a lower face and $s=-1$ for an upper face. Define
$$
O=sQ,\qquad
F(\xi)=a+hO\xi,\qquad
(\mathcal Tv)(F(\xi))=hO v(\xi),
\qquad a\in\mathbb Q^3,\quad h\in\mathbb Q_{>0}.
$$
The reference first, second, and third coordinates become the remaining,
tangent, and normal physical coordinates, respectively.

| Tangent axis | Normal axis | $P$ | $\det Q$ |
|---|---|---|---:|
| $x$ | $y$ | $(2,0,1)$ | $+1$ |
| $x$ | $z$ | $(1,0,2)$ | $-1$ |
| $y$ | $x$ | $(2,1,0)$ | $-1$ |
| $y$ | $z$ | $(0,1,2)$ | $+1$ |
| $z$ | $x$ | $(1,2,0)$ | $+1$ |
| $z$ | $y$ | $(0,2,1)$ | $-1$ |

Each row has a lower and an upper version, giving twelve choices. The
physical Dirichlet plane is $x_n=a_n$, and the patch lies on its positive
side for lower faces and negative side for upper faces. The ordered
target endpoints are
$$
a+sh e_r,\qquad a+sh(e_r+e_t).
$$
Thus the ordered tangent displacement is $sh e_t$. The origin $a$ is the
image of the reference origin, not the first target endpoint. It is the
coordinatewise lower patch corner for $s=+1$ and upper patch corner for
$s=-1$. Upper-face transport uses uniform inversion of all three
coordinates.

### Kuhn geometry and the orientation correction

Coordinate permutations preserve the Kuhn cell sets because they permute
the six possible coordinate-step orders. Uniform inversion reverses a
coordinate-step chain; reading the inverted chain backward gives a Kuhn
chain in the transformed cube. Hence every $O=sQ$ preserves the geometric
Kuhn triangulation.

The determinant of the initially transported local cell is
$$
h^3\det O=h^3s\det Q.
$$
The implementation keeps the local vertex order when $s\det Q=+1$.
When $s\det Q=-1$, it uses the transposition
$$
\sigma=(0,2,1,3),\qquad
K_i^{\rm phys}=F(\widehat K_{\sigma(i)}),
\qquad
\beta_i^{\rm phys}=\widehat\beta_{\sigma(i)}.
$$
The same permutation applies to vertices and Bernstein multi-indices.
It restores the positive determinant $h^3$ without changing the
represented polynomial.

| Permutation parity | Lower face | Upper face |
|---|---|---|
| $\det Q=+1$ | Inherit local vertices | Swap local vertices 1 and 2 |
| $\det Q=-1$ | Swap local vertices 1 and 2 | Inherit local vertices |

Global node order, cell order, target-row order, and ordered edge
endpoints remain inherited. The target modes are still indexed by the
power at the inherited second endpoint. No geometric re-sorting changes
the trace vector.

### Divergence, source image, and means

Since $O^TO=I$, the chain rule gives
$$
\nabla_x(\mathcal Tv)(F(\xi))
 =O\,\nabla_\xi v(\xi)\,O^T,
\qquad
\operatorname{div}_x(\mathcal Tv)(F(\xi))
 =\operatorname{div}_\xi v(\xi).
$$
The transformed divergence coefficients therefore equal the reference
coefficients after the matching barycentric relabelling. Target
reproduction, zero protected rows, and zero endpoint coefficients are
unchanged.

The inverse map
$$
v(\xi)=h^{-1}O^T v_{\rm phys}(a+hO\xi)
$$
preserves continuity and the one-plane Dirichlet condition. It is a
bijection of reference and physical source-star spaces with the same
inherited target coordinates. Thus full source surjectivity transports
in both directions for all twelve choices.

The absolute volume Jacobian is $h^3$ even for negative $\det O$. Hence
the divergence cell average is unchanged:
$$
\frac1{|F(K)|}\int_{F(K)}\operatorname{div}(\mathcal Tv)\,dx
 =\frac1{|K|}\int_K\operatorname{div}v\,d\xi.
$$
Zero means and zero patch-boundary velocity trace persist.

### Seminorm and coefficient scaling

Orthogonal conjugation preserves the Frobenius norm, so
$$
|\mathcal Tv|_{H^1(F(\widehat\Omega))}^2
 =h^3|v|_{H^1(\widehat\Omega)}^2.
$$
The physical bounds are therefore $1500h^3$ and
$(25632/49)h^3$ in the unchanged complete target norm. The velocity
$L^2$ norm squared scales by $h^5$; a full $H^1$ norm should not be
substituted for this seminorm statement.

A scalar velocity row at node $q$ and component $c$ moves to the same
node index and component $P[c]$, and its entries are multiplied by $sh$.
Thus the maximum squared coefficient-row norm is $h^2\rho_k$.
The physical degree-scaled node coordinates are
$$
k a+hOq_{\rm ref}.
$$
They are emitted as exact rational strings in `nodes_times_degree`;
divide by $k$ for geometric locations. The associated vectors remain
Bernstein control coefficients, not sampled velocity values.

## Reusable interface

```python
construct_reference(degree=4)
transport(operator, tangent_axis="y", normal_axis="z", side="lower",
          origin=(0, 0, 0), scale=1)
construct(degree=4, tangent_axis="y", normal_axis="z", side="lower",
          origin=(0, 0, 0), scale=1)
apply(operator, trace)
```

`construct_reference` returns the reference operator. `transport` accepts
that result without mutating it and returns a reusable physical operator.
Application-specific `requested_trace` and `velocity_coefficients` fields
are removed from the copied reference result. `construct` combines the
two operations, including for the default identity transform.

`apply` takes a list containing the complete six- or nine-coordinate
trace and returns vector Bernstein coefficients in the recorded node
order. Every complete target is admissible: `source_basis` is the full
identity, `free_coordinate_indices` contains every target index, and
`compatibility_relations` is empty.

Inputs use exact integers, rational strings, or `fractions.Fraction`
values in process. The axes must be distinct, the scale positive, and
the trace length correct. Invalid numeric data or geometric arguments
raise `ValueError`; CLI failures report a clear message and return
nonzero. Booleans and floating-point values are not accepted as exact
numeric inputs.

### CLI

```sh
python research/ridgway_freudenthal/boundary_axial_edge_lift.py \
  --degree 4 --all-orientations --origin=-2/3,1/5,7/2 --scale 3/2 \
  --trace 1,-2,3,-4,5,-6 --output quartic-boundary-axial-lifts.json

python research/ridgway_freudenthal/boundary_axial_edge_lift.py \
  --degree 5 --all-orientations --origin=2/7,-5/3,1/4 --scale 2/3 \
  --trace 1/2,-2/3,3/4,-4/5,5/6,-6/7,7/8,-8/9,9/10 \
  --output quintic-boundary-axial-lifts.json
```

Use Python 3.10+ and the standard library, with the existing adjacent
source files and `p4_mean_repair_basis.json`. Select one orientation with
`--orientation T-N-SIDE`, for example `--orientation x-z-upper`.
The default `y-z-lower` is the identity reference orientation.
`--orientation` and `--all-orientations` are mutually exclusive.

Both `--origin` and `--trace` take one comma-separated argument. Use
the `--origin=...` or `--trace=...` spelling if its first entry is negative.
Omitting `--trace` returns the reusable operator; `--all-orientations`
constructs the reference once and reuses it twelve times. Output paths
must be new. Without `--output`, JSON is written to stdout.

### Output semantics

| Result | Schema | Status |
|---|---|---|
| Reference | `freudenthal-boundary-axial-edge-lift/v1` | `CONSTRUCTED` |
| One physical orientation | `freudenthal-boundary-axial-edge-transport/v1` | `TRANSPORTED_AND_CHECKED` |
| All twelve orientations | `freudenthal-boundary-axial-edge-batch/v1` | `TRANSPORTED_AND_CHECKED` |

The batch contains an `operators` dictionary with the twelve
`tangent-normal-side` keys. Each physical operator includes:

- Actual physical `cells`, `nodes_times_degree`, ordered `target_edge` and
  `target_coordinates`, plus its sparse coefficient `basis`.
- `reference_to_physical_component`, `coordinate_sign`,
  `permutation_determinant`, `orthogonal_determinant`, and
  `physical_vertex_to_reference_vertex` for the exact ordering convention.
- `dirichlet_face` with the physical axis, plane coordinate, and interior
  side. The source boundary description concerns the star; the returned
  velocity vanishes on the entire patch boundary.
- `shape` as physical-axis **cube counts**, with `reference_shape=[2,1,1]`.
  Physical side lengths are $h$ times these counts.
- `maximum_squared_coefficient_row_norm` equal to $h^2\rho_k$ and
  `h1_squared_bound_from_target_l2` equal to $h^3$ times the reference bound.
  Their `reference_`-prefixed fields retain the unscaled values.

`reference_source_rows` and `source_identity_check` always describe the
**reference** Dirichlet source-star computation, including in a physical
operator. They retain the original reference multi-indices and components.
The inverse-transform argument proves the corresponding physical source
image; these fields do not pretend to contain a separately recomputed
physical source matrix.

`physical_identity_check` is reconstructed from each actual physical
geometry. The existing generic checker divides cross products by the
exact cell determinant, checks positive orientation and boundary
coefficient omission, and checks every basis column against every
target/protected edge row and all twelve means. It records row and
column counts, `boundary_trace`, and the exact strings `"0"` for
`edge_residual_max` and `mean_residual_max`.

## Completed native construction

The two parameter sets shown above ran successfully on Python
3.12.14/Linux. Both commands exited 0. They produced the named quartic
and quintic JSON files and constructed all twelve orientations per
degree. Every physical edge and mean residual was zero for every target
basis column, including both signs of permutation parity and both
boundary sides. The new source-star right inverses also had exact
residual zero.

| Executed quantity | Degree four | Degree five |
|---|---|---|
| Origin | $(-2/3,1/5,7/2)$ | $(2/7,-5/3,1/4)$ |
| Scale | $3/2$ | $2/3$ |
| Complete input trace | $(1,-2,3,-4,5,-6)$ | $(1/2,-2/3,3/4,-4/5,5/6,-6/7,7/8,-8/9,9/10)$ |
| Physical squared row norm | $375/256$ | $712/11025$ |
| Physical seminorm-squared bound | $10125/2$ | $22784/147$ |
| Target columns checked per orientation | 6 | 9 |
| Orientations checked | 12 | 12 |

The commands took approximately 0.425 and 0.793 seconds in that native
run; the maximum observed child resident set across both commands was
22,400 KiB. These are execution measurements, not a throughput guarantee.
No new test suite, fixture, workflow, external dependency, or separate
replay of accepted earlier proofs was introduced.

## Coverage and remaining construction

The result establishes the endpoint-zero axial-edge class in the relative
interior of one Dirichlet boundary face for degrees four and five. Its
twelve signed transports, exact translations, and positive isotropic
scales preserve the stated source image, protected output, and bound.

The full boundary and vertex census, interactions at intersections of
Dirichlet planes, global assembly, and conversion to a mesh-uniform
pressure-norm estimate remain separate work. A finite-patch coefficient
bound alone is not the global Scott-Vogelius inf-sup theorem.

The accepted geometry, protected-map algorithm, mean basis, elevation and
physical checker retain their existing source and review attribution.
This construction makes no sponsor contact, new-paper, current-prize,
eligibility, submission, award, or payment claim.
