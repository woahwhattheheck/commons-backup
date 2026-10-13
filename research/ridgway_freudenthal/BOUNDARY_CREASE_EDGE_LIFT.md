# Protected lifts at two Dirichlet planes

This construction extends the [original Freudenthal research lane
#14999](https://github.com/woahwhattheheck/commons/issues/14999) and its
[initial contribution #30041](https://github.com/woahwhattheheck/commons/pull/30041).
It uses the retained [quartic mean repair](P4_MEAN_REPAIR.md), its stored
eleven-column basis, the accepted quintic degree elevation, and the generic
physical identity reconstruction from
[coordinate transport](FACE_DIAGONAL_TRANSPORT.md).
The [boundary axial construction](BOUNDARY_AXIAL_EDGE_LIFT.md) supplies the
shared coordinate utilities. Those results and sources remain unchanged.

[`boundary_crease_edge_lift.py`](boundary_crease_edge_lift.py) constructs the two
straight box-edge source classes considered here in degrees `4` and `5`.
The same-side, two-cell source has full interior divergence-trace image:
four complete coordinates at degree four and six at degree five. The
mixed-side, one-cell source has zero image: each of its two or three complete
coordinates must vanish. This zero-image conclusion follows directly from
the actual Dirichlet source rows.

For every admissible complete trace, the output is a continuous vector
Bernstein field on a twelve-cell patch. It matches that trace, has zero
divergence on every other tetrahedral edge, has zero endpoint divergence,
has all twelve cell-average divergences zero, and has zero velocity on the
entire patch boundary. Both source classes transport exactly to all twelve
choices of tangent axis and two lower/upper coordinate-face sides.

This is a finite local construction and source characterization. It does not
prove a mesh-uniform inf-sup theorem or perform global assembly.

## 1. Two reference stars and the trace coordinates

Use the standard positively oriented Kuhn triangulation of

$$
\widehat\Omega=[0,2]\times[0,1]\times[0,1].
$$

The existing two-cube geometry numbers its twelve tetrahedra by the first
cube's six cells followed by the second cube's six cells. Each has volume
`1/6`. The reference edges are parallel to the second coordinate axis.

| Reference class | Dirichlet planes | Ordered target edge | Actual incident cells |
|---|---|---|---|
| `same` | `x=0` and `z=0` | `(0,0,0) → (0,1,0)` | `2,3` |
| `mixed` | `x=0` and `z=1` | `(0,0,1) → (0,1,1)` | `5` |

The relevant positive local vertex orders are

$$
\begin{aligned}
K_2&=((0,0,0),(1,1,0),(0,1,0),(1,1,1)),\\
K_3&=((0,0,0),(0,1,0),(0,1,1),(1,1,1)),\\
K_5&=((0,0,0),(0,1,1),(0,0,1),(1,1,1)).
\end{aligned}
$$

Let `k` be `4` or `5` and set `m=k-2`. Divergence has degree `k-1`.
At each incident cell, the target consists of the `m` interior Bernstein
coefficients on the ordered edge. The endpoint coefficients are excluded
from the target and protected at zero in the output.

For `j=1,...,m`, give the high endpoint power `j` and the low endpoint power
`k-1-j`. Target rows are ordered first by reference cell index and then by
`j`. Thus the complete trace vector is

$$
y=(y_{2,1},\ldots,y_{2,m},y_{3,1},\ldots,y_{3,m})
$$

for `same` and

$$
y=(y_{5,1},\ldots,y_{5,m})
$$

for `mixed`. These are Bernstein coefficients, not values sampled at points.

The source space used to determine admissible traces is continuous vector
piecewise `P_k` on the incident star, zero on the two stated Dirichlet
planes. Its other star boundaries are unrestricted. The constructed
output has the stronger condition of zero velocity on all of
`∂Ω̂`. Consequently, source characterization and protected
extension are separate parts of the construction.

## 2. Exact source image

For a cell with barycentric coordinates `λ_i` and vector Bernstein
coefficients `c_α`,

$$
v|_K=\sum_{|\alpha|=k}c_\alpha B_\alpha^k,\qquad
(\operatorname{div}v)_{\beta,K}
 =k\sum_{i=0}^3\nabla\lambda_i\cdot c_{\beta+e_i},
 \quad |\beta|=k-1.
$$

Shared coefficients are indexed by the degree-scaled physical node

$$
p=\sum_{i=0}^3\alpha_i a_i.
$$

The program retains every source-star node except those on either
Dirichlet plane, then reconstructs the divergence rows from the actual
cell gradients. Continuity is imposed by the shared node index, and the
Dirichlet conditions by omitting the corresponding coefficients.

### 2.1 Same-side class: all target coordinates are independent

The two cells share the face with vertices `(0,0,0)`, `(0,1,0)` and
`(1,1,1)`. At mode `j`, the sole retained coefficient appearing in either
target row is the common coefficient at

$$
C_j=(1,j+1,1).
$$

Here and below `C_j` is a degree-scaled node; the physical coefficient
location is `C_j/k`.

On `K_2` the off-edge vertex `(1,1,1)` has barycentric coordinate `z`.
All other contributions to the edge row lie on `z=0` and vanish. On
`K_3` that same off-edge vertex has barycentric coordinate `x`, and all
other contributions lie on `x=0`. Hence the actual source rows are

$$
y_{2,j}=k\,c_z(C_j),\qquad
y_{3,j}=k\,c_x(C_j),\qquad 1\le j\le m.
$$

These rows have no nontrivial linear relation. Given any complete `y`,
set

$$
c(C_j)=\frac1k\bigl(y_{3,j},\,0,\,y_{2,j}\bigr)
$$

and set every other retained source coefficient to zero. The shared
coefficients agree across the common face, and neither Dirichlet plane
contains `C_j`. This is an explicit continuous source realization of
every `y∈R^{2m}`.

The exact constructor also obtains a right inverse of the reconstructed
source rows. Its `reference_source_rows` record exactly the two formulas
above, including the cell, Bernstein index, common node, component and
factor `k`. The source basis is the identity matrix of size `2m`;
`compatibility_relations` is empty.

The number of retained scalar nodes is

$$
N_{\rm same}(k)
 =2\binom{k+3}{3}-3\binom{k+2}{2}+(k+1).
$$

This counts the two tetrahedral node sets, identifies the common face,
and removes the two Dirichlet faces with their common edge counted once.
It gives `30` nodes at degree four and `55` at degree five, or `90` and
`165` scalar component unknowns. The source rank is respectively `4`
and `6`.

### 2.2 Mixed-side class: every target coefficient is zero

Only `K_5` meets the target edge. In its stated vertex order, the
Dirichlet face `x=0` is `λ_3=0` and the Dirichlet face `z=1` is
`λ_0=0`. A source coefficient survives only if both

$$
\alpha_0>0,\qquad \alpha_3>0.
$$

The edge index at mode `j` is

$$
\beta=(0,j,k-1-j,0).
$$

Each derivative contribution has index `β+e_i`. Such an index cannot
have both its zeroth and third entries positive. Every contribution is
therefore a prescribed zero boundary coefficient:

$$
y_{5,j}=0,\qquad 1\le j\le m.
$$

Equivalently, each scalar component of the cell polynomial is divisible
by the product of the two distinct affine face equations. On their
intersection, every first derivative of that product times a polynomial
vanishes. The Bernstein argument above directly matches the implemented
rows.

The retained scalar source-node count is

$$
N_{\rm mixed}(k)=\binom{k+1}{3},
$$

which gives `10` and `20` nodes, or `30` and `60` component unknowns.
The program verifies that every reconstructed target row is identically
empty. Its source rank and dimension are zero, its source basis has
`m` rows and zero columns, and its compatibility matrix is the
`m×m` identity.

Thus `y=0` is necessary. It is also sufficient: the zero field on the
whole patch satisfies every requested condition. This is an intrinsic
source relation for this stated one-cell Dirichlet star, established
before considering protected extension. It is not an inference from a
failed finite-patch solve.

## 3. Protected extension and mean removal

For each degree, use the existing continuous two-cube coefficient space
with all patch-boundary velocity coefficients omitted. It has `63`
interior vector nodes at degree four and `144` at degree five, hence
`189` and `432` scalar component unknowns.

Let `T` contain the selected target divergence rows. Let `P` contain
every remaining edge row, including endpoint rows. The geometry includes
all divergence Bernstein indices supported on at most two vertices, so
zero protected rows give zero polynomial divergence on every other
tetrahedral edge and zero divergence at the target endpoints.

Let `B` be the source basis: `I_{2m}` for `same` or the empty-width
`m×0` matrix for `mixed`. Exact rational elimination constructs `A_0`
with

$$
P A_0=0,\qquad T A_0=B.
$$

The same-side source therefore has a protected right inverse on this
fixed patch. For the mixed-side class, `A_0` has zero columns and
represents the zero field.

Let `M` map coefficients to the twelve cell-average divergences.
Every raw column is continuous and zero on the whole patch boundary.
The divergence theorem and equal cell volumes therefore give

$$
\sum_{\ell=0}^{11}(M A_0)_{\ell j}=0.
$$

The program checks this identity exactly. For the same-side class, all
four quartic raw columns and all six quintic raw columns have some
nonzero cell mean.

The stored quartic mean-repair columns realize
`e_j-e_11` for `j=0,...,10` and have zero divergence on all edges and
zero patch-boundary velocity. Write their operator as `L_4`. At
degree five, use its existing exact Bernstein elevation `E_{4→5}`:

$$
L_5=E_{4\to5}L_4.
$$

Elevation represents the same polynomial, so it preserves all edge
divergences, boundary traces and cell means. In the current two-cube
ordering the accepted eleven-column elevation helper applies directly.

For a zero-sum mean vector `q`, use its first eleven entries as
coordinates in the basis `e_j-e_11`. The final operator is

$$
A=A_0-L_k M A_0.
$$

Here `L_k M` means that zero-sum-coordinate composition. It satisfies

$$
P A=0,\qquad T A=B,\qquad M A=0.
$$

Continuity and the omitted boundary coefficients are preserved. This
composition reuses the stored mean-repair basis; it does not reconstruct
the prior mean-repair proof. For the zero-dimensional mixed-side source,
no mean correction or degree elevation is needed, and neither is run.

### Exact reference results

| Quantity | Same, `k=4` | Same, `k=5` | Mixed, `k=4` | Mixed, `k=5` |
|---|---:|---:|---:|---:|
| Incident cells | `2,3` | `2,3` | `5` | `5` |
| Source scalar nodes | 30 | 55 | 10 | 20 |
| Source component unknowns | 90 | 165 | 30 | 60 |
| Complete target coordinates | 4 | 6 | 2 | 3 |
| Source dimension/rank | 4 | 6 | 0 | 0 |
| Patch component unknowns | 189 | 432 | 189 | 432 |
| Protected rows | 188 | 258 | 190 | 261 |
| Protected rank | 118 | 169 | 122 | 175 |
| Combined edge rank | 122 | 175 | 122 | 175 |
| All edge rows | 192 | 264 | 192 | 264 |
| Cell-mean rows | 12 | 12 | 12 | 12 |
| Final matrix shape | `189×4` | `432×6` | `189×0` | `432×0` |
| Final nonzero scalar entries | 78 | 524 | 0 | 0 |
| Raw columns needing mean removal | 4 | 6 | 0 | 0 |
| Maximum squared coefficient-row norm `ρ` | `5/8` | `162/1225` | `0` | `0` |
| Reference squared-seminorm bound | `1440` | `23328/49` | `0` | `0` |

The ranks in this table refer to the reconstructed finite matrices,
with their duplicate geometric edge rows retained. They do not
constitute a global source-space rank calculation.

## 4. A finite-degree coefficient bound

For the final same-side matrix define

$$
\rho=\max_r\sum_j A_{rj}^2.
$$

Each scalar coefficient obeys

$$
|c_r(y)|^2\le\rho\|y\|_2^2.
$$

On each reference Kuhn tetrahedron,

$$
\sum_{i=0}^3|\nabla\lambda_i|^2=6.
$$

For any scalar velocity component `w`, its gradient is

$$
\nabla w
 =k\sum_{|\beta|=k-1}B_\beta^{k-1}
       \sum_{i=0}^3\nabla\lambda_i\,c_{\beta+e_i}.
$$

Nonnegativity and partition of unity of the Bernstein basis, followed
by Cauchy–Schwarz over the four derivative coefficients, imply

$$
|\nabla w|^2
 \le k^2\cdot6\cdot4\,\rho\|y\|_2^2.
$$

There are three scalar velocity components and reference patch volume
two. Integrating gives

$$
|v(y)|_{H^1(\widehat\Omega)}^2
 \le144\,k^2\rho\,\|y\|_2^2.
$$

For the actual final matrices,

$$
|v_4(y)|_{H^1(\widehat\Omega)}^2\le1440\|y\|_2^2,
\qquad
|v_5(y)|_{H^1(\widehat\Omega)}^2
 \le\frac{23328}{49}\|y\|_2^2.
$$

These are conservative bounds in the complete trace-coefficient norm,
not optimal constants or nodal-value norms. The mixed-side source
contains only `y=0` and its chosen output is exactly zero, so its bound
is zero. No estimate on inadmissible nonzero mixed-side data is claimed.

## 5. Twelve orientations and exact coordinate transport

Choose a tangent axis `t`. Let `(r,n)` be the other two axes in
`x,y,z` order. Reference components `(x,y,z)` map to physical
components `(r,t,n)`. If `Q` is that permutation matrix, the component
lists and parity are:

| Tangent `t` | Ordered normal axes `(r,n)` | Reference-to-physical component list | `det Q` |
|---|---|---|---:|
| `x` | `y,z` | `(1,0,2)` | `-1` |
| `y` | `x,z` | `(0,1,2)` | `+1` |
| `z` | `x,y` | `(0,2,1)` | `-1` |

Specify a lower/upper side for each normal axis. The two reference
classes cover these choices as follows:

| First normal side | Second normal side | Reference class | Sign `s` | Reference second plane |
|---|---|---|---:|---|
| lower | lower | `same` | `+1` | `z=0` |
| lower | upper | `mixed` | `+1` | `z=1` |
| upper | lower | `mixed` | `-1` | `z=1` |
| upper | upper | `same` | `-1` | `z=0` |

Set `O=sQ`. For exact rational `a∈Q³` and `h>0`, use

$$
F(\xi)=a+hO\xi,\qquad
v_{\rm phys}(x)=hO\,\widehat v(F^{-1}(x)).
$$

The first physical Dirichlet plane has coordinate `x_r=a_r` and
interior sign `s`. If the reference second-plane coordinate is
`z_0∈{0,1}`, its physical coordinate is

$$
x_n=a_n+s h z_0.
$$

For `z_0=0` its interior sign is `s`; for `z_0=1` its interior sign
is `-s`. These are the named lower/upper sides recorded in
`dirichlet_faces`.

The translation `a` is the image of the reference origin; it need not
be the minimum corner of the physical patch. Each batch entry is its
own transformed two-cube patch. The twelve entries are not an assembly
of twelve edges on a single fixed box with one common minimum corner.
The ordered edge endpoints are inherited under `F`, including when
their tangent coordinate decreases.

### Why the triangulation is preserved

A Kuhn cube contains the monotone vertex chain for every permutation of
the three coordinate directions. Permuting coordinate directions
permutes those chains. Uniform coordinate negation reverses each chain
after translation to the reflected cube. Thus coordinate permutations,
uniform negation, translation and positive isotropic scale preserve this
Kuhn triangulation as a geometric cell complex.

In three dimensions,

$$
\det O=s\det Q.
$$

If this determinant is positive, inherit each local vertex order. If
it is negative, swap local vertices `1` and `2`. The resulting
physical-to-reference local index permutation is

$$
\pi=(0,2,1,3).
$$

This restores positive tetrahedral determinant. Apply the identical
permutation to each target Bernstein multi-index:

$$
a_i^{\rm phys}=F(a_{\pi(i)}^{\rm ref}),\qquad
\beta_i^{\rm phys}=\beta_{\pi(i)}^{\rm ref}.
$$

Cell, shared-node, target-row, mode and ordered-edge-endpoint order remain
inherited. This relabelling does not re-sort cells or nodes.

A degree-scaled reference node `p` becomes

$$
p_{\rm phys}=k a+hO p.
$$

The output stores these physical scaled nodes as exact rational
strings. Its sparse scalar coefficient row `3ℓ+i` moves to
`3ℓ+P[i]` and its value is multiplied by `s h`. No source-coordinate
permutation is needed: target rows retain their reference order.

### Divergence and source compatibility commute

Differentiating the transport gives

$$
\nabla_x v_{\rm phys}(x)
 =O\,\nabla_\xi\widehat v(\xi)\,O^T,
\qquad \xi=F^{-1}(x),
$$

and therefore

$$
\operatorname{div}_x v_{\rm phys}(x)
 =\operatorname{div}_\xi\widehat v(\xi).
$$

Barycentric coordinate functions are pulled back with the recorded local
index permutation. Target Bernstein coefficients are consequently
unchanged. Zero protected edge divergence and zero endpoint divergence
transport, as do continuity and zero velocity on both physical
Dirichlet planes and on the full patch boundary.

The inverse velocity transform is

$$
\widehat v(\xi)=h^{-1}O^T v_{\rm phys}(F(\xi)).
$$

It preserves the source-star degree, continuity and the two Dirichlet
conditions, and commutes with divergence in the reverse direction.
Thus the transported source image is exactly the reference image:
full `R^{2m}` in the same-side class, and `{0}` in the mixed-side
class. Both necessity and sufficiency follow from this invertible
map.

Cell integrals scale by `h³` and cell volumes also scale by `h³`.
Cell-average divergences are unchanged, so all twelve zero means
transport.

### Seminorm and coefficient scaling

Orthogonal conjugation preserves the Frobenius norm, and the absolute
Jacobian determinant is `h³`. Therefore

$$
|v_{\rm phys}|_{H^1(F(\widehat\Omega))}^2
 =h^3|\widehat v|_{H^1(\widehat\Omega)}^2.
$$

The physical same-side bounds are `1440 h³` for degree four and
`(23328/49)h³` for degree five, in the unchanged complete trace norm.
The maximum squared coefficient-row norm separately scales by `h²`.
These different factors are stored explicitly; the reference bound
formula is not reapplied to the already scaled row norm.

## 6. API, output and exact admission

The public functions are:

```python
construct_reference(degree=4, edge_class="same")

transport(
    operator,
    tangent_axis="y",
    side_first="lower",
    side_second="lower",
    origin=(0, 0, 0),
    scale=1,
)

construct(
    degree=4,
    tangent_axis="y",
    side_first="lower",
    side_second="lower",
    origin=(0, 0, 0),
    scale=1,
)

apply(operator, trace)
```

`side_first` and `side_second` refer to the normal axes in the ordered
pair from the orientation table. `transport` consumes a constructed
reference operator whose `edge_class` matches the requested side pair.
It returns a new physical operator. `construct` performs those steps
together. `apply` consumes a list of complete trace coefficients and
returns the vector Bernstein coefficient triples in the shared node
order.

Degrees other than `4` or `5` are rejected. Origins, scales and trace
entries use exact integer or rational input; Python `Fraction` values
are supported. Floats and booleans are rejected, and scale must be
strictly positive. Complete trace lengths are `4/6` for `same` and
`2/3` for `mixed`. Any nonzero mixed-side entry is rejected by the
source compatibility condition. The construction itself extends by
linearity to real admissible traces; the interface uses rational data
to retain exact certificates.

The reference schema is
`freudenthal-boundary-crease-edge-lift/v1`. A physical operator uses
`freudenthal-boundary-crease-edge-transport/v1`. An all-edge batch uses
`freudenthal-boundary-crease-edge-batch/v1` with an `operators`
dictionary.

The twelve keys encode the tangent axis and the two named normal sides:

| Tangent | Available keys |
|---|---|
| `x` | `x-y-lower-z-lower`, `x-y-lower-z-upper`, `x-y-upper-z-lower`, `x-y-upper-z-upper` |
| `y` | `y-x-lower-z-lower`, `y-x-lower-z-upper`, `y-x-upper-z-lower`, `y-x-upper-z-upper` |
| `z` | `z-x-lower-y-lower`, `z-x-lower-y-upper`, `z-x-upper-y-lower`, `z-x-upper-y-upper` |

Each operator includes:

- Explicit positively oriented physical `cells`, exact physical
  `nodes_times_degree`, the ordered `target_edge` and target labels.
- `basis_shape` and sparse triples `[scalar_row,column,value]`;
  omitted patch-boundary velocity coefficients are zero.
- The source basis, compatibility relations and actual
  `reference_source_rows`. Those recorded source rows deliberately use
  reference cells and reference degree-scaled nodes, including inside a
  physical operator; their coordinate semantics are explicit.
- Permutation, coordinate sign, local vertex relabelling and the two
  physical Dirichlet faces with coordinates and interior sides.
- Reference and physical squared coefficient-row norms and squared
  seminorm bounds. `shape` counts cubes in the permuted directions;
  `reference_shape` retains `[2,1,1]`.
- `source_identity_check` and `physical_identity_check`.

The physical checker reconstructs barycentric gradients using actual
rational determinants, rebuilds all physical edge and mean rows, and
checks each source-basis column against the transported source basis.
It records the number of basis columns, edge rows, target and protected
rows, and zero-mean rows, with exact maximum residual strings `"0"`.

For `mixed`, there are zero basis columns. Its empty-column physical
certificate accompanies the literally zero output and explicit geometry;
the proof that nonzero source traces are inadmissible is the identically
zero source-row calculation in Section 2.2.

## 7. Actual native construction

Python `3.10+` and the standard library are sufficient. The two parameter
sets below completed in the actual program with Python `3.12.14`,
one all-edge command per degree:

```sh
python research/ridgway_freudenthal/boundary_crease_edge_lift.py \
  --degree 4 --all-edges \
  --origin=-1/3,2/5,7/2 --scale 3/2 \
  --same-trace 1,-2,3,-4 --mixed-trace 0,0 \
  --output quartic-boundary-crease-lifts.json

python research/ridgway_freudenthal/boundary_crease_edge_lift.py \
  --degree 5 --all-edges \
  --origin=2/7,-5/3,1/4 --scale 2/3 \
  --same-trace 1/2,-2/3,3/4,-4/5,5/6,-6/7 --mixed-trace 0,0,0 \
  --output quintic-boundary-crease-lifts.json
```

Both exited `0` and produced all twelve physical operators, six from
each source class. Every checked physical target, protected and
cell-mean identity had exact residual zero. The output files also contain
the requested complete trace and applied velocity coefficients.

| Native parameter set | Same-side physical squared row norm | Same-side physical squared-seminorm bound | Elapsed |
|---|---:|---:|---:|
| `k=4`, `h=3/2` | `45/32` | `4860` | `0.400 s` |
| `k=5`, `h=2/3` | `72/1225` | `6912/49` | `0.777 s` |

Mixed-side row norms and bounds were zero in both runs. The first
child's peak RSS was `15,616 KiB`; the cumulative maximum child RSS
across both commands was `18,176 KiB`. These timings and memory readings
describe this execution, not a performance guarantee.

For one edge, use `--edge` and `--trace`. For example, a same-side
quartic trace has four entries. For a mixed-side quartic edge it has two
entries, both zero. In an all-edge batch, the two source classes have
different complete trace lengths, so `--same-trace` and
`--mixed-trace` supply them separately; `--trace` is rejected in
that mode. Omitting traces returns reusable operators.

`--origin` and trace arguments are comma-separated exact vectors.
Use the equals form when the first entry is negative, such as
`--origin=-1/3,2/5,7/2` or `--same-trace=-1,2,-3,4`.
`--edge` and `--all-edges` are mutually exclusive. `--output`
creates a new file and refuses to overwrite an existing path.

## 8. Scope of the result

The construction proves exact admissible source images and protected
zero-cell-mean lifts for these two coordinate Dirichlet-crease classes
at degrees four and five, together with their twelve stated coordinate
and side transports. The same-side extension succeeds on the fixed
two-cube patch. The mixed-side source restriction is proved directly
from its one-cell geometry.

It does not characterize arbitrary boundary geometries, add a vertex
correction, assemble the local lifts on a whole mesh, or bound the
overlap of a global construction. A failure on some other restricted
patch would require separate interpretation; it would not by itself
prove a global source relation. The broader census, actual global
source compatibility and mesh-uniform theorem remain distinct work
under the original research issue. No sponsor disposition, current
prize availability, submission, payment or award is asserted.
