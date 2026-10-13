# Protected Dirichlet boundary-vertex lifts

Issue: https://github.com/woahwhattheheck/commons/issues/14999

`boundary_vertex_lift.py` constructs P4 and P5 lifts of every compatible
divergence tuple at a vertex on an axis-aligned Kuhn box boundary. Five
reference classes generate all 26 face, crease and corner orientations.
Their full Dirichlet source dimensions are 8, 5, 0, 3 and 0.

For each compatible tuple, the returned continuous velocity has zero outer
patch trace. Its divergence matches the central-vertex values, vanishes at
every other vertex and every edge-interior Bernstein coordinate, and has
zero average in every patch tetrahedron. The two mixed-side classes have
only the zero source tuple, so their output is the zero field.

The construction extends the [interior-vertex work](INTERIOR_VERTEX_LIFT.md)
by imposing the actual Dirichlet constraints on the first-derivative source
variables. It then composes the retained interior-edge and grid-mean
operators. This is a fixed-patch vertex result; global pressure-space
assembly and the mesh-uniform theorem remain separate.

## Run or reuse an operator

Python 3.10+, standard library only, from the repository root:

```sh
python research/ridgway_freudenthal/boundary_vertex_lift.py \
  --degree 4 --all-orientations --vertex=-2,1/3,5/2 --scale 3/2 \
  --output boundary-p4.json

python research/ridgway_freudenthal/boundary_vertex_lift.py \
  --degree 5 --all-orientations --vertex=2/7,-3,5/2 --scale 2/3 \
  --output boundary-p5.json
```

`--vertex` is the physical central vertex. `--scale` is a positive exact
rational cube size. The result's `cells` gives the full physical patch;
`boundary_faces` names the domain boundary planes through the central
vertex. Use `--vertex=-2,1/3,5/2` when its first coordinate is negative.

For one orientation, choose an identifier such as:

- `face-y-upper`;
- `crease-x-lower-y-lower`;
- `crease-x-lower-y-upper`;
- `corner-x-lower-y-lower-z-lower`;
- `corner-x-lower-y-lower-z-upper`.

The CLI's choices list all 26 identifiers. A single orientation accepts
`--trace` in its complete `incident_cells` order or `--free-trace` in its
`free_cell_ids` order. These flags are mutually exclusive and cannot be
combined with the all-orientations batch, because source dimensions differ
between classes. An incompatible tuple exits nonzero with the cell ID and
exact residual. Output paths are created exclusively; without `--output`
the JSON goes to stdout.

The reusable API is:

- `construct_reference(degree, kind)` for one of the five reference classes;
- `transport(reference, orientation, vertex, scale)`;
- `construct(degree, orientation, vertex, scale)` for both steps;
- `trace_from_free(operator, values)`;
- `apply(operator, complete_trace)`.

For example, reuse a saved batch without reconstructing the local maps:

```python
import json
from pathlib import Path
from research.ridgway_freudenthal.boundary_vertex_lift import apply, trace_from_free

saved = json.loads(Path("boundary-p5.json").read_text())
operator = saved["operators"]["face-y-upper"]
target = trace_from_free(
    operator, ["1/2", "-1", "3/2", "-2", "5/2", "-3", "7/2", "-4"]
)
coefficients = apply(operator, target)
```

`nodes_times_degree` stores degree times each physical coefficient-node
coordinate. The returned vectors are Bernstein coefficients, not point
samples. A sparse matrix entry `[row, column, value]` uses
`row = 3*node_index + component` and the independent coordinate ordering.
All omitted coefficients are zero. A zero-image class therefore needs no
stored nodes or nonzero coefficients.

## Reference geometry and source dimensions

Cubes follow the existing `grid(shape)` order: Cartesian product in xyz,
with z fastest, followed by the six positively oriented `kuhn.py` cells.
The local chain permutations are `012, 021, 102, 120, 201, 210`, with
vertices 1/2 swapped when needed for positive orientation.

Here, lower and upper refer to the actual domain boundary planes through
the central vertex. A crease is the intersection of two such planes.

