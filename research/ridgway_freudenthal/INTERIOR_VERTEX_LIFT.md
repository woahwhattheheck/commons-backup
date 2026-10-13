# Protected interior-vertex lift on eight Kuhn cubes

Issue: https://github.com/woahwhattheheck/commons/issues/14999

`interior_vertex_lift.py` constructs a continuous piecewise-P4 or P5 vector
field on eight cubes around an interior mesh vertex. Its divergence takes any
compatible 24-cell tuple at that vertex, vanishes at every other patch vertex
and at every edge-interior Bernstein coordinate, and has zero average in each
of the 48 tetrahedra. The entire outer velocity trace is zero.

The complete vertex source image has dimension 18, with six explicit
relations. The implementation accepts the complete compatible tuple or its
18 independent coordinates. It uses the existing protected axial,
face-diagonal and body-diagonal operators and the retained quartic mean basis;
it does not repeat the old mean-operator solve.

This is a finite local source-image and protected-lift result. Boundary
vertices, the remaining global compatibility/assembly argument and the
mesh-uniform theorem remain separate.

## Use

Python 3.10+, standard library only, from the repository root:

```sh
python research/ridgway_freudenthal/interior_vertex_lift.py \
  --degree 4 --vertex=-2,1/3,5/2 --scale 3/2 \
  --free-trace=1,-1,2,-2,3,-3,4,-4,5,-5,6,-6,7,-7,8,-8,9,-9 \
  --output vertex-p4.json

python research/ridgway_freudenthal/interior_vertex_lift.py \
  --degree 5 --vertex=2/7,-3,5/2 --scale 2/3 \
  --trace=2,1,-1,3,-2,4,5,11,-3,1,6,-4,7,6,-5,8,-6,9,-7,10,8,-8,23,-18 \
  --output vertex-p5.json
```

`--vertex` is the physical central vertex, not the patch's lower corner.
The patch is `vertex + [-scale, scale]^3`. Scale is positive and exact;
coordinates and traces accept integers or rational strings. A negative first
coordinate can be supplied with `--vertex=-2,1/3,5/2`.

Omit both trace options to construct a reusable sparse operator. An output
path is created exclusively; without `--output` the JSON goes to stdout.
`--trace` and `--free-trace` are mutually exclusive. An incompatible full
tuple exits nonzero with the dependent cell and exact residual, before
construction or output creation.

The API exposes:

- `construct_reference(degree)` on `[0,2]^3`, centered at `(1,1,1)`;
- `transport(reference, vertex, scale)` for exact translation/scaling;
- `construct(degree, vertex, scale)` for both steps;
- `trace_from_free(values)` to form the compatible complete tuple;
- `apply(operator, trace)` to return its vector Bernstein coefficients.

`nodes_times_degree` contains degree times the physical coefficient-node
coordinates. These are Bernstein coefficients, not sampled point values.
A sparse basis entry `[row, column, value]` uses
`row = 3*node_index + component` and the 18-column `free_cell_ids` order.
Application values appear in `velocity_coefficients` with the same node order.
Cell IDs, local vertex order and divergence multi-indices are explicit in
the result.

## Geometry and complete source coordinates

Use the retained `grid((2,2,2))` convention: cubes are enumerated by
`itertools.product(range(2), repeat=3)`, followed by the six `kuhn.py`
tetrahedra. Their chain permutations are `012, 021, 102, 120, 201, 210`;
the stored local vertex order swaps vertices 1 and 2 for negative chain
orientation. The code finds the central local vertex by coordinates.

The reference center is \(c=(1,1,1)\). Its 24 incident global cell IDs, in
complete trace order, are:

```text
0, 1, 2, 3, 4, 5, 6, 8, 13, 16, 18, 19,
27, 29, 32, 33, 40, 41, 42, 43, 44, 45, 46, 47
```

Write \(q_i=(\operatorname{div}u)|_{T_i}(c)\). These are separate one-sided
divergence values; divergence need not be continuous across tetrahedra.

There are 14 mesh edges incident to \(c\): the six axial directions
\(\pm e_i\), the six same-sign face-diagonal directions
\(\pm(e_i+e_j)\), and the two body-diagonal directions
\(\pm(1,1,1)\). In sorted order their displacements are:

