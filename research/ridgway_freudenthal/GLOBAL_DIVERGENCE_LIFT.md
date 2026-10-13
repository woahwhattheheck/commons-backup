# Global divergence constructor

Issue: https://github.com/woahwhattheheck/commons/issues/14999

`global_divergence_lift.py` constructs a continuous, zero-boundary velocity
of degree four or five whose divergence is the complete supplied
piecewise-polynomial pressure on a uniform Kuhn cube mesh. It applies the
minimum-energy mean lift, every required vertex lift, every required
edge-interior lift, and the element-bubble inverse in that order.

The output contains one shared vector Bernstein coefficient per global
coefficient node. Its final check reconstructs every pressure coefficient
from the assembled field, both on the reference mesh and after exact
physical translation and scaling. This includes face and element interiors.

The implementation covers n-by-n-by-n meshes with n at least two.
[The global bound](GLOBAL_DIVERGENCE_BOUND.md) proves the corresponding
mesh-independent right-inverse estimate on the actual divergence image;
that guide treats n=1 separately by finite-dimensional existence.
The current executable uses the displayed two-cube local patches and
therefore does not accept n=1.

## Runtime and direct use

Python 3.10+, standard library only. The direct runtime files are:

- `global_divergence_lift.py`, the composed constructor;
- `global_lift_operators.json`, the retained production matrices;
- `global_patch_plan.py`, the mesh census and coordinate maps;
- `mean_energy_lift.py`, the reusable exact mean solve;
- `cell_bubble_lift.py`, `p4_mean_repair.py` and `kuhn.py`,
  whose exact geometry, Bernstein-index and integration helpers are imported.

No local vertex or edge constructor is run. The production matrix asset
contains the unit-reference operators obtained from their retained actual
outputs. Its source records retain the exact provenance and coordinate
normalization. The global program validates the matrix dimensions and free
source coordinates, then binds their original target labels to each
planned patch. It reports the asset's byte count, SHA-256 and Git blob.

A complete pressure JSON has `n`, `degree`, optional `origin` and
`cell_size`, and `pressure_coefficients`. Run:

```sh
python research/ridgway_freudenthal/global_divergence_lift.py \
  pressure.json --energy --output global-velocity.json
```

The existing mean constructor also emits a valid complete pressure array.
Its `subdivisions` and `cell_divergence_coefficients` fields are accepted
as aliases:

```sh
python research/ridgway_freudenthal/mean_energy_lift.py \
  --subdivisions 2 --degree 4 --output mean-field.json

python research/ridgway_freudenthal/global_divergence_lift.py \
  mean-field.json --energy --output reconstructed-field.json
```

Alternatively, start with an existing shared continuous Dirichlet velocity
in the same coefficient format:

```sh
python research/ridgway_freudenthal/global_divergence_lift.py \
  supplied-velocity.json --from-velocity --energy \
  --output lifted-divergence.json
```

That mode computes the complete divergence of the supplied field, then
constructs a velocity with the same divergence. The two velocities need
not coincide, because their difference can lie in the divergence kernel.
A nonzero boundary coefficient, duplicate node or node outside the specified
mesh is rejected before this conversion.

The output path must be new. If writing fails, the command removes only a
partial file whose device and inode still identify the file it created.
An existing output is preserved. Without `--output`, complete JSON goes
to stdout; with it, stdout contains a compact result summary.

The optional `--energy` flag integrates all nine gradient components in
the exact Bernstein Gram form. The regular output already includes a
rigorous upper bound assembled from the component estimates.

## Pressure and coordinate conventions

For degree k, every tetrahedron has all degree-(k−1) normalized Bernstein
coefficients, in `p4_mean_repair.indices(k-1)` order. There are 20 rows
per cell for k=4 and 35 for k=5. The pressure arrays follow cube x, then y,
then z, then the six positive `kuhn_tets()` entries.

A coefficient is the multiplier of a normalized Bernstein polynomial.
It is not the value at that Bernstein node. Consequently the cell mean is
the arithmetic average of all coefficients in the cell's pressure array.
The total of those cell means must be zero because all tetrahedra have
the same volume and the velocity has zero boundary trace.

All numerical input values are integers or exact rational strings.
Floating-point and Boolean coefficient values are rejected.
The physical map is x = a + hξ, where ξ lies in [0,n]³,
a is the three-coordinate origin and h is the positive cube size.
The default h=1/n produces the unit cube.

The global algorithm stores integer reference coefficient nodes N and
rational reference velocity coefficients c internally. Physical output is:

- coefficient node multiplied by k: k a + h N;
- velocity coefficient: h c;
- cell vertices: a + h ξ.