| Reference class | Grid shape | Central vertex | Boundary planes | Complete vertex values | Allowed vector variables | Source dimension | Orientations |
|---|---|---|---|---:|---:|---:|---:|
| Face | \((1,2,2)\) | \((0,1,1)\) | lower x | 12 | 4 | 8 | 6 |
| Same-side crease | \((1,1,2)\) | \((0,0,1)\) | lower x, lower y | 8 | 2 | 5 | 6 |
| Mixed-side crease | \((1,1,2)\) | \((0,1,1)\) | lower x, upper y | 4 | 0 | 0 | 6 |
| Same-side corner | \((2,1,1)\) | \((0,0,0)\) | lower x, lower y, lower z | 6 | 1 | 3 | 2 |
| Mixed-side corner | \((2,1,1)\) | \((0,0,1)\) | lower x, lower y, upper z | 2 | 0 | 0 | 6 |

Face patches contain 24 tetrahedra; the other patches contain 12. The
corner patch is extended to two cubes along its reference x axis to reuse
the retained mean repair. Its second cube contributes no additional
central-vertex source row.

The result requires the displayed patch to fit in the domain. In particular,
it does not provide an alternative one-cube corner correction. The
transported `cells` and `reference_shape` make that support requirement
explicit.

## The full Dirichlet first-derivative source

Let \(c\) be the boundary vertex. The continuous degree-\(k\) vertex
coefficient is \(u_c=0\) under Dirichlet conditions. As in the interior case,
only coefficients with multi-index \((k-1)e_c+e_w\) contribute to a derivative
at \(c\). Their shared values \(a_w\) give

\[
q_T=(\operatorname{div}u)|_T(c)
    =k\sum_{w\in T\setminus\{c\}}a_w\cdot\nabla\lambda_w.
\]

A coefficient lying on a domain boundary plane is zero. The only remaining
variables are edge-near coefficients strictly inside all those planes.
The selected node has integer key \((k-1)c+w\); the code also checks that
it is inside the chosen outer patch.

Conversely, any values for the allowed vectors define the continuous field

\[
v_T=\sum_{w\in T\setminus\{c\}}
    a_w B^k_{(k-1)e_c+e_w}
  =\sum_w k a_w\lambda_c^{k-1}\lambda_w,
\]

with all other coefficients zero and zero extension outside the star.
Shared edge coefficients give continuity; omitted boundary coefficients
give the Dirichlet and outer patch traces. At every other vertex the first
derivatives vanish for \(k\ge3\).

This proves that the allowed first-derivative variables describe the full
continuous Dirichlet source image. Higher polynomial coefficients cannot
enlarge it. For the degrees constructed here, the respective scalar jet
spaces have dimensions 12, 6, 0, 3 and 0.

Every Kuhn mesh edge has direction \(\pm\chi_S\): its nonzero coordinate
components all have the same sign. A mixed-side crease or corner would need
an allowed displacement with both positive and negative components to enter
the domain interior. None exists. Their complete vertex divergence tuples
are therefore zero, rather than merely unconstructed.

## Explicit source relations and inverses

Write \(q_i\) for the one-sided central divergence in reference cell \(i\).
The formulas below give \(k a_\delta\), where \(\delta=w-c\).
Every unlisted coefficient is zero. Divide by \(k\) on the reference patch;
physical transport supplies its scale factor once.

### Face vertex

Complete cell order:

```text
3, 5, 8, 9, 16, 17, 18, 19, 20, 21, 22, 23
```

Choose independent cells:

```text
3, 8, 9, 16, 17, 20, 21, 22
```

The four necessary and sufficient relations are

\[
q_5=q_3,\qquad q_{18}=q_{16}-q_{17}+q_{20},\qquad
q_{19}=q_8-q_9+q_{22},\qquad q_{23}=q_{21}.
\]

An explicit inverse is:

| Displacement \(\delta\) | \(k a_\delta\), xyz components |
|---|---|
| \((1,0,0)\) | \((q_3,\ q_3-q_{16},\ q_3-q_8)\) |
| \((1,0,1)\) | \((q_9,\ q_9-q_{22},\ 0)\) |
| \((1,1,0)\) | \((q_{17},\ 0,\ q_{17}-q_{20})\) |
| \((1,1,1)\) | \((q_{21},\ 0,\ 0)\) |

Thus the 12-by-12 jet map has rank 8 and kernel dimension 4.

### Same-side crease vertex

Complete cell order is `4,5,6,7,8,9,10,11`; independent cells are
`4,5,6,7,9`. The relations are