```text
(-1,-1,-1), (-1,-1,0), (-1,0,-1), (-1,0,0),
(0,-1,-1), (0,-1,0), (0,0,-1), (0,0,1),
(0,1,0), (0,1,1), (1,0,0), (1,0,1), (1,1,0), (1,1,1)
```

## Why the 42 first-derivative variables give the full source image

On a cell incident to \(c\), let \(u_c\) denote the common degree-\(k\)
vertex Bernstein coefficient and let \(u_{cw}\) denote the coefficient
with multi-index \((k-1)e_c+e_w\). Continuity makes \(u_c\) common to the
star and \(u_{cw}\) common to every cell containing edge \(cw\).

The vertex derivative depends only on these coefficients:

\[
(\operatorname{div}u)|_T(c)
 = k\sum_{w\in T\setminus\{c\}}(u_{cw}-u_c)\cdot\nabla\lambda_w.
\]

This follows directly from the Bernstein derivative formula and
\(\sum_i\nabla\lambda_i=0\). Higher Bernstein coefficients do not contribute
to a derivative at \(c\). Thus every unrestricted continuous piecewise-Pk
source gives 14 shared vectors \(a_w=u_{cw}-u_c\), or 42 scalar variables.

Conversely, any choice of those vectors defines a continuous field by
setting all coefficients to zero except

\[
v_T=\sum_{w\in T\setminus\{c\}}
       a_w B^k_{(k-1)e_c+e_w}
    =\sum_w k a_w\lambda_c^{k-1}\lambda_w.
\]

Use zero on cells outside the star. Faces inside the star inherit the same
shared coefficients. On every star-boundary face \(\lambda_c=0\), so the
field joins continuously to zero. For \(k=4,5\), its value and derivative
vanish at every other vertex. The selected coefficient node has integer key
\((k-1)c+w=kc+(w-c)\).

Consequently, the 24-by-42 matrix \(M\), whose row entries are the applicable
\(\nabla\lambda_w\), describes exactly the full continuous-source vertex
image through \(q=kMa\). It is not a restriction obtained by overlooking
higher polynomial degrees of freedom.

## The six relations and an explicit right inverse

The complete source tuple satisfies:

\[
\begin{aligned}
q_4-q_5-q_6+q_8&=0, &
q_2-q_3-q_{13}+q_{16}&=0,\\
q_0-q_1-q_{27}+q_{29}&=0, &
q_{40}-q_{41}-q_{42}+q_{44}&=0,\\
q_{32}-q_{33}-q_{43}+q_{46}&=0, &
q_{18}-q_{19}-q_{45}+q_{47}&=0.
\end{aligned}
\]

Each is the alternating row relation around one incident singular
face-diagonal edge. They can also be read directly from the barycentric
gradient rows of \(M\). The six dependent cell IDs
`8, 16, 29, 44, 46, 47` occur separately, so the relations are independent.

Choose the other 18 cell IDs as free coordinates:

```text
0, 1, 2, 3, 4, 5, 6, 13, 18, 19, 27, 32, 33, 40, 41, 42, 43, 45
```

The following formulas supply the converse and a usable inverse. Put
\(r_i=q_i/k\) on the reference patch. Set all unlisted vector components
to zero.

| Displacement \(w-c\) | Component | Bernstein coefficient |
|---|---|---|
| \((-1,-1,-1)\) | \(x\) | \(-r_0+r_{27}-r_{43}\) |
| \((-1,-1,-1)\) | \(y\) | \(-r_2+r_{13}-r_{45}\) |
| \((-1,-1,-1)\) | \(z\) | \(-r_4+r_6\) |
| \((-1,-1,0)\) | \(x\) | \(-r_6+r_{32}-r_{43}\) |
| \((-1,-1,0)\) | \(y\) | \(r_4-r_5-r_6+r_{18}-r_{45}\) |
| \((-1,0,-1)\) | \(x\) | \(-r_{13}+r_{40}-r_{42}+r_{45}\) |
| \((-1,0,-1)\) | \(z\) | \(r_2-r_3-r_{13}+r_{18}\) |
| \((-1,0,0)\) | \(x\) | \(-r_{18}+r_{45}\) |
| \((0,-1,-1)\) | \(y\) | \(-r_{27}+r_{40}-r_{42}+r_{43}\) |
| \((0,-1,-1)\) | \(z\) | \(r_0-r_1-r_{27}+r_{32}\) |
| \((0,-1,0)\) | \(y\) | \(-r_{32}+r_{43}\) |
| \((0,0,-1)\) | \(z\) | \(-r_{40}+r_{42}\) |
| \((0,0,1)\) | \(x\) | \(r_{32}-r_{33}-r_{43}\) |
| \((0,0,1)\) | \(y\) | \(r_{18}-r_{19}-r_{45}\) |
| \((0,1,0)\) | \(x\) | \(r_{40}-r_{41}-r_{42}+r_{45}\) |
| \((0,1,0)\) | \(y\) | \(r_{45}\) |
| \((1,0,0)\) | \(x\) | \(r_{43}\) |
| \((1,0,0)\) | \(y\) | \(-r_{42}+r_{43}\) |