Thus divergence coefficients are unchanged by transport. Squared H1
seminorms, pressure L2 norms squared and cell integrals scale by h³.

The returned physical `nodes_times_degree` array contains only nodes with
a nonzero velocity vector. Divide each displayed coordinate by k to locate
the coefficient node. Every omitted coefficient is zero.

## Preparing once and applying several times

```python
import sys
sys.path.insert(0, "research/ridgway_freudenthal")

from global_divergence_lift import prepare, construct

prepared = prepare(n=2, degree=4)
first = construct(q1, n=2, degree=4, prepared=prepared)
second = construct(q2, n=2, degree=4, prepared=prepared,
                   integrate_energy=True)
```

Here q1 and q2 are complete arrays of 48 tetrahedron pressure arrays.
The preparation retains the geometry, pressure-index maps, normalized local
operators and patch bindings. The first application assembles the mean
energy matrix; subsequent applications reuse that factorization for new
cell means.

`load_operators(path)` loads another exact copy of the production asset
and reports its byte provenance. Pass its result as `operators=...`
to `prepare`. A caller may also pass the actual JSON product of
`global_patch_plan.construct` as `plan=...`; its degree, mesh and
physical placement must agree. These are reuse interfaces, not mechanisms
for silently changing the source-space or mesh conventions.

`pressure_from_velocity(value, prepared)` is the API equivalent of
`--from-velocity`. It returns a canonical pressure-input object after
validating the shared coefficient positions and zero exterior trace.

## Binding one retained local operator

Each matrix entry retains its unit-reference cell, coefficient-node,
target-coordinate and source-column ordering. For a selected global patch,
the planner records a signed permutation O, reference zero image z and the
local-to-global cell map.

If O reverses orientation, the planner swaps local tetrahedron vertices 1
and 2 to keep a positive cell orientation. To read a pressure target, the
global constructor first applies that vertex permutation to the retained
Bernstein multi-index, then uses the planner's cell-position map. This
preserves the original reference endpoint order even when inversion
reverses an edge's canonical low-to-high order.

For every patch, the set of mapped target labels must equal its entire
global incident star:

- one vertex coefficient for every incident tetrahedron;
- k−2 interior coefficients for every incident edge/tetrahedron pair.

The program refuses a missing, duplicate or extra target label. It also
requires that the retained reference cell order equal the planner's actual
template order and that every mapped coefficient node belong to the
global mesh.

Let t be that complete local trace, S its retained source matrix, and f the
coordinates selected by the retained free-row indices. The application
requires t = S f exactly and then computes the sparse matrix product B f.
This keeps the source relations for singular and Dirichlet classes.
A zero-dimensional source is represented by empty rows and admits only
the zero complete trace.

The local coefficient at reference node N is sent to k z + O N and its
vector value to O c. Contributions from all patches are added at the same
global node. A single dictionary value at every shared Bernstein node
gives the common coefficient trace across adjacent tetrahedra.

## The four stages

### 1. Minimum-energy means

The constructor averages each pressure array and gives those cell means
to `mean_energy_lift.py`. The mean stage minimizes H1 energy in the full
continuous P1 vector plus normal cubic face-bubble space, subject to those
means.

It subtracts the mean field's **complete polynomial divergence**.
The remaining cell means are exactly zero. Vertex and edge coefficients
may have changed and are extracted from this new residual.

The mean solver is the only global factorization. On the n=2 grid its
75-coordinate velocity space reduces to 28 free coordinates after
47 independent mean constraints. The saved local mean-repair elimination
is never invoked by the global program.

### 2. All vertices

For every mesh vertex, the planner chooses the contained patch and source
class. The global program extracts all incident vertex coefficients from
the stage's residual, applies the retained compatible map, and sums the
resulting fields.

Each local map preserves all other vertex targets, every edge-interior
coefficient and all cell means. The program therefore extracts all traces
from the same residual, then subtracts the divergence of the whole vertex
stage once. It requires every vertex coefficient and every cell mean to be
zero afterward, and separately requires that this stage changed no
edge-interior coefficient.

| Vertex class | Complete source dimension | Reference patch |
| --- | ---: | --- |
| Interior | 18 | Eight cubes |
| Face | 8 | Four cubes |
| Same-side crease | 5 | Two cubes |
| Mixed-side crease | 0 | Two cubes |
| Same-side corner | 3 | Two cubes |
| Mixed-side corner | 0 | Two cubes |

All 26 lower/upper boundary-vertex orientations occur in the census.
The retained matrices are their common reference operators; the planner
supplies the appropriate signed coordinate map.

### 3. All edge interiors