\[
q_8=-q_4+q_5+q_6,\qquad q_{10}=q_7,\qquad q_{11}=q_9.
\]

Use

\[
k a_{(1,1,0)}=(q_5,q_4,q_4-q_6),\qquad
k a_{(1,1,1)}=(q_9,q_7,0).
\]

The 8-by-6 jet map has rank 5 and kernel dimension 1.

### Same-side corner vertex

Complete cell order is `0,1,2,3,4,5`; independent cells are `0,1,3`.
The relations and inverse are

\[
q_2=q_0,\qquad q_4=q_1,\qquad q_5=q_3,\qquad
k a_{(1,1,1)}=(q_3,q_1,q_0).
\]

The 6-by-3 jet map has rank 3.

### Mixed-side classes

The mixed crease's complete cell order is `3,5,8,9`; the mixed corner's
is `4,5`. Each listed value must be zero. Their free coordinate arrays and
coefficient fields are empty.

### Exact source characterization in the constructor

The implementation substitutes these formulas into every central
divergence row. It requires identity on the selected free rows, then checks
that every admissible Dirichlet jet row is the corresponding combination
of those selected rows. The first condition supplies a right inverse;
the second proves that no admissible source direction has been omitted.

This exact rational calculation establishes both directions of the image
description without a floating-point rank threshold or a new large
elimination. The formulas and relations are returned as explicit
`source_basis`, `source_relations` and `free_cell_ids` data.

## Protected edge and mean composition

The raw vertex lift already has zero derivatives at the other vertices.
On an incident edge whose near-center coefficient is forced to zero, its
divergence contains only the central endpoint Bernstein coefficient:
all terms involving another \(\lambda_w\) vanish along that edge.
Consequently only the 4, 2 or 1 strictly inward incident edges need
edge-interior correction.

The retained protected edge operators have zero divergence at all vertices,
zero divergence on every other edge, zero cell means and zero boundary
velocity trace. Subtracting them removes the raw field's edge-interior
coordinates while preserving its vertex source tuple. The implementation
checks each complete edge trace against that operator's actual source image
before applying its free-coordinate basis.

All required patches fit inside the chosen reference boxes:

| Vertex class | Edge corrections |
|---|---|
| Face | one axial, two face-diagonal, one body-diagonal |
| Same-side crease | one face-diagonal, one body-diagonal |
| Same-side corner | one body-diagonal |
| Mixed classes | none |

For the face reference, the two face-diagonal transports use normal axes y
and z with origins \((0,0,1)\) and \((0,1,0)\). Its body lift uses the
negative-y neighbor of the cube with lower corner \((0,1,1)\).
The same-side crease uses the z-normal face map at the origin and the
negative-z body neighbor of cube \((0,0,1)\). The same-side corner uses
the positive-x body neighbor of the origin cube.

Cell vertex sets are mapped back to the complete reference grid. The code
requires every allowed inward edge to occur exactly once and every
correction cell to stay inside the patch.

The means of the combined field are then computed in **all** 24 or 12
tetrahedra, including the extra corner cube. Their sum is zero because
the continuous field has zero outer trace and all tetrahedra have equal
volume. The existing
[rectangular-grid mean repair](P4_GRID_MEAN_REPAIR.md) removes those means
while preserving every vertex and edge divergence coordinate.

The shared `interior_vertex_lift.remove_means` helper now accepts
`shape=...`; its original `(2,2,2)` default is unchanged. The P5 correction
is genuinely degree-elevated from the retained quartic field:

\[
b^5_\alpha=\sum_{i:\alpha_i>0}\frac{\alpha_i}{5}b^4_{\alpha-e_i}.
\]

No old mean solve is called. A batch constructs each edge reference once
per degree and reuses the five vertex references across their orientations.

## Coordinate transport and the 26 orientations

Let \(P\) be a cyclic coordinate permutation, \(s\in\{1,-1\}\), \(h>0\),
and \(a\) the requested physical vertex. For reference center \(c\), use

\[
x=a+hsP(\xi-c),\qquad v_h(x)=hsP\,v(\xi).
\]

The divergence tuple is unchanged in inherited cell order. Reference
lower faces become physical upper faces when \(s=-1\). Permutations and
global sign reversal produce:

- six face orientations;
- six same-side and six mixed-side crease orientations;
- two same-side and six mixed-side corner orientations.