Substitution into \(kMa\) gives the identity on the 18 selected rows and
the six displayed dependent-row combinations. Equivalently, with the
sorted neighbor ordering above and xyz component ordering, the selected
column indices are

```text
0, 1, 2, 3, 4, 6, 8, 9, 13, 14, 16, 20, 21, 22, 24, 25, 30, 31
```

and the corresponding 18-row minor of \(M\) has determinant \(-1\).
The six relations and explicit inverse establish rank 18, a 24-dimensional
kernel in the 42-variable jet space, and a six-dimensional cokernel.
No floating-point rank threshold is used. The constructor substitutes the
inverse into all 24 exact vertex rows as part of constructing its operator.

## Protect the edges, then clear the means

The raw vertex field has the required endpoint values, but it can have
nonzero interior divergence coefficients on the 14 incident edges.
Its divergence is zero along nonincident edges: on those edges
\(\lambda_c=0\), and the differentiated raw terms still contain
\(\lambda_c^{k-2}\) or \(\lambda_c^{k-1}\).

For each incident edge, the constructor extracts the raw field's
edge-interior coefficients in the corresponding operator's own cell and
Bernstein-index order. It applies the accepted protected lift and subtracts
it. The component counts and patch sizes are:

| Edge class | Incident edges | Cubes in each correction patch |
|---|---:|---:|
| Axial | 6 | 4 |
| Face diagonal | 6 | 2 |
| Body diagonal | 2 | 2 |

All these patches fit inside `[0,2]^3`. For the upper body diagonal, the
negative-x neighbor transport places its second cube inside the box;
its endpoint and local vertex relabelling are inherited from the existing
body transport. The constructor maps cell vertex sets back to the 48-cell
grid and requires each incident edge to occur exactly once.

The raw face-diagonal trace obeys the existing mode-by-mode checkerboard
source relation because it comes from a continuous field. Before composing
any edge basis, the constructor reconstructs its complete trace from that
basis's free coordinates. Axial and body-diagonal sources are full;
face-diagonal sources retain their compatibility constraints.

Each edge correction has zero divergence at all vertices and on every
other edge, zero cell means and zero outer velocity trace. Their subtraction
therefore preserves the 24 vertex values while removing all edge-interior
coefficients. Reading every edge target from the original raw field makes
the composition independent of correction order.

The code then computes the 48 cell means of this combined field directly
from all degree-\(k-1\) divergence Bernstein coefficients. The means sum to
zero because the field is continuous and has zero outer trace; all reference
tetrahedra have the same volume. It applies
[the existing rectangular-grid mean repair](P4_GRID_MEAN_REPAIR.md) to each
of the 18 columns. That repair changes no mesh-edge divergence coefficient,
including the vertex coordinates.

For P5 the quartic correction is degree-elevated by

\[
b^5_\alpha=\sum_{i:\alpha_i>0}\frac{\alpha_i}{5}b^4_{\alpha-e_i}.
\]

The implementation reuses `axial_edge_lift.elevate_quartic` with all
eight-cube interior nodes and all 18 columns. It never reinterprets
`nodes_times_four` as quintic coordinates.

The face constructor now accepts `construct(degree, mean_repair=operator)`,
so this composition consumes the retained `p4_mean_repair_basis.json`.
Its original no-argument mean-construction behavior remains available.
Saved JSON cell coordinates are normalized before the geometry comparison.

