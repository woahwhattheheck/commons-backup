# Protected boundary face-diagonal lifts

This construction continues [the Freudenthal research lane](https://github.com/woahwhattheheck/commons/issues/14999)
using the accepted [protected-map construction](FACE_DIAGONAL_LIFT.md), the
[two-cube quartic mean repair](P4_MEAN_REPAIR.md), and the
[coordinate-transport argument](FACE_DIAGONAL_TRANSPORT.md). It concerns the
diagonal of one Dirichlet boundary face, with continuous quartic or quintic
velocities.

The implemented `boundary_face_diagonal_lift.py` constructs a protected,
zero-cell-mean lift for every compatible target. The actual Dirichlet source
relation is equality of the two incident traces in each interior mode, leaving
two free coordinates at degree four and three at degree five. The final
reference maps have only four and five nonzero scalar coefficients. Both obey
a reference seminorm-squared bound of $72$ times the complete compatible
trace-coordinate norm squared. Exact transport covers the lower and upper
versions of all three coordinate-normal faces.

## Reference geometry and trace coordinates

The reference patch, Dirichlet plane, and ordered target edge are
$$
\widehat\Omega=[0,2]\times[0,1]^2,\qquad
\widehat\Gamma=\{x=0\},\qquad
\widehat e=[(0,0,0),(0,1,1)].
$$
The two cubes contain twelve tetrahedra in the unchanged order of `kuhn.py`:
the six cells of the first cube, followed by the six cells translated by
`(1,0,0)`. The target has two incident cells, **3 and 5**, with positively
oriented vertex lists
$$
K_3=((0,0,0),(0,1,0),(0,1,1),(1,1,1)),
$$
$$
K_5=((0,0,0),(0,1,1),(0,0,1),(1,1,1)).
$$

Set $m=k-2$. A target trace consists of the degree-$(k-1)$ divergence
Bernstein coefficients with positive powers at both ordered endpoints. The
coefficient with power $j=1,\ldots,m$ at the second endpoint occurs at
$$
\beta^{(3)}_j=(k-1-j,0,j,0),\qquad
\beta^{(5)}_j=(k-1-j,j,0,0).
$$
The complete target vector is cell-major:
$$
y=(y_{3,1},\ldots,y_{3,m},y_{5,1},\ldots,y_{5,m}).
$$
It has four coordinates at degree four and six at degree five. These are
Bernstein coefficients, not point samples. Both endpoint divergence values are
protected at zero, as are all edge-supported divergence coefficients outside
this interior target list.

The output velocity has zero trace on the **entire patch boundary**. That is
stronger than the physical Dirichlet restriction used to identify necessary
source relations: the source-star calculation below removes coefficients on
$x=0$ only and retains coefficients on all other faces of the two-cell star.
Keeping these two spaces distinct is essential.

## Actual Dirichlet source image

Let $V^k_\Gamma(\operatorname{star}\widehat e)$ be the continuous piecewise
degree-$k$ vector space on $K_3\cup K_5$ with zero velocity trace on $x=0$.
Let $S$ map its shared Bernstein coefficients to the complete interior target
vector. No artificial outer-star boundary condition or source endpoint
restriction is imposed.

For a tetrahedron $K$ with barycentric coordinates $\lambda_i$, the divergence
coefficient is
$$
d_{K,\beta}
 =k\sum_{i=0}^3\nabla\lambda_i\cdot v_{K,\beta+e_i}.
$$
In either incident cell, all vertices except $(1,1,1)$ lie on $x=0$.
For a target index $\beta_j$, the coefficients obtained by incrementing one
of those three boundary-vertex powers are Bernstein coefficients of the
Dirichlet face and vanish. The barycentric coordinate of $(1,1,1)$ is $x$
in both cells, so its gradient is $(1,0,0)$.

The remaining coefficient has the same degree-scaled geometric node in both
cells:
$$
p_j=(1,j+1,j+1).
$$
It lies on the shared triangular face. Continuity identifies its vector
coefficient between the two tetrahedra. If $c_{p_j,x}$ denotes its first
component, then
$$
d_{K_3,\beta^{(3)}_j}
 =k\,c_{p_j,x}
 =d_{K_5,\beta^{(5)}_j}.
$$
The equality follows from the actual continuous Dirichlet source space.
It is not an assumed condition on an independently chosen discontinuous
pressure space.

With
$$
H=\begin{bmatrix}I_m&-I_m\end{bmatrix},
\qquad
B=\begin{bmatrix}I_m\\I_m\end{bmatrix},
$$
the exact source-row identity is
$$
HS=0,\qquad \operatorname{range}B=\ker H.
$$
Thus every admissible complete target vector has the form $y=Bz=(z,z)$.
The free vector $z$ has two coordinates at degree four and three at degree
five. The norm conversion is exact:
$$
\|y\|_2^2=2\|z\|_2^2.
$$

Conversely, the shared nodes $p_j$ are distinct and not on $x=0$.
Setting $c_{p_j,x}=z_j/k$ and all other source coefficients to zero already
shows that the Dirichlet source map has image $\operatorname{range}B$.
This argument concerns the source space; it need not protect the other edge
traces or cell means. A protected lift supplies those additional conditions.

The same source count can be obtained without imposing an artificial star
boundary: two tetrahedra share one triangular face, and their two Dirichlet
faces share the target edge. The number of retained scalar Bernstein nodes is
$$
2\binom{k+3}{3}-3\binom{k+2}{2}+(k+1).
$$
The native source-row enumeration records the corresponding vector coefficient
count and checks the equality of each pair of target rows exactly.

## Protected construction and unchanged source compatibility

Let $V^k_0(\widehat\Omega)$ be the continuous patch-boundary-zero velocity
space. In its shared coefficient coordinates, let $P$ collect all protected
edge rows, $T$ collect the complete target rows, and $M$ collect the twelve
cell-average divergence rows. The exact protected solves construct a raw operator from free target
coordinates to velocity coefficients satisfying
$$
P R_{\rm raw}=0,\qquad T R_{\rm raw}=B.
$$
Each returned column is a genuine continuous finite-element field. Its restriction
to $K_3\cup K_5$ lies in $V^k_\Gamma(\operatorname{star}\widehat e)$, so the
constructed protected inverse realizes every source-compatible target in the
smaller patch-boundary-zero space:
$$
\operatorname{range}B
 =\operatorname{range}(T R_{\rm raw})
 \subseteq\operatorname{range}S
 \subseteq\ker H
 =\operatorname{range}B.
$$
Exact rational matrix identities extend to every real free target vector.
For rational data, the returned velocity coefficients are rational.

The construction succeeds in both degrees. Its exact counts are:

| Reference quantity | Degree four | Degree five |
|---|---:|---:|
| Patch tetrahedra | 12 | 12 |
| Source-star retained Bernstein nodes | 30 | 55 |
| Source-star scalar coefficient unknowns | 90 | 165 |
| Complete target coordinates | 4 | 6 |
| Free source dimension | 2 | 3 |
| Patch scalar coefficient unknowns | 189 | 432 |
| Protected edge rows / rank | 188 / 120 | 258 / 172 |
| Combined protected-and-target rank | 122 | 175 |
| Final operator shape | 189 × 2 | 432 × 3 |
| Final nonzero scalar coefficients | 4 | 5 |
| Checked edge rows | 192 | 264 |
| Checked zero-mean rows | 12 | 12 |

The rank increments are $122-120=2$ and $175-172=3$, exactly the free source
dimensions. The returned matrices and reconstructed identities establish
surjectivity onto the equal-trace source space, including the protected
endpoint-zero condition.

For interpreting another patch, the rank increment
$$
\dim T(\ker P)
 =\operatorname{rank}\begin{bmatrix}P\\T\end{bmatrix}
  -\operatorname{rank}P
$$
describes the image of that protected patch space. A failed protected solve
alone would not prove an additional relation on the unrestricted Dirichlet
source star. Necessary source relations must be justified on that source
space, as the identity $HS=0$ is here.

## Removing all cell means without changing the edge traces

Let $w=R_{\rm raw}z$ and $m=Mw$. Every reference tetrahedron has volume $1/6$.
Continuity cancels interior face fluxes, while the exterior velocity trace is
zero, hence
$$
\frac16\sum_{K=0}^{11}m_K
 =\int_{\widehat\Omega}\operatorname{div}w\,dx
 =\int_{\partial\widehat\Omega}w\cdot n\,dS
 =0.
$$
The raw means therefore lie in the zero-sum domain of the accepted two-cube
quartic repair.

Write $C_4$ for that repair expressed as a map on all twelve zero-sum cell
means. Its stored eleven columns act on the first eleven means; the twelfth
is their negative sum. The correction has the prescribed cell means, zero
divergence on every edge, and zero patch-boundary velocity trace.

For degree four use $C_4$ directly. For degree five, the existing exact
elevation helper represents this same eleven-column quartic correction as
degree five. Componentwise on each cell,
$$
(E_5b)_\alpha
 =\sum_{\substack{0\le i\le3\\\alpha_i>0}}
    \frac{\alpha_i}{5}\,b_{\alpha-e_i},
\qquad |\alpha|=5.
$$
Degree elevation changes the Bernstein representation, not the polynomial.
It preserves continuity, boundary values, divergence edge traces, and cell
means. Let $E_4$ be the identity representation.

The combined operator is
$$
R=R_{\rm raw}-E_k C_4 M R_{\rm raw}.
$$
Because the correction has zero divergence on every edge and removes exactly
the raw cell means,
$$
PR=0,\qquad TR=B,\qquad MR=0.
$$
The velocity still vanishes on the entire patch boundary. Thus the repair
does not change the source image or introduce another compatibility relation.
The existing local repair and elevation are reused; no new mean solver is
required.

## Compact form of the final reference operator

The actual sparse result can be written without its full coefficient matrix.
Let $z=(z_1,\ldots,z_m)$ and let the coordinates below be multiplied by the
velocity degree. The only nonzero **vector** Bernstein coefficients are
$$
c_{(1,2,2)}=\frac{z_1}{k}(1,1,1),
\qquad
c_{(1,j+1,j+1)}=\frac{z_j}{k}(1,0,0)
\quad(2\le j\le k-2),
\qquad k\in\{4,5\}.
$$
All other patch coefficients, including all boundary coefficients, are zero.
This describes two vector coefficient nodes at degree four and three at
degree five; the first vector contributes three scalar matrix entries, giving
four and five nonzero scalar entries in total.

These are the final coefficients after the stated mean-repair composition.
The exact edge and mean checks apply to this sparse result. The expression
is asserted here for the constructed degrees four and five.

## A bound in free and complete trace-coordinate norms

Let $R$ be the **final**, mean-corrected coefficient matrix, and define its
maximum squared scalar row norm by
$$
\rho_k=\max_r\sum_{\ell=1}^{m}R_{r\ell}^2.
$$
The sparse matrix acts on $z$, so every scalar velocity coefficient satisfies
$$
|c_r|^2\le\rho_k\|z\|_2^2.
$$
For a vector coefficient, summing over the three components gives
$\|c\|_2^2\le3\rho_k\|z\|_2^2$.

On any unit Kuhn tetrahedron, the squared barycentric gradient norms sum to
$1+2+2+1=6$. The Bernstein derivative identity is
$$
\nabla v
 =k\sum_{|\beta|=k-1}B^{k-1}_\beta
       \sum_{i=0}^3c_{\beta+e_i}\otimes\nabla\lambda_i.
$$
The nonnegative Bernstein weights sum to one. Jensen's inequality, followed
by Cauchy–Schwarz for the four derivative terms, gives the pointwise bound
$$
|\nabla v|_F^2
 \le k^2\cdot6\cdot4\cdot3\,\rho_k\|z\|_2^2.
$$
The reference patch has volume two, so
$$
|Rz|_{H^1(\widehat\Omega)}^2
 \le144\,k^2\rho_k\|z\|_2^2.
$$
For a compatible complete trace $y=Bz$, define $L_k y=Rz$. Since
$\|y\|_2^2=2\|z\|_2^2$, the complete-trace version is
$$
|L_k y|_{H^1(\widehat\Omega)}^2
 \le72\,k^2\rho_k\|y\|_2^2.
$$

The final coefficient matrices give $\rho_4=1/16$ and $\rho_5=1/25$:

| Reference quantity | Degree four | Degree five |
|---|---:|---:|
| Maximum squared scalar row norm $\rho_k$ | $1/16$ | $1/25$ |
| Free-coordinate seminorm-squared bound $144k^2\rho_k$ | $144$ | $144$ |
| Complete-trace seminorm-squared bound $72k^2\rho_k$ | $72$ | $72$ |

Thus, for either constructed degree and every compatible complete trace,
$$
|L_k y|_{H^1(\widehat\Omega)}^2\le72\|y\|_2^2.
$$

These are conservative finite-patch bounds in Bernstein trace-coefficient
norm. They are neither optimized constants nor bounds stated in pressure
$L^2$ norm. The quantity bounded is the velocity **seminorm squared**.

## Six-face coordinate transport

Let the cyclic permutation matrix $Q$ map reference component $i$ to physical
component $P[i]$:
$$
P_x=(0,1,2),\qquad P_y=(1,2,0),\qquad P_z=(2,0,1).
$$
Choose $s=+1$ for a lower face or $s=-1$ for an upper face, and set
$$
O=sQ,\qquad
F(\xi)=a+hO\xi,\qquad
(\mathcal T v)(F(\xi))=hO v(\xi),
\qquad a\in\mathbb Q^3,\quad h\in\mathbb Q_{>0}.
$$
Then $O^TO=I$ and $\det O=s$. The physical boundary plane is
$x_{P[0]}=a_{P[0]}$. The patch extends toward increasing normal coordinate for
a lower face and decreasing normal coordinate for an upper face.

| Face normal | Reference-to-physical component map | Lower-face edge displacement | Upper-face edge displacement |
|---|---|---|---|
| $x$ | $(0,1,2)$ | $h(0,1,1)$ | $-h(0,1,1)$ |
| $y$ | $(1,2,0)$ | $h(1,0,1)$ | $-h(1,0,1)$ |
| $z$ | $(2,0,1)$ | $h(1,1,0)$ | $-h(1,1,0)$ |

In every case the **ordered** physical edge starts at $a$ and ends at $F(0,1,1)$.
For an upper face, $a$ is the coordinatewise upper corner of the physical patch:
uniform inversion reverses all three coordinates. It is not a reflection of
the normal coordinate alone.

### Kuhn cells and positive orientation

A coordinate permutation sends a monotone coordinate-step chain to another
such chain, and the Kuhn triangulation contains all six step orders.
Uniform inversion sends a chain to a reversed chain in the corresponding
translated cube. Reading that chain in reverse again gives a positive
coordinate-step chain. Consequently all six choices of $O=sQ$ preserve the
geometric Kuhn tetrahedra on the transformed rectangular grid.

For $s=+1$, the local vertex order is inherited unchanged. For $s=-1$, the
affine image initially has determinant $-h^3$. The output relabels each
tetrahedron by
$$
\sigma=(0,2,1,3),\qquad
K^{\rm phys}_i=F(\widehat K_{\sigma(i)}),
$$
and applies the same permutation to every local Bernstein multi-index:
$$
\beta^{\rm phys}_i=\widehat\beta_{\sigma(i)}.
$$
This one transposition restores the determinant to $h^3$ and leaves the
represented polynomial unchanged.

Global node order, cell order, and target-row order remain inherited. The
ordered target endpoints are not exchanged; the recorded power is still the
power at the inherited second endpoint. The local vertex/barycentric
relabelling supplies the matching physical representation, so it does not
reverse the target modes or change the equality relation.

### Divergence, source compatibility, and means

The chain rule gives
$$
\nabla_x(\mathcal Tv)(F(\xi))
 =O\,\nabla_\xi v(\xi)\,O^T,
$$
and therefore
$$
\operatorname{div}_x(\mathcal Tv)(F(\xi))
 =\operatorname{div}_\xi v(\xi).
$$
There is no extra sign for an upper face. Both the spatial and vector
transformations use the same orthogonal map.

After the simultaneous barycentric relabelling, every divergence Bernstein
coefficient equals its reference coefficient. Thus the complete target vector,
its relation $Hy=0$, the protected zero rows, and zero endpoint coefficients
are preserved.

The inverse transformation is
$$
v(\xi)=h^{-1}O^T v_{\rm phys}(a+hO\xi).
$$
It maps the physical continuous Dirichlet source star bijectively to the
reference one and respects the inherited target coordinates. Consequently the
physical source image is exactly $\ker H$ in both directions, not merely a
subset proved by transporting outputs.

The volume Jacobian is $|\det(hO)|=h^3$, including when $s=-1$. Thus the
cell-average divergence is unchanged:
$$
\frac1{|F(K)|}\int_{F(K)}
 \operatorname{div}(\mathcal Tv)\,dx
 =\frac1{|K|}\int_K\operatorname{div}v\,d\xi.
$$
Zero means and zero patch-boundary velocity trace transport as well.

### Seminorm and sparse coefficient scaling

Orthogonal conjugation preserves the Frobenius norm. Hence
$$
|\mathcal Tv|_{H^1(F(\widehat\Omega))}^2
 =h^3|v|_{H^1(\widehat\Omega)}^2.
$$
Both the free-coordinate and complete-trace seminorm-squared bounds are
multiplied by $h^3$. The full velocity $L^2$ norm squared scales by $h^5$,
so a full $H^1$ norm should not be substituted for this seminorm statement.

For a reference scalar coefficient row indexed by node $n$ and component $c$,
the physical row is indexed by the same node and component $P[c]$ and is
multiplied by $sh$. Thus its squared row norm scales by $h^2$; the sign has
no effect on that norm. Reference and physical row-norm metadata must remain
distinct from the $h^3$ energy scaling.

The physical degree-scaled node is
$$
k a+hO\,n_{\rm ref}.
$$
Its entries are exact rational strings in `nodes_times_degree`; divide by $k$
for the geometric location. These locations index continuous Bernstein
coefficients and do not turn the coefficients into point samples.

## Interface and exact construction evidence

The Python interface is:

```python
construct_reference(degree=4)
transport(operator, normal_axis="x", side="lower", origin=(0, 0, 0), scale=1)
construct(degree=4, normal_axis="x", side="lower", origin=(0, 0, 0), scale=1)
apply(operator, trace)
```

`construct_reference` returns the reusable reference operator. `transport`
accepts that reference result, leaves it unchanged, and returns a reusable
physical operator; application-specific `requested_trace` and
`velocity_coefficients` fields are removed from the copied reference result.
`construct` combines the two operations and returns a physical operator even
for the default identity transform.

`apply` takes the **complete** four- or six-coordinate trace as a list and
returns vector Bernstein coefficients in the recorded node order. It requires
equality of the two cell blocks. Its sparse `basis` acts on the first block,
as recorded by `free_coordinate_indices`, while `source_basis` is $B=[I;I]$.
An incompatible pair raises `ValueError` with the one-based mode and exact
residual; the CLI reports the error and exits 1 before opening its output.
Accepted numeric values are exact integers, rational strings, or
`fractions.Fraction` values in process. Booleans and floating-point values are
not exact numeric inputs to this interface.

### CLI examples

```sh
python research/ridgway_freudenthal/boundary_face_diagonal_lift.py \
  --degree 4 --all-faces --origin=-2,1/3,5/2 --scale 3/2 \
  --trace 1,2,1,2 --output quartic-boundary-face-lifts.json

python research/ridgway_freudenthal/boundary_face_diagonal_lift.py \
  --degree 5 --all-faces --origin=2/5,-1,7/3 --scale 2/3 \
  --trace 1/2,-1/3,2,1/2,-1/3,2 --output quintic-boundary-face-lifts.json
```

Use Python 3.10+ with the standard library and the existing adjacent source
files and `p4_mean_repair_basis.json`. Output paths must be new; omitting
`--output` writes JSON to stdout. Omitting `--trace` returns the reusable
operator without an applied velocity. A single face can be selected with
`--face x-lower`, `x-upper`, `y-lower`, `y-upper`, `z-lower`, or `z-upper`;
`--face` and `--all-faces` are mutually exclusive. The default is `x-lower`.

Both `--origin` and `--trace` take one comma-separated argument. Use the
`--origin=...` or `--trace=...` spelling when the first entry is negative.
The scale must be positive. `--all-faces` constructs the reference once and
reuses it for the six signed transports.

### Output contract

| Result | Schema | Status |
|---|---|---|
| Reference | `freudenthal-boundary-face-diagonal-lift/v1` | `CONSTRUCTED` |
| One physical face | `freudenthal-boundary-face-diagonal-transport/v1` | `TRANSPORTED_AND_CHECKED` |
| All six faces | `freudenthal-boundary-face-diagonal-batch/v1` | `TRANSPORTED_AND_CHECKED` |

The batch contains an `operators` dictionary with the six hyphenated face
keys. Each physical operator carries its own cells, degree-scaled nodes,
ordered target coordinates, sparse velocity basis, and exact identity
certificate.

`reference_to_physical_component` records $P$ and `coordinate_sign` records
$s$. The field `physical_vertex_to_reference_vertex` is `[0,1,2,3]` for a
lower face and `[0,2,1,3]` for an upper face. `dirichlet_face` records the
physical axis, exact plane coordinate, and `interior_side` as `positive` or
`negative`. The source-boundary description concerns the source star; the
returned velocity still has zero trace on the entire patch boundary.

`maximum_squared_coefficient_row_norm` is the physical $h^2\rho_k$, with
`reference_maximum_squared_coefficient_row_norm` retaining $\rho_k$. The two
bound fields `h1_squared_bound_from_free_l2` and
`h1_squared_bound_from_target_l2` contain $144h^3$ and $72h^3$ respectively.
Their `reference_`-prefixed counterparts retain $144$ and $72$.

The `physical_identity_check` reconstructs barycentric gradients from the
actual physical cell coordinates, including division by the exact
determinant. It checks every free basis column against every target and
protected edge row, all twelve mean rows, positive cell orientation, and
the omission of boundary velocity coefficients. Its fields include
`basis_columns`, `edge_rows`, `target_rows`, `protected_rows`,
`zero_mean_rows`, `boundary_trace`, `edge_residual_max`, and
`mean_residual_max`. The last two are the exact strings `"0"`.
This physical reconstruction also checks the simultaneous upper-face
vertex and barycentric relabelling.

### Completed native construction

The two parameter sets shown above completed on Python 3.12.14/Linux with
exit 0. All six face choices were constructed for each degree. Every
reported physical edge and cell-mean residual was exactly zero for every
free basis column. The actual retained outputs are named
`quartic-boundary-face-lifts.json` and `quintic-boundary-face-lifts.json`.

| Executed quantity | Degree four | Degree five |
|---|---|---|
| Origin | $(-2,1/3,5/2)$ | $(2/5,-1,7/3)$ |
| Scale $h$ | $3/2$ | $2/3$ |
| Complete trace | $(1,2,1,2)$ | $(1/2,-1/3,2,1/2,-1/3,2)$ |
| Face choices checked | All six | All six |
| Physical squared row norm | $9/64$ | $4/225$ |
| Physical free-coordinate bound | $486$ | $128/3$ |
| Physical complete-trace bound | $243$ | $64/3$ |

The existing eleven-column mean basis was loaded and composed, and its
existing quintic elevation was reused. The new construction introduced no
external dependency, test suite, fixture, or workflow change.

## Coverage and attribution

This result concerns one endpoint-zero boundary face-diagonal class in degrees
four and five, with the Dirichlet condition on its boundary plane. The six-face
transport covers the three cyclic normal directions and their lower/upper
versions, together with exact translation and positive isotropic scaling.

It does not establish the complete boundary-star or vertex census, the full
global source-space characterization, a global assembly algorithm, or a
mesh-uniform Scott–Vogelius theorem. The fixed two-cube patch and its
coefficient-norm bound remain part of the statement.

The accepted Kuhn geometry, protected-map solver, local mean repair,
degree-elevation routine, and previous interior constructions retain their
source and review attribution under the existing research issue. No sponsor
contact, new paper, current prize availability, eligibility, submission,
acceptance, or payment claim follows.