A global sign reversal has negative orientation in three dimensions.
The stored cells therefore swap local vertices 1/2 and their divergence
multi-index entries. Vector rows are permuted and multiplied by \(hs\).
Coefficient nodes transform as
\(ka+hsP(N-kc)\), where \(N\) is the reference degree-scaled node.

The output retains its explicit cell-array order; it does not interpret
reference lattice cell IDs as a newly enumerated physical grid. Target
multi-indices refer to those actual output cells. Both reference and
physical inward-edge direction lists are supplied.

The final physical checker reconstructs all divergence edge/vertex rows
and all cell means from the transported cells, nodes and sparse basis.
Thus negative signs and coordinate permutations are checked against the
returned geometry.

## Exact operators and fixed-patch bounds

The nonzero reference maps are:

| Class | P4 scalar rows × source columns | P4 nonzeros | P5 scalar rows × source columns | P5 nonzeros |
|---|---:|---:|---:|---:|
| Face | 441 × 8 | 399 | 972 × 8 | 1,446 |
| Same-side crease | 189 × 5 | 102 | 432 × 5 | 438 |
| Same-side corner | 189 × 3 | 29 | 432 × 3 | 125 |

Mixed classes return the zero map with shape `0×0`. Each nonzero face map
repairs eight mean columns with 22 retained two-cube applications; the
same-side crease repairs five columns with eight applications; the corner
repairs three columns with three applications.

There are \(n_T(4+6(k-2))\) total vertex/edge divergence rows. The target
and protected counts are:

| Class | Target rows | P4 protected rows | P5 protected rows | Zero cell means |
|---|---:|---:|---:|---:|
| Face | 12 | 372 | 516 | 24 |
| Same-side crease | 8 | 184 | 256 | 12 |
| Mixed-side crease | 4 | 188 | 260 | 12 |
| Same-side corner | 6 | 186 | 258 | 12 |
| Mixed-side corner | 2 | 190 | 262 | 12 |

Let \(A\) be the largest squared Euclidean norm of a scalar coefficient
row, measured against the selected free source coordinates. Those
coordinates are a subset of the complete tuple \(q\).
As in the interior-vertex derivation,
\(\sum_i|\nabla\lambda_i|^2=6\) on a unit Kuhn tetrahedron, and the Bernstein
derivative/partition-of-unity estimate gives

\[
|v|_{H^1(\Omega)}^2
 \le |\Omega|\,3k^2\cdot4\cdot6\,A\|q\|_{\ell^2}^2
 =|\Omega|\,72k^2 A\|q\|_{\ell^2}^2.
\]

Here \(|\Omega|=4\) for faces and 2 for creases/corners. Conservative
reference squared-seminorm constants are:

| Class | P4 bound | P5 bound |
|---|---:|---:|
| Face | \(7416\) | \(120600/49\) |
| Same-side crease | \(1152\) | \(16416/49\) |
| Same-side corner | \(720\) | \(15696/49\) |
| Either mixed class | \(0\) | \(0\) |

Physical transport multiplies these constants by \(h^3\).
They are local bounds in the complete compatible vertex-trace norm.
The missing global pressure-norm and assembly argument is not asserted here.

## Direct use and retained dependencies

Both all-orientation commands above ran successfully: all 52 returned
physical operators matched their source image and had zero protected-edge
and cell-mean residuals. The P5 saved upper-y-face operator was also applied
to the eight independent rational values shown in the API example,
returning 324 coefficient vectors.

A mixed-crease call with `--trace=1,0,0,0` exited 1 with
`incompatible crease_mixed vertex source trace at cell 3: residual 1`
and created no output file. These were direct uses of the new CLI/API;
no old standalone proof suite or new test file was used.

The construction retains the [interior-vertex operator](INTERIOR_VERTEX_LIFT.md),
[axial-edge lift](AXIAL_EDGE_LIFT.md),
[face-diagonal lift and source relation](FACE_DIAGONAL_LIFT.md),
[face transport](FACE_DIAGONAL_TRANSPORT.md),
[body-diagonal transport](BODY_DIAGONAL_TRANSPORT.md),
and [grid mean repair](P4_GRID_MEAN_REPAIR.md), with their existing
source geometry, retained mean coefficients, derivations and attribution.