## Exact resulting operators and a fixed-patch norm bound

The constructed reference operators have:

| Degree | Scalar coefficient rows × source columns | Nonzero entries | Target vertex rows | Protected edge rows | Zero cell means |
|---|---:|---:|---:|---:|---:|
| 4 | 1,029 × 18 | 1,319 | 24 | 744 | 48 |
| 5 | 2,187 × 18 | 4,977 | 24 | 1,032 | 48 |

There are \(48(4+6(k-2))\) total vertex/edge rows: 768 for P4 and 1,056
for P5. All outer velocity coefficients are omitted. The final exact
physical reconstruction uses the existing
`face_diagonal_transport.check_physical_operator` on every basis column,
every target/protected edge coordinate and every cell mean. The returned
basis, cell geometry and node coordinates describe the actual field.

For a concrete conservative bound, let \(A_k\) be the largest squared
Euclidean norm of any scalar coefficient row of the 18-column reference
matrix. The selected input coordinates are a subset of the complete tuple,
so each scalar coefficient is bounded in square by
\(A_k\|q\|_{\ell^2(24)}^2\).

On a unit Kuhn tetrahedron,
\(\sum_i|\nabla\lambda_i|^2=6\). The Bernstein derivative formula,
partition of unity and the four-term Cauchy inequality give, after summing
the three vector components and integrating over the volume-eight patch,

\[
|v|_{H^1([0,2]^3)}^2
 \le 8\cdot3\cdot k^2\cdot4\cdot6\,A_k\|q\|_{\ell^2(24)}^2
 =576k^2 A_k\|q\|_{\ell^2(24)}^2.
\]

The resulting constants are:

| Degree | \(A_k\) | Reference squared-seminorm bound \(C_k=576k^2A_k\) |
|---|---:|---:|
| 4 | \(235/72\) | \(30080\) |
| 5 | \(1216/1225\) | \(700416/49\) |

For physical center \(a\) and positive scale \(h\), use
\(x=a+h(\xi-c)\) and \(v_h(x)=h\,v(\xi)\). Divergence target values remain
unchanged, while

\[
|v_h|_{H^1(a+[-h,h]^3)}^2
 \le h^3C_k\|q\|_{\ell^2(24)}^2.
\]

Coefficient rows scale by \(h\), and the code applies this factor once.
The reference inverse formulas therefore use \(r_i=q_i/k\); multiplying
them by \(h\) again inside the already-scaled transport would be incorrect.

These are bounds in the complete compatible vertex-trace norm on a fixed
patch. They do not assert the missing global pressure-norm estimate or a
completed mesh-uniform inf-sup proof.

## Direct use of the new implementation

The two commands above were run on the constructed operators with nontrivial
rational translations and scales. P4 returned reference bound `30080` and
physical bound `101520`; P5 returned reference bound `700416/49` and physical
bound `622592/147`. Both reported exact zero target/protection and mean
residuals. Both repaired 18 mean columns using 64 retained two-cube
applications. P5 used exact degree elevation.

A complete tuple with cell 8 changed from `11` to `12` exited 1 with
`incompatible vertex source trace at dependent cell 8: residual 1` and
created no output file. These were direct calls to the new CLI; no old
standalone certificate suite, new test file or old mean solve was used.

## Existing components retained

- [Kuhn geometry](kuhn.py): original positively oriented six-cell convention.
- [Protected axial-edge lift](AXIAL_EDGE_LIFT.md).
- [Compatible face-diagonal lift](FACE_DIAGONAL_LIFT.md) and
  [coordinate transport](FACE_DIAGONAL_TRANSPORT.md).
- [P4 body-diagonal lift](P4_BODY_DIAGONAL_LIFT.md),
  [P5 companion](P5_BODY_DIAGONAL_LIFT.md), and
  [six-neighbor transport](BODY_DIAGONAL_TRANSPORT.md).
- [Two-cube quartic mean repair](P4_MEAN_REPAIR.md) and
  [grid composition](P4_GRID_MEAN_REPAIR.md).

The new work composes these source-backed local operators and preserves
their separate derivations and attribution.
