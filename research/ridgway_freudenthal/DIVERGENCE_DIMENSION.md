# Exact divergence-image and kernel dimensions

Issue: https://github.com/woahwhattheheck/commons/issues/14999

The completed [global constructor](GLOBAL_DIVERGENCE_LIFT.md) gives an
exact coordinate description of its pressure image. This note proves that
the mean, vertex, edge and cell-residual coordinates form a linear
isomorphism, then counts them. It also identifies the complementary
divergence-free velocity space and the projector supplied by the existing
right inverse.

The argument uses the accepted protected local maps and their contained
placements. It does not infer rank from a few computed fields or from
necessary local relations alone.

## 1. Spaces and result

Let \(\mathcal T_n\) be the uniform Kuhn triangulation of a cube into
\(n^3\) smaller cubes, each subdivided into six tetrahedra. All cubes use
the same monotone-chain orientation. Take \(n\ge2\) and \(k\in\{4,5\}\).
Set

\[
V_{n,k}=\{v\in C^0(\overline\Omega)^3:
v|_T\in\mathcal P_k(T)^3,\ v|_{\partial\Omega}=0\},
\qquad
Q_{n,k}=\operatorname{div}V_{n,k},
\]

\[
Z_{n,k}=\{v\in V_{n,k}:\operatorname{div}v=0\}.
\]

The pressure degree is \(k-1\); the second subscript above records the
velocity degree. The dimensions are over the real numbers. The same
counts hold over the rationals for the exact rational reference geometry.

**Theorem.** For every \(n\ge2\),

\[
\begin{aligned}
\dim Q_{n,4}&=108n^3-12n^2-24n+5,\\
\dim Q_{n,5}&=195n^3-15n^2-30n+5,
\end{aligned}
\tag{1}
\]

and

\[
\begin{aligned}
\dim Z_{n,4}&=84n^3-132n^2+60n-8,\\
\dim Z_{n,5}&=180n^3-210n^2+75n-8.
\end{aligned}
\tag{2}
\]

The proof below constructs the coordinate isomorphism that justifies
adding the class dimensions. Translation and positive isotropic scaling
do not change these dimensions.

These formulas are asserted only for \(n\ge2\). The existing uniform-bound
guide treats \(n=1\) by a separate finite-dimensional existence argument.
[The separate single-cube calculation](SINGLE_CUBE_DIMENSION.md) now gives
the exact image/kernel pairs \(76/5\) for degree four and \(155/37\) for
degree five. In particular, substituting \(n=1\) into (1) or (2) is
incorrect at degree four; this note does not extend those formulas.

## 2. The component spaces and their protected maps

Write \(D=\operatorname{div}\). All pressure coefficients below multiply
normalized Bernstein basis polynomials. An interior coefficient is not
a value sampled at its coefficient node.

Use four finite-dimensional coordinate spaces.

1. \(M_n\) contains one cell mean \(m_T\) per tetrahedron, with
   \(\sum_T m_T=0\). All tetrahedra have equal volume, so this is the
   global zero-integral condition.
2. \(A_z\) is the complete compatible one-sided vertex-value source space
   at mesh vertex \(z\), including its physical Dirichlet conditions.
3. \(E_{e,k}\) is the complete compatible source of the \(k-2\)
   edge-interior Bernstein coefficients per incident tetrahedron at
   mesh edge \(e\), after the endpoint coefficients vanish.
4. \(B_{T,k}\) consists of degree-\((k-1)\) pressure polynomials on \(T\)
   with all vertex and edge-interior coefficients zero and cell mean zero.

Fix the patch choices and coordinate order from
[GLOBAL_PATCH_PLAN.md](GLOBAL_PATCH_PLAN.md). The accepted construction
provides linear velocity maps with the following identities.

| Map | Prescribed divergence data | Divergence data preserved at zero |
| --- | --- | --- |
| \(R_0:M_n\to V_{n,k}\) | Every cell mean | No vertex or edge preservation is needed |
| \(R_z:A_z\to V_{n,k}\) | Complete tuple at vertex \(z\) | All other vertices, every edge interior, every cell mean |
| \(R_e:E_{e,k}\to V_{n,k}\) | Complete interior tuple at edge \(e\) | Every vertex, every other edge interior, every cell mean |
| \(R_T:B_{T,k}\to V_{n,k}\) | Entire supplied polynomial on \(T\) | Every other cell; its own vertex/edge coefficients and mean are zero |