The constructor extracts the remaining k−2 interior pressure coefficients
on every incident tetrahedron of each mesh edge. The body-diagonal,
interior-face, boundary-face, interior-axial, boundary-axial and both
boundary-crease classes cover every Kuhn edge.

These local operators preserve all vertices, all other edge interiors and
all cell means. After summing and subtracting their divergence, every
pressure coefficient supported on at most two local vertices is zero.
All cell means remain zero.

### 4. Element bubbles

The remaining pressure is exactly the element-local residual space of
[CELL_BUBBLE_LIFT.md](CELL_BUBBLE_LIFT.md). The constructor applies that
guide's explicit inverse directly. It does not build another local matrix.

For k=4 there is one vector coefficient at alpha=(1,1,1,1).
For k=5 there are four vector coefficients, at the multi-indices obtained
by doubling one entry of (1,1,1,1). Using the accepted free pressure rows,
a row whose missing barycentric coordinate is j and doubled coordinate is
s contributes q/k times (v_j−v_s) to the corresponding velocity vector.
For k=4 use s=0 and the three independent face rows.

Every velocity multi-index is strictly positive, so the field vanishes
on all four faces of its tetrahedron. Zero extension preserves all
neighboring elements. The program subtracts the complete divergence and
requires every remaining coefficient to be zero.

Finally it reconstructs the divergence of the *sum* of all four stages,
then repeats that reconstruction using the returned physical cells,
coefficients and physical barycentric gradients. Both arrays must equal
the original supplied pressure exactly.

## Why the local source tuples are compatible

The relevant pressure space is Q = div V, where V is the actual continuous
degree-k vector space with zero boundary trace.

For q in Q, every constructed stage lies in V: the local maps have zero
patch-boundary trace, every patch is contained in the mesh, and the global
coefficient dictionary gives a shared continuous trace. Subtracting the
divergence of a constructed field therefore leaves the residual in Q.

At every step, the extracted local tuple is thus the trace of an actual
residual velocity's divergence. It belongs to the complete local source
image identified by the corresponding reference construction, including
the Dirichlet zero-dimensional classes. This is the compatibility
argument; it does not assume that unrelated pressure constraints define Q.

Conversely, whenever the program returns a successful result, the displayed
continuous Dirichlet velocity and full exact reconstruction certify that
the supplied pressure is in its divergence image. An incompatible-source
error identifies the class, global target, coordinate and nonzero residual.
An input, file or resource error is not a mathematical source-space
classification.

## Norm information and the uniform estimate

Each output stage records a rigorous upper bound for its squared reference
H1 seminorm. The mean bound is its independently integrated exact energy.
For vertices and edges, local bounds are summed and multiplied by the
conservative overlap counts 64 and 448. The element bubbles have disjoint
interiors, so their coefficient estimates add directly.

For four component fields v_j, the inequality
`||sum_j grad(v_j)||² ≤ 4 sum_j ||grad(v_j)||²`
gives the returned input-specific upper bound. Its physical value is
multiplied by h³.

When `--energy` is selected, the program also differentiates the assembled
field in its exact degree-(k−1) Bernstein basis and integrates the nine
gradient components against the full Gram matrix. This includes cross
terms between the four stages. That exact energy must not exceed the
component upper bound. The observed energy-to-pressure ratio concerns the
supplied input and is not presented as an optimal uniform constant.

The mesh-independent estimate in
[GLOBAL_DIVERGENCE_BOUND.md](GLOBAL_DIVERGENCE_BOUND.md) goes further.
It bounds coefficient extraction through the full reference pressure
Gram inverse, uses complete-star coverage to count each extracted
(cell, Bernstein index) once, and applies the fixed overlap bounds.
Combining these estimates with the mean and bubble bounds gives a
right-inverse constant independent of n for each fixed degree.
The file gives the explicit composed expression and its n=1 extension.

## Cost and retained work

All matrix applications are rational sparse products. The reference asset
is fixed for each degree, and a new mesh changes only patch selection and
index transport. No old local source elimination, stored mean-repair
construction or local proof run is repeated.

The minimum-energy mean solver currently factors a dense reduced system
of dimension 9n³−15n²+9n−2. Its exact field-operation cost is cubic in that
dimension, with additional integer bit growth. The global executable is
therefore intended for small exact grids. The uniform mathematical estimate
does not imply that this dense solver is an efficient implementation for
large n.

Output size includes every input and reconstructed pressure coefficient,
every nonzero shared velocity node, the mesh census and per-patch stage
summaries. Detailed patch geometry can be obtained separately from the
planner. The generated field and exact residuals are the concrete product;
no sponsor disposition, payment or submission follows from the program's
successful execution.
