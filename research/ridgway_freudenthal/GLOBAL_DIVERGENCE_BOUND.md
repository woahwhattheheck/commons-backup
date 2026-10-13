# Mesh-uniform global divergence bound

Issue: https://github.com/woahwhattheheck/commons/issues/14999

This guide derives a global right-inverse estimate by composing the accepted
minimum-energy cell-mean lift, protected vertex lifts, protected edge lifts,
and element-bubble inverse. The exact placements and coefficient-index maps
come from [the global patch planner](GLOBAL_PATCH_PLAN.md).

The pressure space in the proposition is the **actual divergence image** of
the continuous Dirichlet velocity space. Membership in that image supplies
the compatibility required by each local source map. No independently
specified list of pressure constraints is substituted for that space.

The component constructions, matrices, original source attribution, and
completed executions remain those in their linked guides. The new result
here is their global composition and its bound, including pressure-norm
extraction, complete-star coverage, and bounded overlap.

## 1. Spaces, norms, and statement

Let \(\Omega=(0,1)^3\). Divide it into \(n^3\) cubes of side
\(h=1/n\), and split each cube into the six positively ordered tetrahedra
from [kuhn.py](kuhn.py). Write this conforming mesh as \(\mathcal T_h\).
For \(k\in\{4,5\}\), set \(m=k-1\) and

\[
V_h^k=\{v\in H_0^1(\Omega)^3:
              v|_T\in[\mathcal P_k(T)]^3
              \text{ for every }T\in\mathcal T_h\},
\qquad
Q_h^{k-1}=\operatorname{div}V_h^k.
\]

Here \(Q_h^{k-1}\) is a subspace of the discontinuous piecewise
\(\mathcal P_m\) space and of \(L_0^2(\Omega)\). The latter inclusion
follows from the zero velocity trace and the divergence theorem. Use

\[
|v|_1=\|\nabla v\|_{L^2(\Omega)},\qquad
\|q\|_0=\|q\|_{L^2(\Omega)},
\]

with the Frobenius norm for the velocity gradient.

**Proposition.** For every \(n\ge2\) and \(k\in\{4,5\}\), the construction
below defines a linear map

\[
\mathcal L_h^k:Q_h^{k-1}\longrightarrow V_h^k,
\qquad
\operatorname{div}\mathcal L_h^k q=q,
\qquad
|\mathcal L_h^kq|_1\le C_k\|q\|_0,
\]

where \(C_k\) is independent of \(n\). One admissible constant is

\[
\boxed{
C_k=C_0+K_v A_0+K_e A_v A_0+K_b A_e A_v A_0,
}
\tag{1}
\]

where

\[
A_0=1+\sqrt3\,C_0,\qquad
A_v=1+\sqrt3\,K_v,\qquad
A_e=1+\sqrt3\,K_e,
\tag{2}
\]

\[
K_v=\sqrt{64\,C_{v,k}\gamma_k},\qquad
K_e=\sqrt{448\,C_{e,k}\gamma_k},\qquad
K_b=\sqrt{C_{b,k}}.
\tag{3}
\]

The accepted mean constant \(C_0\), the exact finite Gram constant
\(\gamma_k\), and the component constants are defined below. These are
conservative bounds; no optimal constant or computed numerical value of
\(C_0\) is asserted.

Consequently the actual image pair has the mesh-uniform estimate

\[
\inf_{\substack{q\in Q_h^{k-1}\\q\ne0}}
\sup_{\substack{v\in V_h^k\\v\ne0}}
\frac{\int_\Omega q\,\operatorname{div}v}
     {|v|_1\|q\|_0}
\ \ge\ C_k^{-1}.
\tag{4}
\]

This proposition concerns the spaces just defined. Identification with a
separately proposed pressure space, disposition of an external manuscript,
and sponsor or prize decisions are separate questions.

## 2. Accepted component maps and their constants

### Mean component