The mean map is the existing minimum-energy mean lift. Its field is
embedded in degree \(k\), and its **complete** polynomial divergence is
used. The vertex and edge maps are the retained protected operators,
transported to the selected contained patches and extended by zero.
The final map is the explicit element-bubble inverse, extended by zero
outside its tetrahedron.

Each map really takes values in \(V_{n,k}\). The patches are unions of
mesh cells and each local velocity has zero trace on its entire patch
boundary. The bubble velocity vanishes on every face of its cell.
Consequently their zero extensions have continuous shared traces and
satisfy the physical boundary condition.

These map identities, the complete local source images, and the
\(n\ge2\) contained-patch argument are supplied by the
[global construction](GLOBAL_DIVERGENCE_LIFT.md#the-four-stages),
[global bound](GLOBAL_DIVERGENCE_BOUND.md#6-compatibility-comes-from-the-actual-residual-image),
and [element inverse](CELL_BUBBLE_LIFT.md#coefficients-and-full-source-image).
Zero-dimensional boundary source spaces are retained as zero factors.

## 3. Coordinate isomorphism: spanning and independence

Form the direct product

\[
X_{n,k}
=M_n\times\prod_z A_z\times\prod_e E_{e,k}\times\prod_T B_{T,k}.
\tag{3}
\]

For \(x=(m,(a_z),(b_e),(c_T))\), define the velocity synthesis map

\[
R x=R_0m+\sum_zR_za_z+\sum_eR_eb_e+\sum_TR_Tc_T
\tag{4}
\]

and its pressure map

\[
F x=D R x
=D R_0m+\sum_zD R_za_z+\sum_eD R_eb_e+\sum_T\widetilde c_T.
\tag{5}
\]

Here \(\widetilde c_T\) is \(c_T\) on \(T\) and zero on every other
tetrahedron. Equation (4) shows directly that \(F(X_{n,k})\subseteq Q_{n,k}\).

### Spanning the actual image

Take \(q\in Q_{n,k}\). Its cell means belong to \(M_n\), because a
continuous velocity with zero boundary trace has total divergence
integral zero. Let \(m\) be those means and put

\[
r_0=q-D R_0m.
\]

Every cell mean of \(r_0\) is zero, and \(r_0\in Q_{n,k}\). The latter
fact follows because both terms are divergences of velocities in
\(V_{n,k}\).

For each vertex \(z\), extract the complete tuple \(a_z\) from \(r_0\).
It lies in \(A_z\): a velocity witnessing \(r_0\in Q_{n,k}\), restricted
to the complete incident star, satisfies exactly the continuous source
and physical boundary conditions used to define \(A_z\).
Set

\[
r_v=r_0-\sum_zD R_za_z.
\]

The protections in the table make all vertex coefficients and all cell
means of \(r_v\) zero. This residual also remains in \(Q_{n,k}\).
All vertex tuples are read from the same \(r_0\); one vertex correction
does not alter another target.

For each edge \(e\), extract its complete interior tuple \(b_e\) from
\(r_v\). The same actual-source argument gives \(b_e\in E_{e,k}\).
The endpoint coefficients are already zero. Put

\[
r_e=r_v-\sum_eD R_eb_e.
\]

Now every vertex and edge-interior coefficient is zero, and every cell
mean remains zero. Thus \(c_T=r_e|_T\) belongs to \(B_{T,k}\) on each
tetrahedron. The element inverse yields

\[
r_e=\sum_TD R_Tc_T.
\]

The four equations telescope to \(q=F(m,(a_z),(b_e),(c_T))\). Therefore
\(F\) is onto the **actual** divergence image.

### Independence of all coordinate factors

Suppose \(F(m,(a_z),(b_e),(c_T))=0\). Extract cell means. All terms except
the mean term have zero cell means, so \(m=0\). By linearity \(R_0m=0\).

Next extract the tuple at an arbitrary vertex \(z\). Every edge and
bubble term has zero vertex data, and every other vertex map preserves
this target. The extracted tuple is exactly \(a_z\), hence \(a_z=0\)
for every \(z\).

With those terms zero, extracting the interior tuple at an arbitrary
edge \(e\) gives exactly \(b_e\). All other edge maps preserve it, and
all bubbles have zero edge data. Thus every \(b_e=0\).

Only \(\sum_T\widetilde c_T=0\) remains. The cell interiors are disjoint,
so \(c_T=0\) for every \(T\). This proves that \(F\) is one-to-one.

Consequently

\[
\boxed{F:X_{n,k}\longrightarrow Q_{n,k}\ \text{is a linear isomorphism}.}
\tag{6}
\]

This is the independence argument behind the dimension count. Patch
supports may overlap; their prescribed and protected divergence
coordinates make the pressure contributions independent. Orthogonality
of the supports or of the resulting pressure fields is not required.

The inverse of \(F\) is exactly the successive residual extraction
described above. In particular, the vertex and edge coordinates in (3)
are those extracted **after the earlier stage has been subtracted**.
They should not all be read from the original \(q\) and then treated as
unchanged data for the four synthesis stages.

Choosing a basis in each factor of (3) and applying \(F\) produces a
basis of \(Q_{n,k}\). There is no additional global relation among those
factor coordinates.

## 4. Cell means and vertex coordinates

There are \(6n^3\) tetrahedra, and every zero-sum mean tuple is realized
by \(R_0\). Hence

\[
\dim M_n=6n^3-1.
\tag{7}
\]

The [complete vertex census](GLOBAL_PATCH_PLAN.md#complete-census) and
the protected [interior](INTERIOR_VERTEX_LIFT.md) and
[boundary](BOUNDARY_VERTEX_LIFT.md) source images give:

| Vertex class | Number | Source dimension per vertex |
| --- | ---: | ---: |
| Interior | \((n-1)^3\) | 18 |
| Inside one boundary face | \(6(n-1)^2\) | 8 |
| Same-side boundary crease | \(6(n-1)\) | 5 |
| Mixed-side boundary crease | \(6(n-1)\) | 0 |
| Same-side corner | 2 | 3 |
| Mixed-side corner | 6 | 0 |

For a crease, same-side means that the two fixed coordinates are both
on lower faces or both on upper faces. For a corner, all three sides
agree. These are source classes of the fixed Kuhn orientation.

Thus the total independent vertex dimension is

\[
\begin{aligned}
d_A(n)
&=18(n-1)^3+48(n-1)^2+30(n-1)+6\\
&=18n^3-6n^2-12n+6.
\end{aligned}
\tag{8}
\]

This count is the same for degrees four and five.

## 5. Edge-interior coordinates

A degree-\((k-1)\) pressure trace on one edge has \(k-2\) interior
Bernstein coefficients after its two endpoints are fixed. The following
source dimension is **per interior mode**, across the complete
incident-cell star.

| Edge class | Number | Source dimension per mode | Source relation |
| --- | ---: | ---: | --- |
| Body diagonal | \(n^3\) | 6 | Full six-cell image |
| Interior face diagonal | \(3n^2(n-1)\) | 3 | One relation among four incident values |
| Boundary face diagonal | \(6n^2\) | 1 | The two incident values agree |
| Interior axial | \(3n(n-1)^2\) | 6 | Full six-cell image |
| Axial inside one boundary face | \(12n(n-1)\) | 3 | Full three-cell image |
| Same-side boundary crease | \(6n\) | 2 | Full two-cell image |
| Mixed-side boundary crease | \(6n\) | 0 | Zero image |

The interior face relation is \(y_1-y_2-y_3+y_4=0\) in its retained
incident-cell order. It is imposed separately in each interior mode.
The other relations in the table likewise act independently per mode.
Complete source derivations are linked in the
[edge compatibility section](GLOBAL_DIVERGENCE_BOUND.md#6-compatibility-comes-from-the-actual-residual-image);
the [planner](GLOBAL_PATCH_PLAN.md#complete-census) supplies the counts.

The per-mode dimension sum is

\[
\begin{aligned}
s_E(n)
={}&6n^3+9n^2(n-1)+6n^2\\
 &+18n(n-1)^2+36n(n-1)+12n\\
={}&33n^3-3n^2-6n.
\end{aligned}
\tag{9}
\]

Therefore

\[
d_E(n,k)=(k-2)(33n^3-3n^2-6n).
\tag{10}
\]

The zero-image crease edges contribute no independent data, while still
belonging to the complete geometric census.

## 6. The final element residual

After all coefficients supported on one or two tetrahedral vertices
vanish, a cubic pressure has four face-interior coefficients left.
Their sum is zero by the cell-mean condition, leaving three independent
coordinates.

A quartic pressure has twelve face-interior coefficients and one
cell-interior coefficient left. Their single sum condition leaves
twelve independent coordinates.

The [element-bubble inverse](CELL_BUBBLE_LIFT.md) realizes every member
of these complete residual spaces with a zero-face-trace velocity.
There is no coupling between different cells. Thus

\[
\dim B_{T,4}=3,\qquad \dim B_{T,5}=12,
\]

\[
d_B(n,4)=18n^3,\qquad d_B(n,5)=72n^3.
\tag{11}
\]

For the cubic residual the one dependent coordinate can be any chosen
face coefficient. For the quartic residual it can be the cell-interior
coefficient, with the twelve face coefficients free. These choices
exhibit the stated dimensions directly.

## 7. Pressure rank and its codimension

By the isomorphism (6),

\[
\dim Q_{n,k}
=(6n^3-1)+d_A(n)+d_E(n,k)+d_B(n,k).
\tag{12}
\]

Substituting (8), (10) and (11) gives

\[
\begin{aligned}
\dim Q_{n,4}
={}&(6n^3-1)+(18n^3-6n^2-12n+6)\\
 &+2(33n^3-3n^2-6n)+18n^3\\
={}&108n^3-12n^2-24n+5,\\[1mm]
\dim Q_{n,5}
={}&(6n^3-1)+(18n^3-6n^2-12n+6)\\
 &+3(33n^3-3n^2-6n)+72n^3\\
={}&195n^3-15n^2-30n+5.
\end{aligned}
\tag{13}
\]

The full discontinuous degree-\((k-1)\) pressure space has
\(6n^3\binom{k+2}{3}\) scalar coefficients: \(120n^3\) for degree-four
velocity and \(210n^3\) for degree-five velocity. Its zero-integral
subspace has one fewer dimension. The codimension of the actual
divergence image **inside that zero-integral space** is consequently

\[
\begin{aligned}
(120n^3-1)-\dim Q_{n,4}&=12n^3+12n^2+24n-6,\\
(210n^3-1)-\dim Q_{n,5}&=15n^3+15n^2+30n-6.
\end{aligned}
\tag{14}
\]

These are consequences of a proved image basis. They do not assume that
an unexamined list of raw constraint rows is independent.

## 8. Continuous velocity dimension and rank-nullity

On one Kuhn cube, every degree-\(k\) Bernstein coefficient node has
coordinates in the \(1/k\) lattice. Conversely, every point of that
lattice inside the cube is a coefficient node of at least one Kuhn
tetrahedron: order its three fractional coordinates, and use their
successive differences as the barycentric coordinates along the
corresponding monotone chain. Multiplying by \(k\) gives nonnegative
integer multi-indices summing to \(k\).

Across the mesh, two tetrahedra sharing a face have the same polynomial
trace exactly when their corresponding face Bernstein coefficients
agree. The analogous edge and vertex identifications follow. Hence a
single scalar coefficient at each shared global coefficient node
parametrizes the continuous scalar degree-\(k\) space.

The global node set is the complete fine lattice with \(kn+1\) positions
in each coordinate. Zero exterior trace sets precisely the boundary-node
coefficients to zero. Each of the remaining \((kn-1)^3\) coefficients is
free; assigning them defines continuous polynomial traces without any
additional relation. Three velocity components therefore give

\[
\dim V_{n,k}=3(kn-1)^3.
\tag{15}
\]

These are Bernstein **coefficients**; the argument does not identify
them with polynomial values at interior nodes.

Rank-nullity for \(D:V_{n,k}\to Q_{n,k}\) now yields

\[
\dim Z_{n,k}=3(kn-1)^3-\dim Q_{n,k},
\tag{16}
\]

which expands to (2). Continuity and the Dirichlet boundary are already
included in (15); counting all cell-local vector coefficients would
give the wrong kernel dimension.

## 9. Concrete sizes and the supplied projector

The following values are substitutions into the proved formulas.
They are not reports of additional numerical rank runs.

| n | Velocity degree | Means | Vertex coordinates | Edge coordinates | Element residual coordinates | Image dimension | Velocity dimension | Kernel dimension |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 4 | 47 | 102 | 480 | 144 | 773 | 1,029 | 256 |
| 2 | 5 | 47 | 102 | 720 | 576 | 1,445 | 2,187 | 742 |
| 3 | 4 | 161 | 402 | 1,692 | 486 | 2,741 | 3,993 | 1,252 |
| 3 | 5 | 161 | 402 | 2,538 | 1,944 | 5,045 | 8,232 | 3,187 |

At \(n=2\), the existing complete-pressure interface stores 960 or
1,680 pressure coefficients, respectively. The smaller image dimensions
above count independent pressure data. The coordinate isomorphism
explains how a basis can be synthesized, while the current program
continues to accept its existing complete arrays.

The existing right inverse is

\[
\mathcal L=R F^{-1}:Q_{n,k}\longrightarrow V_{n,k},
\qquad D\mathcal L=I.
\tag{17}
\]

It supplies the exact divergence-free projector

\[
P=I-\mathcal L D:V_{n,k}\longrightarrow Z_{n,k}.
\tag{18}
\]

Indeed, \(DP=0\), \(Pz=z\) for every \(z\in Z_{n,k}\), and
\(P^2=P\) follows from \(D\mathcal L=I\). Moreover,

\[
V_{n,k}=Z_{n,k}\oplus\mathcal L(Q_{n,k}).
\tag{19}
\]

The intersection is zero because \(\mathcal L q\in Z_{n,k}\) implies
\(q=D\mathcal L q=0\). Thus subtracting the existing constructor's lift
of a supplied velocity's divergence leaves an exactly divergence-free
field. This conclusion uses the current shared coefficient convention;
it introduces no new input format or runtime command.

The chosen complement depends on the fixed component maps. The
projector is not asserted to be energy-orthogonal. If \(C_k\) is the
right-inverse bound already derived in
[GLOBAL_DIVERGENCE_BOUND.md](GLOBAL_DIVERGENCE_BOUND.md), then

\[
|Pv|_{H^1}\le |v|_{H^1}+C_k\|Dv\|_{L^2}
\le(1+\sqrt3\,C_k)|v|_{H^1}.
\tag{20}
\]

The pressure-image dimension also differs from the dimension of the
mean solver's reduced factorization. That [existing dense mean system](MEAN_ENERGY_LIFT.md) has
\(9n^3-15n^2+9n-2\) free coordinates, or 28 at \(n=2\) and 133 at
\(n=3\). The dimension formulas do not remove that implementation's
dense exact-algebra cost.

## 10. Source basis and scope

This derivation composes the established source-image and protection
identities; all component authors retain their original attribution in
the linked guides. The source state read for this note is:

| Source | Git blob |
| --- | --- |
| [Global constructor guide](GLOBAL_DIVERGENCE_LIFT.md) | 48ce5bf73ded6dea76a16e5bb3c34ee7f8308c7a |
| [Complete patch census](GLOBAL_PATCH_PLAN.md) | aa04be8c8fc021ace7dd1d5e9dae3178766534f8 |
| [Global compatibility and bound](GLOBAL_DIVERGENCE_BOUND.md) | 6ad5daadbf6d0ea36cda2990c3a09c5d2b6d6aeb |
| [Complete element residual inverse](CELL_BUBBLE_LIFT.md) | adcf20dbe6169f0dbb549b77952c802a96258d46 |

The result is an analytic consequence for the stated uniform cubic
meshes and degrees. It does not establish formulas for other
triangulations, mixed boundary conditions, \(n=1\), or arbitrary
anisotropic refinements. No local operator construction or global rank
calculation was repeated. Scientific novelty, external manuscript
disposition and any sponsor process are separate from this dimension
derivation.
