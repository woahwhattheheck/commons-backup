# Body-diagonal transport to all six cube neighbors

The [quartic](P4_BODY_DIAGONAL_LIFT.md) and
[quintic](P5_BODY_DIAGONAL_LIFT.md) reference constructions give protected,
zero-cell-mean body-diagonal lifts on a fixed two-cube Kuhn patch.
`body_diagonal_transport.py` extends those accepted operators to
neighbors `+x`, `-x`, `+y`, `-y`, `+z`, `-z`, with exact rational translation
and positive isotropic scale. This is a usable local extension under
[issue #14999](https://github.com/woahwhattheheck/commons/issues/14999).

The target source space remains all twelve quartic or eighteen quintic interior
edge coefficients. The original geometry, protected lifts, degree elevation,
mean repair and bounds retain their attribution. The new interface selects
the second cube geometrically; it does not implement global patch selection,
the complete class census or a mesh-uniform stability theorem.

## Run the operator

Python 3.10+, standard library only, from the repository root:

```sh
python research/ridgway_freudenthal/body_diagonal_transport.py \
  --degree 4 --all-neighbors --origin=-2,1/3,0 --scale 3/2 \
  --trace=1,-1,2,-2,3,-3,4,-4,5,-5,6,-6 \
  --output /tmp/quartic-body-transports.json

python research/ridgway_freudenthal/body_diagonal_transport.py \
  --degree 5 --all-neighbors --origin=2/7,-3,5/2 --scale 2/3 \
  --trace=1/2,-1,3/2,-2,5/2,-3,7/2,-4,9/2,-5,11/2,-6,13/2,-7,15/2,-8,17/2,-9 \
  --output /tmp/quintic-body-transports.json
```

Use a new output path. Omit `--output` to print JSON; omit
`--trace` to obtain only reusable operators. Choose one direction with,
for example, `--neighbor=-y`; its default is `+x`.
The equals form is needed for option values beginning with a minus sign.

The command composes each reference body lift once with the existing retained
`p4_mean_repair_basis.json`, then reuses that result across all six
directions. It does not rerun the mean-repair elimination. An existing saved
reference body operator can instead be supplied with `--reference PATH`;
its schema must match `--degree`.

| Option | Meaning |
|---|---|
| `--degree` | Quartic (4) or quintic (5) velocity degree. |
| `--neighbor` | One of the six signed directions; default `+x`. |
| `--all-neighbors` | Return all six; mutually exclusive with `--neighbor`. |
| `--origin X,Y,Z` | Lower corner of the central cube for every direction. |
| `--scale H` | Positive exact rational cube side length; default 1. |
| `--reference PATH` | Read a previously constructed reference body operator. |
| `--trace Y` | One comma-separated vector of 12 or 18 exact coefficients. |
| `--output PATH` | Create a new JSON output file. |

These are Bernstein coefficients, not edge samples or nodal interpolation
values. Inputs accept integers and exact rational strings; floating-point
coordinates and coefficients are not part of the exact interface.

## One central cube, six choices

Let the reference patch be
$
\widehat\Omega=[0,2]\times[0,1]^2,\qquad
\widehat e=[(0,0,0),(1,1,1)].
$
The first six tetrahedra lie in the central reference cube, and the remaining
six lie in its positive-x neighbor.

Write the chosen sign as $s\in\{-1,+1\}$. Reference component $i$ maps to
physical component $P[i]$, using the cyclic permutations below.

| Axis | $P$ | $P(\xi_0,\xi_1,\xi_2)$ |
|---|---|---|
| x | `(0,1,2)` | $(\xi_0,\xi_1,\xi_2)$ |
| y | `(1,2,0)` | $(\xi_2,\xi_0,\xi_1)$ |
| z | `(2,0,1)` | $(\xi_1,\xi_2,\xi_0)$ |

For central-cube lower corner $a\in\mathbb Q^3$ and $h>0$, set
$
\delta=\frac{1-s}{2},\qquad b=a+\delta h(1,1,1),\qquad O=sP,
\qquad \Phi(\xi)=b+hO\xi.
$
Both signs map the first cube to the same physical central cube
$C=a+[0,h]^3$. Its second cube is $C+s h e_{\mathrm{axis}}$.
The negative map reverses all three coordinates and translates them; a
reflection in only one coordinate is not this construction.

A Kuhn tetrahedron is the vertex set of a chain
$0,e_i,e_i+e_j,(1,1,1)$. A coordinate permutation permutes these six chain
sets. Central inversion reverses each chain, producing another of the same
six sets. Hence every displayed choice preserves the underlying Kuhn mesh
in each cube. The selected two-cube patch must lie in the actual domain.

Cell indices stay in reference order. They are not sorted by physical
coordinates. The same is true of shared coefficient nodes, target columns,
and target endpoints.

## Endpoint and local vertex order

The ordered endpoints are
$
(\Phi(0),\Phi(1,1,1))=
\begin{cases}
(a,\ a+h(1,1,1)),&s=+1,\\
(a+h(1,1,1),\ a),&s=-1.
\end{cases}
$
For each inherited target cell 0 through 5, the target columns have
`high_endpoint_power = j`, $j=1,\ldots,k-2$, and endpoint powers
$(k-1-j,j)$. “High” means the reference endpoint $(1,1,1)$, now the
second returned endpoint. For a negative direction that is the physical
lower endpoint. The program never silently reverses the trace vector.

A caller using a separate physical lower-to-upper convention must explicitly
map its incident-cell order and reverse the mode index
$j\mapsto(k-1)-j$ for negative directions. Giving the same raw vector to all
six operators means the same inherited coordinates; it need not mean the
same trace after an external geometric reordering.

All cyclic $P$ have determinant $+1$, while $\det O=s$. Positive
directions retain local vertex order. Negative directions use
$
r=(0,2,1,3),\qquad
a^{\mathrm{phys}}_i=\Phi(\widehat a_{r(i)}),\qquad
\beta^{\mathrm{phys}}_i=\widehat\beta_{r(i)}.
$
The vertex swap restores positive determinant $h^3$. Target betas happen
to use only endpoint slots 0 and 3, but the implementation still applies
the complete relabeling rule. Global node identities and target columns
are unchanged.

## Velocity and divergence

For a reference polynomial velocity $\widehat v$, define
$
v(\Phi(\xi))=hO\widehat v(\xi).
$
This is a bijection of continuous piecewise degree-$k$ vector fields,
including the subspaces with zero patch-boundary trace. Its inverse is
$\widehat v(\xi)=h^{-1}O^T v(\Phi(\xi))$.

With $(Dv)_{ij}=\partial_j v_i$, the chain rule gives
$
D_xv(\Phi(\xi))=O(D_\xi\widehat v)(\xi)O^T,\qquad
\operatorname{div}_x v(\Phi(\xi))
=\operatorname{div}_\xi\widehat v(\xi).
$
Thus the divergence is a scalar pullback with no sign or amplitude factor.
All three velocity components receive the sign $s$.

After vertex relabeling,
$
\lambda_i^{\mathrm{phys}}(\Phi(\xi))
=\widehat\lambda_{r(i)}(\xi),\qquad
\nabla_x\lambda_i^{\mathrm{phys}}
=h^{-1}O\nabla_\xi\widehat\lambda_{r(i)}.
$
In the Bernstein divergence formula
$
d_{K,\beta}=k\sum_{i=0}^3
\nabla\lambda_i\cdot v_{\beta+e_i},
$
the factors $h^{-1}O$ and $hO$ cancel in their scalar product.
Consequently the ordered target coefficients are reproduced exactly,
every other-edge coefficient and endpoint value remains zero, and cell
average divergences remain zero. Cell integrals acquire $h^3$, so their
zero values are also preserved.

The accepted reference target map is onto $\mathbb R^{12}$ for P4 or
$\mathbb R^{18}$ for P5. This coordinate bijection preserves that full
source image. There is no checkerboard relation or reduced target basis
for this body-diagonal class.

## Exact representation and physical reconstruction

A reference shared node label $N=k\widehat x$ becomes
$
N_{\mathrm{phys}}=k b+hON.
$
The output uses `nodes_times_degree`; dividing by $k$ gives the physical
Bernstein-node coordinate. The degree-specific reference node key is removed,
so no stale reference-coordinate alias remains.

A sparse entry `[3*n+c, j, value]` becomes
`[3*n+P[c], j, h*s*value]`. The node and target indices retain their
meanings. Nonzero counts remain 270 and 1,763, respectively.

The new module reuses
`face_diagonal_transport.check_physical_operator` with the full identity
matrix as `source_basis`. This checker rebuilds barycentric gradients
from the returned physical cells, including their determinants. It then
reconstructs every divergence edge row and every cell-average row using
the returned nodes and basis. It does not copy a reference residual report.

For every returned basis column, target rows must equal the identity and
all protected rows and means must be zero. There are 192 edge rows for P4
and 264 for P5, including vertices. Means use all divergence Bernstein
coefficients, with average weights $1/20$ and $1/35$, respectively.
There are twelve zero-mean rows in either degree. Shared geometric node
keys represent continuous traces; omitted boundary coefficients are zero.

The retained quartic mean operator has 189 rows and eleven columns, with
ordered targets $e_j-e_{11}$, $j=0,\ldots,10$.
The P4/P5 reference constructors now optionally accept
`construct(mean_repair=operator)`, normalize JSON list coordinates for
geometry comparison, and retain their existing final combined-field
identities. Their no-argument behavior remains available. The transport's
default construction passes the retained operator directly; P5 uses its
existing exact degree elevation on those same eleven columns.

For the source used here, the retained mean-basis Git blob is
`c0082bea8230f6d52ae98d77a996095d46c4b713` and its SHA-256 is
`a4aea9b89bbd72a3bef36e1856da518b865421d51c39a88af737ba807b73e82c`.
A constructed reference records the digest it actually consumed.

## Seminorm bound and scope

Orthogonal invariance of the Frobenius norm and
$|\det D\Phi|=h^3$ give
$
|v|_{H^1(\Phi(\widehat\Omega))}^2
=h^3|\widehat v|_{H^1(\widehat\Omega)}^2
\le h^3 C_k\|y\|_{\ell^2}^2,\qquad
C_4=1728,\quad C_5=\frac{39744}{49}.
$
The norm of the inherited trace vector is unchanged. A permutation into a
caller's separately defined cell/endpoint ordering also preserves that
Euclidean norm.

This is the squared H1 **seminorm** in trace-coefficient norm.
The squared velocity L2 norm scales by $h^5$; the full H1 norm does not
have a single $h^3$ factor. No pressure-L2 extraction constant, global
assembly bound, mesh-uniform theorem, new publication, sponsor submission,
prize award or payment follows from this local result.

## API and output

```python
reference_operator(degree=4)
transport(operator, neighbor="+x", origin=(0, 0, 0), scale=1)
construct(degree=4, neighbor="+x", origin=(0, 0, 0), scale=1)
apply(operator, trace)
```

`transport` accepts an already constructed P4/P5 reference result and
does not mutate it. Saved application fields are removed before transport.
`apply` returns the physical vector Bernstein coefficients in the same
shared-node order.

A single result has schema `freudenthal-body-diagonal-transport/v1`.
A batch has schema `freudenthal-body-diagonal-transport-batch/v1` and
six complete operators indexed by the neighbor strings. Each has status
`TRANSPORTED_AND_CHECKED`, explicit coordinate/order metadata,
the inherited reference bound, the scaled bound, and its exact
`physical_identity_check`. A supplied trace adds canonical rational
`requested_trace` and `velocity_coefficients` fields.

## Actual execution

Both commands shown above completed successfully on October 3, 2026.
Each composed one reference using the retained mean basis and returned all
six neighbor operators. All twelve returned physical operators had exact
edge and mean residuals `"0"`.

| Degree | Scale | Matrix shape | Nonzeros per neighbor | Edge rows | Target rows | Protected rows | Mean rows | Scaled squared-seminorm bound |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 4 | $3/2$ | $189\times12$ | 270 | 192 | 12 | 180 | 12 | $5832$ |
| 5 | $2/3$ | $432\times18$ | 1,763 | 264 | 18 | 246 | 12 | $11776/49$ |

The two native calls took approximately 0.247 and 0.577 seconds and had a
maximum child-process resident set of 20,864 KiB. All eight consumed source
and retained-basis files were unchanged by execution. The mean solver,
completed earlier constructions, external certificate suites and sponsor
submission roads were not separately rerun.