Let \(\Pi_0\) be the cellwise \(L^2\) projection onto constants. The
[minimum-energy mean lift](MEAN_ENERGY_LIFT.md#uniform-bound-for-the-mean-lift)
provides a linear map \(M_h\) for all mean-zero piecewise constants \(q_0\)
such that

\[
M_hq_0\in V_h^k,\qquad
\Pi_0\operatorname{div}M_hq_0=q_0,\qquad
|M_hq_0|_1\le C_0\|q_0\|_0.
\tag{5}
\]

The same cubic field is represented in degree four or five by exact
degree elevation, so one may use the same \(C_0\) for both degrees.

Equation (5) prescribes the divergence **means**. It does not say
\(\operatorname{div}M_hq_0=q_0\) as a polynomial. Its nonconstant
divergence coefficients are included when forming the next residual.

The cited guide proves that \(C_0<\infty\) is independent of \(n\):
a continuous divergence right inverse, a boundary-preserving
Scott–Zhang interpolant, and normal cubic face bubbles give a bounded
feasible field, and the discrete minimum-energy field has no larger
seminorm. The continuous right inverse and interpolation references,
with their precise hypotheses, are recorded in that guide. No uniform
estimate for the older whole-grid tree-routing field is used here.

### Vertex and edge components

For a mesh vertex \(z\), write \(E_z r\) for the complete tuple of
one-sided values \(r|_T(z)\) over its incident cells, in the local
operator's recorded order. The accepted vertex map \(L_z\) has zero
velocity trace on its full patch boundary. Its divergence:

- reproduces \(E_z r\) at \(z\);
- vanishes at every other patch vertex and at every edge-interior
  Bernstein coordinate;
- has zero mean on every patch cell.

For a mesh edge \(e\), write \(E_e r\) for its complete tuple of
edge-interior Bernstein coefficients, with one block for each incident
cell and one entry for each of the \(k-2\) interior modes. Its endpoints
are excluded. The accepted edge map \(L_e\) has zero velocity trace on its
full patch boundary. Its divergence:

- reproduces \(E_e r\) on the selected edge;
- vanishes at all vertices and on every other patch edge;
- has zero mean on every patch cell.

These maps act on their actual compatible source images. Their output
fields are linear in the selected free coordinates, and those coordinates
are entries of the complete input tuple. The constants below bound the
**final mean-corrected field in complete-tuple Euclidean norm**, including
all internal edge and mean corrections.

| Vertex class | Reference squared-seminorm bound, P4 | P5 | Component derivation |
| --- | ---: | ---: | --- |
| Interior | \(30080\) | \(700416/49\) | [Interior vertex](INTERIOR_VERTEX_LIFT.md#exact-resulting-operators-and-a-fixed-patch-norm-bound) |
| Face | \(7416\) | \(120600/49\) | [Boundary vertex](BOUNDARY_VERTEX_LIFT.md#exact-operators-and-fixed-patch-bounds) |
| Same-side crease | \(1152\) | \(16416/49\) | [Boundary vertex](BOUNDARY_VERTEX_LIFT.md#exact-operators-and-fixed-patch-bounds) |
| Same-side corner | \(720\) | \(15696/49\) | [Boundary vertex](BOUNDARY_VERTEX_LIFT.md#exact-operators-and-fixed-patch-bounds) |
| Mixed-side crease or corner | \(0\) | \(0\) | [Zero source classes](BOUNDARY_VERTEX_LIFT.md#mixed-side-classes) |

| Edge class | Reference squared-seminorm bound, P4 | P5 | Component derivation |
| --- | ---: | ---: | --- |
| Body diagonal | \(1728\) | \(39744/49\) | [Body transport](BODY_DIAGONAL_TRANSPORT.md#seminorm-bound-and-scope) |
| Interior face diagonal | \(576\) | \(1008\) | [Face diagonal](FACE_DIAGONAL_LIFT.md#bound-and-execution) |
| Boundary face diagonal | \(72\) | \(72\) | [Boundary face diagonal](BOUNDARY_FACE_DIAGONAL_LIFT.md#a-bound-in-free-and-complete-trace-coordinate-norms) |
| Interior axial | \(5248\) | \(98136/49\) | [Axial edge](AXIAL_EDGE_LIFT.md#a-finite-degree-bernstein-coefficient-bound) |
| Axial in one boundary face | \(1500\) | \(25632/49\) | [Boundary axial edge](BOUNDARY_AXIAL_EDGE_LIFT.md#explicit-finite-patch-seminorm-bound) |
| Same-side boundary crease | \(1440\) | \(23328/49\) | [Boundary crease](BOUNDARY_CREASE_EDGE_LIFT.md#4-a-finite-degree-coefficient-bound) |
| Mixed-side boundary crease | \(0\) | \(0\) | [Zero crease image](BOUNDARY_CREASE_EDGE_LIFT.md#22-mixed-side-class-every-target-coefficient-is-zero) |

Thus the classwise maxima are

\[
C_{v,4}=30080,\quad C_{v,5}=700416/49,\qquad
C_{e,4}=5248,\quad C_{e,5}=98136/49.
\tag{6}
\]

Each physical placement uses \(F(\xi)=a+hO\xi\), or the equivalent
vertex-centered formula, where \(O\) is a coordinate permutation
possibly followed by uniform sign reversal. Velocities transform by

\[
v(F(\xi))=hO\widehat v(\xi).
\]

The chain rule and orthogonality give

\[
\nabla v(F(\xi))=O\nabla\widehat v(\xi)O^\top,\qquad
\operatorname{div}v(F(\xi))=\operatorname{div}\widehat v(\xi),
\qquad
|v|_1^2=h^3|\widehat v|_1^2.
\tag{7}
\]

There is no additional sign in the pressure trace. The simultaneous
positive-cell vertex relabelling and Bernstein-index permutation preserve
the represented polynomial and Euclidean tuple norm. Therefore

\[
|L_z t|_1^2\le h^3 C_{v,k}\|t\|_{\ell^2}^2,\qquad
|L_e y|_1^2\le h^3 C_{e,k}\|y\|_{\ell^2}^2.
\tag{8}
\]

### Element component

On any physical cell \(T\), the
[element-bubble inverse](CELL_BUBBLE_LIFT.md#explicit-pressure-norm-bound)
maps every \(r_T\in\mathcal P_m(T)\) with zero vertex/edge coefficients
and zero cell mean to a vector polynomial \(B_T r_T\) satisfying

\[
B_T r_T|_{\partial T}=0,\qquad
\operatorname{div}B_T r_T=r_T,\qquad
|B_T r_T|_{1,T}^2\le C_{b,k}\|r_T\|_{0,T}^2,
\tag{9}
\]

with

\[
C_{b,4}=113400,\qquad C_{b,5}=32246100/17.
\tag{10}
\]

These constants already use the pressure \(L^2\) norm. They do not need
another multiplication by the full coefficient-extraction constant.

## 3. Pressure coefficients and a finite exact extraction constant

On an ordered tetrahedron use normalized Bernstein polynomials

\[
B_\alpha^m(\lambda)=\frac{m!}{\alpha_0!\alpha_1!\alpha_2!\alpha_3!}
                    \prod_{i=0}^3\lambda_i^{\alpha_i},
\qquad |\alpha|=m.
\]

For a pressure \(r|_T=\sum_{|\alpha|=m}c_{T,\alpha}B_\alpha^m\),
the \(c_{T,\alpha}\) are Bernstein coefficients. Interior coefficients
are not point samples.

Let \(\widehat T\) be one unit Kuhn tetrahedron, of volume \(1/6\).
The full Bernstein Gram matrix, in any fixed complete index order, is

\[
(G_k)_{\alpha\beta}
 =\int_{\widehat T} B_\alpha^m B_\beta^m
 =\frac{(m!)^2}{(2m+3)!}
   \prod_{i=0}^3
   \frac{(\alpha_i+\beta_i)!}{\alpha_i!\beta_i!}.
\tag{11}
\]

To obtain this formula, multiply the normalized Bernstein terms and use
\(\int_{\widehat T}\lambda^\eta=\prod_i\eta_i!/(|\eta|+3)!\).
All six unit Kuhn cells have the same barycentric integration formula.
Reordering the local vertices only permutes the complete basis.

Define the exact rational number

\[
\boxed{\displaystyle
\gamma_k=\max_\alpha\sum_\beta |(G_k^{-1})_{\alpha\beta}|.
}
\tag{12}
\]

This is a computable definition: \(G_4\) is \(20\times20\) and \(G_5\)
is \(35\times35\), with rational entries supplied by (11). It refers to
the **full** pressure basis, not the smaller element-bubble source Gram
matrix used to obtain (10).

The Bernstein basis is linearly independent, so \(G_k\) is symmetric
positive definite. The largest eigenvalue of \(G_k^{-1}\) is at most
its maximum absolute row sum. Hence, for every coefficient vector \(c\),

\[
\|c\|_{\ell^2}^2\le\gamma_k\,c^\top G_kc.
\]

A physical cell has volume \(h^3/6\), so its Gram matrix is \(h^3G_k\).
It follows that every discontinuous piecewise-\(\mathcal P_m\) field
satisfies

\[
\sum_{T\in\mathcal T_h}\sum_{|\alpha|=m}|c_{T,\alpha}|^2
 \le\gamma_k h^{-3}\|r\|_0^2.
\tag{13}
\]

This inequality needs no divergence-image assumption.

### Each target coordinate is extracted once

A vertex trace entry is exactly
\(c_{T,m e_i}=r|_T(v_i)\). The pair \((T,m e_i)\) belongs to one
global vertex. Consequently

\[
\sum_z\|E_zr\|_{\ell^2}^2
 =\sum_T\sum_{i=0}^3|c_{T,m e_i}|^2
 \le\gamma_k h^{-3}\|r\|_0^2.
\tag{14}
\]

An interior edge coefficient has exactly two positive entries in its
multi-index. Their two cell vertices determine a unique global edge.
Conversely, every global edge's incident-cell list and all its interior
modes produce exactly those cell/coefficient pairs. Thus

\[
\sum_e\|E_er\|_{\ell^2}^2
 =\sum_T\ \sum_{\substack{|\alpha|=m\\
                         |\operatorname{supp}\alpha|=2}}
             |c_{T,\alpha}|^2
 \le\gamma_k h^{-3}\|r\|_0^2.
\tag{15}
\]

Different one-sided values on neighboring cells remain different
coordinates. There is no continuity assumption on the pressure and no
identification of these entries. The equality counts each **cell plus
multi-index** once; it does not multiply by the number of cells in a star.

The planner's `local_cell_to_global_cell` and
`local_vertex_to_global_vertex_position` maps give this exact
correspondence. If a transported local index is \(\beta\) and its local
vertex-position permutation is \(p\), the global index is defined by
\(\beta^{\mathrm{global}}_{p(i)}=\beta_i\).
A reversed inherited edge endpoint order is already included in that
mapping. No further mode reversal or orientation sign is applied.

## 4. Every target has a contained complete-star patch

The [planner's placement formulas](GLOBAL_PATCH_PLAN.md) use the same
Kuhn cube and positive local cell order as the component operators.
The following facts explain why they cover every mesh target for all
\(n\ge2\), not only the displayed finite products.

A Kuhn cell is a monotone coordinate-step chain inside one grid cube.
Therefore any mesh edge has canonical componentwise lower endpoint
\(\ell\) and upper endpoint \(\ell+\chi_S\), for exactly one nonempty
subset \(S\subseteq\{x,y,z\}\). There are seven directions.
For a coordinate changed by the edge, its containing cube must have
lower coordinate \(\ell_i\). For a fixed coordinate \(r\), an incident
cube has lower coordinate \(r-1\) or \(r\), when that cube lies in the
mesh. This identifies every possible incident cube.

| Target | Incident-cube coverage and selected patch |
| --- | --- |
| Body diagonal | The star lies in one cube. Add its positive-x neighbor when available, otherwise its negative-x neighbor. The second choice is available because \(n\ge2\). |
| Interior face diagonal | The fixed normal coordinate is \(1\le r\le n-1\). The patch covers both adjacent normal cubes, with interval \([r-1,r+1]\), and the unit intervals in the changing coordinates. |
| Boundary face diagonal | The star lies in the boundary cube. The patch uses two inward normal cubes and the two unit changing-coordinate intervals. |
| Interior axial edge | Its two fixed coordinates are interior. Use their intervals \([r-1,r+1]\), and the unit tangent interval. This contains all four incident cubes. |
| Axial edge in one boundary face | Use one inward normal cube, two cubes around the remaining interior fixed coordinate, and the unit tangent interval. |
| Boundary crease axial edge | One cube contains the star. The chosen patch is two cubes deep in the first normal direction and one cube in the second normal and tangent directions. Both same-side and mixed-side versions point inward. |
| Interior vertex | The box \(z+[-1,1]^3\) contains all eight possible incident cubes. |
| Face vertex | One inward cube in the normal direction and two around each interior tangential coordinate contain all incident cubes. |
| Crease vertex | One inward cube in each boundary-normal direction and two around the interior tangent coordinate contain all incident cubes. |
| Corner vertex | The star lies in one cube. The reference extends to a second inward cube in one coordinate direction for the accepted correction. |

All coordinates in this table are lattice coordinates; multiply intervals
by \(h\) and translate for physical coordinates. Interior coordinates
lie in \(\{1,\ldots,n-1\}\); an inward two-cube interval at a boundary
is either \([0,2]\) or \([n-2,n]\). Thus every listed patch lies in
\([0,n]^3\). No two-cube construction is invoked at \(n=1\).

Coordinate permutations and uniform coordinate inversion preserve Kuhn
cell vertex sets: they permute or reverse monotone chains. The local
vertex swap for negative orientation changes only their ordering.
The listed target and its complete incident cubes are transformed copies
of the corresponding reference target. Within each cube, the unchanged
six-cell subdivision therefore gives exactly the complete incident
tetrahedron star.

For vertices, the five boundary reference configurations give six face,
six same-side crease, six mixed-side crease, two same-side corner, and
six mixed-side corner orientations: all 26 possibilities. For axial
edges, zero, one, or two boundary fixed coordinates give the interior,
one-face, or crease class. The two crease side patterns give the same
or mixed class. Diagonal edges are classified by the same fixed-coordinate
rule. These alternatives are exhaustive and disjoint.

Every patch is a union of global cells; its side lengths are at most
\(2h\); it contains its target vertex or both target-edge endpoints.
The chosen maps identify every local cell with exactly one global cell
and every local vertex with its position in that global cell.

### Census

The exact counts provide an additional description of this enumeration.
They are obtained by choosing varying coordinates and deciding whether
each fixed coordinate is interior or on a specified side.

| Target class | Number |
| --- | ---: |
| Interior vertex | \((n-1)^3\) |
| Face vertex | \(6(n-1)^2\) |
| Same-side crease vertex | \(6(n-1)\) |
| Mixed-side crease vertex | \(6(n-1)\) |
| Same-side corner vertex | \(2\) |
| Mixed-side corner vertex | \(6\) |
| Body-diagonal edge | \(n^3\) |
| Interior face-diagonal edge | \(3n^2(n-1)\) |
| Boundary face-diagonal edge | \(6n^2\) |
| Interior axial edge | \(3n(n-1)^2\) |
| Axial edge in one boundary face | \(12n(n-1)\) |
| Same-side crease axial edge | \(6n\) |
| Mixed-side crease axial edge | \(6n\) |

The vertex total is \((n+1)^3\); the edge total is
\(7n^3+9n^2+3n\). There is one patch record per target, including zero-image
classes, for a total of \((2n+1)^3\) records. For \(n=2\) these give
27 vertices, 98 edges, and 125 patches; for \(n=3\) they give
64 vertices, 279 edges, and 343 patches, agreeing with the completed
planner products.

## 5. Uniform overlap: 64 vertex patches and 448 edge patches

Use integer grid vertices as anchors. A vertex patch is anchored at its
target vertex. An edge patch is anchored at its canonical componentwise
lower endpoint, even when the transported reference uses the opposite
endpoint first.

Fix a tetrahedron \(T\) in the lattice cube
\(i+[0,1]^3\), \(i\in\mathbb Z^3\). If a selected patch contains \(T\),
its box contains this cube: every selected box is a union of whole grid
cubes. In a coordinate direction, the box has integer endpoints and
length either one or two. Because it also contains its integer anchor
\(a\), that anchor coordinate must be one of

\[
a_j\in\{i_j-1,\ i_j,\ i_j+1,\ i_j+2\}.
\tag{16}
\]

There are at most \(4^3=64\) possible anchors. Exactly one vertex patch
is selected per vertex, so no cell interior is covered by more than
64 vertex patches.

At one anchor there are at most seven mesh edges with that canonical
lower endpoint, one for each nonzero \(0/1\) displacement. Exactly one
patch is selected for each edge. Hence no cell interior is covered by
more than

\[
7\cdot4^3=448
\tag{17}
\]

edge patches. Boundary truncation only decreases these numbers. Statements
on cell interiors suffice for the integral; cell interfaces have measure
zero.

For zero-extended patch fields, pointwise Cauchy–Schwarz consequently gives

\[
\left|\sum_z v_z\right|_1^2\le64\sum_z|v_z|_1^2,
\qquad
\left|\sum_e v_e\right|_1^2\le448\sum_e|v_e|_1^2.
\tag{18}
\]

Each field in these sums is the complete accepted local lift, including
its internal corrections. Those corrections are already contained in
the selected patch and in the bounds (8). They do not create additional
global anchors or an additional overlap factor.

## 6. Compatibility comes from the actual residual image

For any \(r\in Q_h^{k-1}\), there exists \(w\in V_h^k\) with
\(\operatorname{div}w=r\). Restrict \(w\) to a target's complete incident
star. It is continuous there and satisfies the physical Dirichlet
conditions. Pulling it back by the chosen invertible transport places
its target tuple in the component's actual reference source image.

The witness \(w\) is used only for this implication. The construction
does not need its coefficients; it reads the pressure coefficients and
applies the accepted explicit local maps.

For vertex targets, the
[interior source derivation](INTERIOR_VERTEX_LIFT.md#why-the-42-first-derivative-variables-give-the-full-source-image)
uses all first-derivative variables shared on the 14 incident edges.
The [boundary source derivation](BOUNDARY_VERTEX_LIFT.md#the-full-dirichlet-first-derivative-source)
imposes the actual zero-trace conditions on those variables. The source
dimensions are 18 for an interior vertex and 8, 5, 0, 3, 0 for face,
same-side crease, mixed-side crease, same-side corner, and mixed-side
corner vertices. Thus every required vertex tuple is admitted; the mixed
classes necessarily receive the zero tuple.

For edge targets, the complete source images in the linked component
derivations are:

| Class | Condition in the inherited per-mode cell order |
| --- | --- |
| Body diagonal | Full image |
| Interior face diagonal | \(y_1-y_2-y_3+y_4=0\) |
| Boundary face diagonal | The two incident values are equal |
| Interior axial | Full image |
| Axial in one boundary face | Full image |
| Same-side boundary crease | Full image |
| Mixed-side boundary crease | Zero image |

The face relations are identities of the full continuous source-star
map; the boundary relations use the actual Dirichlet source map.
They are not inferred from a failed protected patch solve.
After the vertex stage the residual endpoints are zero, which is exactly
the endpoint condition of the protected edge outputs. Any additional
physical boundary condition on a restricted source can only reduce its
possible tuples, so it cannot invalidate membership in the stated source
image.

Every constructed patch velocity has zero trace on its entire patch
boundary. Its extension by zero is therefore a continuous member of
\(V_h^k\), including along artificial patch interfaces and physical
domain faces. Consequently

\[
r\in Q_h^{k-1},\quad v\in V_h^k
\quad\Longrightarrow\quad
r-\operatorname{div}v\in Q_h^{k-1}.
\tag{19}
\]

This invariance is used after every stage. A collection of necessary
local pressure relations is never assumed to characterize \(Q_h^{k-1}\).

## 7. Constructing the right inverse

Take \(q\in Q_h^{k-1}\).

### Stage 0: cell means

Set

\[
q_0=\Pi_0q,\qquad
u_0=M_hq_0,\qquad
r_0=q-\operatorname{div}u_0.
\tag{20}
\]

The total integral of \(q_0\) is zero, so the mean input is admissible.
Equation (5) gives \(\Pi_0r_0=0\). Since \(u_0\in V_h^k\),
equation (19) gives \(r_0\in Q_h^{k-1}\).

### Stage V: all vertices

Using the single residual \(r_0\), construct and zero-extend

\[
u_v=\sum_z L_z(E_zr_0),\qquad
r_v=r_0-\operatorname{div}u_v.
\tag{21}
\]

Section 6 makes every input compatible. Complete-star coverage ensures
that every one-sided value at the target is corrected. Each local map
has zero divergence at all other vertices. Thus \(r_v\) vanishes at
every cell vertex. Its cell means remain zero, and (19) gives
\(r_v\in Q_h^{k-1}\).

The local maps also preserve every edge-interior coefficient. Their
targets can all be read from \(r_0\) before forming the sum; no sequential
update or ordering assumption is needed.

### Stage E: all edge interiors

Using the single residual \(r_v\), set

\[
u_e=\sum_e L_e(E_er_v),\qquad
r_e=r_v-\operatorname{div}u_e.
\tag{22}
\]

The residual is still in the actual divergence image, so its complete
edge tuples obey the source conditions in Section 6. Its endpoints
already vanish. Every local map preserves all vertices, all other edges,
and every cell mean. Hence \(r_e\) has zero coefficients at all vertices
and all edge interiors, and has zero mean on every cell. It also remains
in \(Q_h^{k-1}\).

The full tuple is read once per edge. In a zero-image class the tuple
is zero and the selected correction is zero; the target is still included
in the complete mesh census.

### Stage B: every cell interior residual

A pressure polynomial has zero trace on all tetrahedral edges exactly
when all its Bernstein coefficients supported on at most two vertices
vanish. For \(m=3\), four face-interior coefficients remain, with one
zero-mean relation. For \(m=4\), twelve face-interior coefficients and
one cell-interior coefficient remain, again with one zero-mean relation.
Their dimensions are therefore three and twelve.

These are precisely the full sources of (9), as established by the
[explicit quartic and quintic element inverses](CELL_BUBBLE_LIFT.md).
Set

\[
u_b=\sum_{T\in\mathcal T_h} B_T(r_e|_T).
\tag{23}
\]

Every summand vanishes on its entire cell boundary, so this is a member
of \(V_h^k\) and its divergence equals \(r_e\) cell by cell.

Finally define

\[
\mathcal L_h^kq=u_0+u_v+u_e+u_b.
\tag{24}
\]

Equations (20)–(23) telescope to
\(\operatorname{div}\mathcal L_h^kq=q\).
All choices of patches and index orders depend only on the mesh.
Every component is linear on its admitted source. Therefore (24) is
a linear map on \(Q_h^{k-1}\).

## 8. Global norm estimate

For any \(v\in H_0^1(\Omega)^3\), Cauchy–Schwarz on the three diagonal
gradient entries gives

\[
\|\operatorname{div}v\|_0\le\sqrt3\,|v|_1.
\tag{25}
\]

Since \(\Pi_0\) is an \(L^2\) orthogonal projection, (5) and (20) imply

\[
|u_0|_1\le C_0\|q\|_0,\qquad
\|r_0\|_0\le(1+\sqrt3 C_0)\|q\|_0=A_0\|q\|_0.
\tag{26}
\]

For the vertex sum, combine the overlap estimate (18), the local
physical bound (8), and extraction (14):

\[
\begin{aligned}
|u_v|_1^2
&\le64\sum_z|L_z(E_zr_0)|_1^2\\
&\le64\,h^3C_{v,k}\sum_z\|E_zr_0\|_{\ell^2}^2\\
&\le64\,C_{v,k}\gamma_k\|r_0\|_0^2.
\end{aligned}
\tag{27}
\]

The physical \(h^3\) and coefficient-extraction \(h^{-3}\) factors
cancel. Hence

\[
|u_v|_1\le K_v\|r_0\|_0,\qquad
\|r_v\|_0\le A_v\|r_0\|_0.
\tag{28}
\]

Apply the same argument to the edge sum, now using (15):

\[
\begin{aligned}
|u_e|_1^2
&\le448\sum_e|L_e(E_er_v)|_1^2\\
&\le448\,h^3C_{e,k}\sum_e\|E_er_v\|_{\ell^2}^2\\
&\le448\,C_{e,k}\gamma_k\|r_v\|_0^2,
\end{aligned}
\tag{29}
\]

and therefore

\[
|u_e|_1\le K_e\|r_v\|_0,\qquad
\|r_e\|_0\le A_e\|r_v\|_0.
\tag{30}
\]

Distinct cell interiors are disjoint. Equation (9) consequently gives
the element sum directly, with overlap one:

\[
|u_b|_1^2
=\sum_T|B_T(r_e|_T)|_{1,T}^2
\le C_{b,k}\sum_T\|r_e\|_{0,T}^2
=C_{b,k}\|r_e\|_0^2.
\tag{31}
\]

Using (26), (28), and (30), the four terms in (24) satisfy

\[
\begin{array}{ll}
|u_0|_1\le C_0\|q\|_0,&
|u_v|_1\le K_v A_0\|q\|_0,\\[2mm]
|u_e|_1\le K_e A_v A_0\|q\|_0,&
|u_b|_1\le K_b A_e A_v A_0\|q\|_0.
\end{array}
\tag{32}
\]

The triangle inequality proves (1). Every constant depends on the
fixed degree, the accepted fixed-patch maps, or the fixed cube, and
none depends on \(n\).

For \(q\ne0\), take \(v=\mathcal L_h^kq\) in the supremum. Its numerator
is \(\|q\|_0^2\), and its seminorm is at most \(C_k\|q\|_0\),
which proves (4).

## 9. The single-cube case and physical scaling

The exact two-cube patch choices above require \(n\ge2\). A separate
finite-dimensional argument includes \(n=1\) in an existence statement.

On the six-cell mesh of one cube, use the same spaces \(V_1^k\) and
\(Q_1^{k-1}=\operatorname{div}V_1^k\). The seminorm \(|\cdot|_1\)
is a norm on \(V_1^k\), because its functions have zero boundary trace.
For each \(q\in Q_1^{k-1}\), choose the velocity of minimum squared
seminorm among all \(v\) with \(\operatorname{div}v=q\).

Equivalently, restrict divergence to the energy-orthogonal complement
of its kernel. That restriction is a linear bijection onto the actual
image. Its inverse is bounded because both spaces are finite dimensional;
denote its finite operator norm by \(C_{1,k}\). If the image were zero,
the zero map would suffice. Thus the maximum
\(\max\{C_k,C_{1,k}\}\) gives an \(n\)-independent existence bound for
all positive integers \(n\).

This finite-case inverse is distinct from the planner and from the
mean-only lift on \(n=1\); no two-cube embedding or full \(n=1\)
assembler execution is asserted.

For a translated cube of fixed side \(L>0\), use \(x=a+L\xi\) and
\(v(x)=L\widehat v(\xi)\). Both \(|v|_1^2\) and \(\|q\|_0^2\)
gain the same factor \(L^3\), so the seminorm-to-pressure constants
above are unchanged. The planner and exact constructors represent
rational choices without rounding; their finite linear identities
also hold for real coefficients.

If the velocity denominator is the full \(H^1\) norm, let \(C_P\)
be the Poincaré constant of the fixed cube. Then

\[
\|v\|_{H^1}\le\sqrt{1+C_P^2}\,|v|_1,
\]

so replace \(C_k\) by \(\sqrt{1+C_P^2}\,C_k\) in that version of
the right-inverse and inf-sup bounds.

## 10. Assembly correspondence and scope

The complete global construction uses the maps in this order:

1. Feed the cell averages of the actual input pressure to the
   minimum-energy mean lift, then subtract its **full polynomial**
   divergence.
2. Extract all one-sided vertex values using the planner's complete
   incident-cell maps; apply and add the corresponding protected fields.
3. Extract every incident-cell edge-interior coefficient from the vertex
   residual using the recorded cell and multi-index permutations.
4. Apply the explicit element inverse to each remaining cell polynomial.

Fields are added through shared global velocity coefficient nodes;
divergence coordinates remain cell-local. Transported local vertex order,
the canonical global positive-cell order, and inherited endpoint order
must be connected by the planner's recorded permutations. These
permutations are norm-preserving and are part of the exact construction.

The proof supplies a mesh-uniform estimate for this complete composition.
It does not require rerunning a retained local solve or assuming that
arbitrary local constraint checks certify a pressure's membership in the
actual image. The component source descriptions and explicit inverses
supply precisely the compatibility and protection statements used here.

The accepted mean, interior and boundary vertex, seven edge-class,
element-bubble, and patch-planner contributions retain their original
credit in the linked source guides. This mathematical proposition
makes no claim about an external manuscript's acceptance, sponsor
approval, prize availability, eligibility, submission, or payment.
