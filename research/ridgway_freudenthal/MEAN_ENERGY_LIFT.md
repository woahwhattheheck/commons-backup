# Minimum-energy cell-mean lift

Issue: https://github.com/woahwhattheheck/commons/issues/14999

`mean_energy_lift.py` constructs the unique velocity of minimum H1
seminorm in a continuous P1 vector space enriched by normal cubic face
bubbles, subject to the prescribed divergence mean in every tetrahedron.
It returns that same cubic field in normalized degree-four or degree-five
Bernstein coordinates.

The constructor works on a uniform n-by-n-by-n Kuhn grid for every positive
integer n. It uses exact rational geometry, integration and linear algebra.
For n=2 it eliminates 47 independent mean constraints and solves a
28-by-28 positive-definite system, instead of a 122-variable saddle system.
The API reuses its geometry and factorization for subsequent mean vectors;
the CLI can emit both polynomial degrees from a single factorization and
mean solve.

The minimum-energy choice has a bound independent of the mesh size on a
fixed cube. The proof below supplies a bounded feasible field using a
continuous divergence right inverse, a boundary-preserving interpolant
and face flux corrections, then compares the finite-dimensional minimizer
with that field. It does not assume a uniform bound for the previous
whole-grid tree-routing operator.

## Use

Python 3.10+, standard library only. Runtime dependencies are
`kuhn.py`, `p4_mean_repair.py` and
`cell_bubble_lift.py`; only their geometry, index and exact-integration
helpers are imported. No earlier mean-repair elimination or stored repair
basis is used.

```sh
python research/ridgway_freudenthal/mean_energy_lift.py \
  --subdivisions 2 --both-degrees \
  --origin=-2,1/3,5/2 --cell-size 3/2 \
  --output minimum-energy-means.json

python research/ridgway_freudenthal/mean_energy_lift.py \
  --subdivisions 1 --degree 5 \
  --means=1/3,-2/3,1,-4/3,5/3,-1
```

`--means` takes all \(6n^3\) cell means in the displayed cell order:
cube x, then y, then z, then the six positive tetrahedra from
`kuhn_tets()`. If omitted, it uses the balanced example
`[1,0,...,0,-1]`. Because the cells have equal volume, the means must
sum to zero. The constructor rejects incompatible input before assembling
the linear system.

Origin uses three comma-separated exact numbers. Cell size is positive
and defaults to \(1/n\), giving the unit cube at the requested origin.
A caller may select another rational size; the physical cube side is
n times that size. Negative fractions are unambiguous with the
`--origin=...` and `--means=...` spellings.

A specified output path must be new. Otherwise JSON goes to stdout.
Failures return a nonzero exit code and an explanatory error message.

For repeated inputs:

```python
import sys
sys.path.insert(0, "research/ridgway_freudenthal")
from mean_energy_lift import assemble, construct

prepared = assemble(2)
means = [1] + [0]*46 + [-1]
quartic = construct(means, degree=4, subdivisions=2, assembly=prepared)
quintic = construct(means, degree=5, subdivisions=2, assembly=prepared)
```

`assemble` builds and factors once; `construct` solves a new
right-hand side in that prepared space and emits the physical field.
The CLI's `--both-degrees` also reuses the same mean solution.

The output includes physical tetrahedra, coefficient nodes multiplied by
the velocity degree, sparse shared velocity coefficients, every physical
divergence coefficient, all cell means and integrals, nodal values, oriented
face fluxes, exact energy and solver dimensions. Omitted velocity
coefficients are zero. A Bernstein coefficient multiplies a normalized
Bernstein polynomial; it is not a point value.

The supplied data describe means. The polynomial divergence generally has
additional vertex and edge coefficients. This lift goes first in the
planned mean/vertex/edge/element composition.

## Finite-element space and normalized fluxes

Work initially on the lattice cube \([0,n]^3\), whose tetrahedra have
volume \(V=1/6\). For a tetrahedron T, write its barycentric gradients as
\(g_i=\nabla\lambda_i\).

There are three P1 nodal velocity coordinates at each interior grid
vertex. For each interior triangular face F, fix one nonzero rational
normal \(N_F\). The implementation uses the primitive integer cross
product of its ordered lattice edges, choosing its first nonzero
component positive.

On either neighboring tetrahedron, if F is opposite local vertex l, put

\[
b_F|_T=\prod_{i\ne l}\lambda_i.
\]

The two traces on F coincide. On every other face the polynomial vanishes.
Extending it by zero beyond the two tetrahedra therefore gives a continuous
function with zero trace on the outer domain boundary. These are the normal
face bubbles used in the Bernardi–Raugel construction; the definition is
also recorded in [Guzmán–Neilan, §5.1][GN].

Let

\[
\gamma_F=\frac{V\,|N_F\cdot g_l|}{20},
\qquad
\psi_F=\frac{N_F b_F}{\gamma_F}.
\]

Both incident cells give the same positive rational \(\gamma_F\).
Since \(\int_Fb_F=|F|/60\), its oriented flux along \(N_F\) is one.
With outward flux sign
\(s_{TF}=\operatorname{sign}(-N_F\cdot g_l)\),

\[
\int_T\operatorname{div}\psi_F=s_{TF}.
\]

Thus the face columns of the cell-integral matrix are exactly an oriented
incidence matrix of the tetrahedron dual graph. A nodal vector basis
\(\lambda_z e_a\) contributes

\[
\int_T\operatorname{div}(\lambda_z e_a)=V(g_z)_a.
\]

Write the entire velocity space as

\[
W_h=[S_h^1\cap H_0^1(\Omega)]^3+
\operatorname{span}\{\psi_F:F\text{ interior}\}.
\]

These nodal and face coordinates are independent: vertex values determine
the P1 coordinates, and then each face flux determines its bubble
coordinate. The stiffness form
\(a(u,v)=\int_\Omega\nabla u:\nabla v\)
is consequently positive definite on their coordinate space.

## Exact sparse stiffness

Let A be the stiffness matrix and C the matrix of integrated divergence.
Only basis functions sharing a tetrahedron couple. The implementation
assembles the following exact local terms:

\[
A^T_{(z,a),(w,b)}
=\delta_{ab}V(g_z\cdot g_w),
\]

\[
A^T_{(z,a),F}
=-\frac{V\,N_{F,a}}{20\gamma_F}(g_z\cdot g_l).
\]

For faces opposite l and m, define
\(\beta_{li}=\mathbf1-e_l-e_i\), \(i\ne l\). Then

\[
A^T_{F,G}
=\frac{N_F\cdot N_G}{\gamma_F\gamma_G}
\sum_{i\ne l,\ j\ne m}(g_i\cdot g_j)
\int_T\lambda^{\beta_{li}+\beta_{mj}}.
\]

Each exponent in the last integral has total degree four. The exact
simplex formula gives

\[
\int_T\lambda^\alpha
=\frac{V}{840}\prod_r\alpha_r!
=\frac1{5040}\prod_r\alpha_r!
\quad (|\alpha|=4,\ V=1/6).
\]

No face-area square roots or quadrature estimates enter the matrix.
The program separately integrates the final cubic field's nine gradient
components in a degree-two Bernstein basis and requires that energy to
equal the assembled quadratic form exactly.

## Eliminating the mean constraints

The compatibility condition is
\(\sum_T|T|q_T=0\). On this grid it is equivalent to
\(\sum_Tq_T=0\), and the reference integrated target is \(m_T=q_T/6\).
Every column of C sums to zero.

The connected dual graph has a deterministic spanning tree rooted at
cell zero. Its incidence columns have rank \(N_T-1\), so every compatible
m is attainable. If a tree edge joins a child subtree to its parent, the
unique tree-only flux for a residual r is

\[
f_e=s_{\mathrm{child},e}
\sum_{T\text{ in child subtree}}r_T.
\]

This routing supplies a particular feasible vector \(x_p\).
All interior nodal values and all non-tree face fluxes remain free.
For each of those coordinates, set it to one, subtract its cell-integral
column from the residual, and use the same tree back-substitution.
The resulting columns form a complete constraint-kernel basis Z.

Therefore every feasible velocity has the unique coordinate form

\[
x=x_p+Zz.
\]

Minimizing the energy gives

\[
(Z^\top AZ)z=-Z^\top Ax_p.
\]

The reduced matrix is positive definite because A is positive definite and
Z has independent columns. Exact LDL-transpose factorization needs no
square roots or numerical pivot tolerances. The constructor checks every
cell integral and every reduced stationarity row after solving.

The tree is only a coordinate parameterization. All nodal and cycle
directions participate in the minimization; its result is the minimum over
the complete space \(W_h\).

### Dimensions and cost

| Quantity | General n | n=1 | n=2 |
| --- | --- | ---: | ---: |
| Tetrahedra | \(6n^3\) | 6 | 48 |
| Interior triangular faces | \(12n^3-6n^2\) | 6 | 72 |
| Interior nodal vector coordinates | \(3(n-1)^3\) | 0 | 3 |
| Independent mean constraints | \(6n^3-1\) | 5 | 47 |
| Reduced free coordinates | \(9n^3-15n^2+9n-2\) | 1 | 28 |
| Full saddle variables | velocity coordinates plus independent constraints | 11 | 122 |

A is sparse, but fundamental-cycle columns can be long and the reduced
matrix can fill in. The current implementation uses dense reduced
factorization: \(O(d^3)\) rational field operations and \(O(d^2)\) reduced
storage, with additional integer bit growth. It is a practical exact
constructor for small grids, including the displayed n=2 case. Its uniform
stability theorem is independent of this solver's asymptotic cost.

## Embedding and physical reconstruction

For a degree-k local multi-index alpha, the P1 contribution is

\[
c_\alpha^{\mathrm{node}}
=\sum_i\frac{\alpha_i}{k}U(v_i).
\]

A face bubble \(t_FN_F b_F/\gamma_F\) contributes

\[
c_\alpha^{F}
=\frac{t_FN_F}{\gamma_F}
\frac{\prod_{i\in F}\alpha_i}{k(k-1)(k-2)}.
\]

These formulas are exact degree elevation of the same cubic field into
P4 or P5. The constructor checks that repeated global coefficient nodes
agree across adjacent cells, and that every coefficient on the outer
domain boundary is zero.

For physical coordinates \(x=a+h\xi\), it sends a reference coefficient
node N to \(ka+hN\) and a velocity coefficient c to hc. Barycentric
gradients scale by \(h^{-1}\), so divergence values and cell means stay
unchanged. Physical cell integrals, oriented face fluxes and squared H1
energy scale by \(h^3\).

After creating the physical cells and shared coefficient dictionary, the
program reconstructs every divergence coefficient using their physical
barycentric gradients and requires the average of each cell's coefficients
to match its requested mean. It returns those divergence coefficients for
the subsequent vertex and edge stages.

## Uniform bound for the mean lift

Fix \(\Omega=(0,1)^3\) and its conforming uniform Kuhn meshes with cell size
\(h=1/n\). Let \(q_0\) be piecewise constant and have integral zero.

A bounded linear continuous right inverse gives
\(w\in H_0^1(\Omega)^3\) with

\[
\operatorname{div}w=q_0,\qquad
\|\nabla w\|_{L^2(\Omega)}
\le C_B\|q_0\|_{L^2(\Omega)}.
\]

The cube is star-shaped with respect to a fixed ball. [Durán, equations
(1.1)–(1.3) and Theorem 3.2][Duran] establish this property of Bogovskii's
operator using only L2 data; the constant depends on the fixed domain.

Use a componentwise boundary-preserving Scott–Zhang P1 interpolant \(I_h\).
On a fixed neighboring-element patch \(\omega_T\), its local estimate gives

\[
\|w-I_hw\|_{L^2(T)}
\le C h\|\nabla w\|_{L^2(\omega_T)},\qquad
\|\nabla(w-I_hw)\|_{L^2(T)}
\le C\|\nabla w\|_{L^2(\omega_T)}.
\]

It also maps the zero trace of w to zero boundary nodal values.
These are the homogeneous-boundary property of [Scott–Zhang, Theorem 2.1,
and the local estimate (4.3)][SZ], with regularity one, exponent two and
derivative orders zero and one.

Put \(e=w-I_hw\). For each interior face F choose one unit normal \(n_F\).
The scaled H1 trace inequality on a reference tetrahedron gives

\[
\|e\|_{L^2(F)}^2
\le C\bigl(h^{-1}\|e\|_{L^2(T)}^2+
h\|\nabla e\|_{L^2(T)}^2\bigr),
\]

so, on a fixed face patch \(\omega_F\),

\[
\left|\delta_F\right|
:=\left|\int_F e\cdot n_F\right|
\le C h^{3/2}\|\nabla w\|_{L^2(\omega_F)}.
\]

Define the feasible comparison field

\[
R_hq_0=I_hw+
\sum_{F\text{ interior}}\frac{60\delta_F}{|F|}b_F n_F.
\]

It belongs to the same space \(W_h\), since rational and unit normals give
the same one-dimensional face-bubble spans. Its interior face fluxes equal
those of w. Its boundary fluxes also agree because both w and \(I_hw\) have
zero trace and all corrections vanish on the outer boundary. Integration
by parts on each element therefore gives

\[
\frac1{|T|}\int_T\operatorname{div}R_hq_0=q_T.
\]

The coefficient of each correction is bounded by
\(C h^{-1/2}\|\nabla w\|_{L^2(\omega_F)}\).
Affine scaling of the fixed cubic bubble gives
\(\|\nabla b_F\|_{L^2(T^+\cup T^-)}\le C h^{1/2}\).
At most four such face bubbles occur in one tetrahedron, and the patches
\(\omega_F\) overlap a uniformly bounded number of times. Squaring and
summing yields

\[
\left\|\nabla\sum_F\frac{60\delta_F}{|F|}b_Fn_F\right\|_{L^2(\Omega)}
\le C\|\nabla w\|_{L^2(\Omega)}.
\]

Adding the interpolant's H1 bound and the continuous right-inverse estimate
proves

\[
\|\nabla R_hq_0\|_{L^2(\Omega)}
\le C\|q_0\|_{L^2(\Omega)}
\]

with C independent of n.

The constructor's exact minimizer \(v_h\) has the same cell means and
minimizes over the entire feasible space containing \(R_hq_0\). Consequently,

\[
\boxed{\|\nabla v_h\|_{L^2(\Omega)}
\le\|\nabla R_hq_0\|_{L^2(\Omega)}
\le C\|q_0\|_{L^2(\Omega)}.}
\]

The rational finite solve needs no numerical evaluation of Bogovskii's
operator or the Scott–Zhang interpolant; those operators establish the
bounded comparison field. Poincaré's inequality supplies a full H1 norm
bound on the fixed domain. Translation and isotropic rescaling preserve the
seminorm-to-pressure ratio.

The output's energy-to-data ratio is an exact value for the supplied mean
vector. It is not presented as an optimal uniform constant.

## Completed native use

On 2026-10-03, the actual CLI constructed the n=2 field with
`--both-degrees --origin=-2,1/3,5/2 --cell-size 3/2`. Its 48 means were
`means[i] = (7*i) % 13 - 6` for indices 0 through 46, followed by
the negative sum of those 47 entries.

The single geometry assembly, factorization and mean solve returned both
degrees in 0.526375 seconds. Each result matched all 48 physical cell means,
with 960 reconstructed pressure coefficients for P4 and 1,680 for P5.
There were 307 and 681 nonzero shared coefficient nodes. Every boundary
coefficient, mean residual, reduced stationarity residual and difference
between independently integrated energy and the stiffness quadratic form
was exactly zero. The physical energy was
`16561848852687224212631150585/12003238592428120042771584`;
the feasible tree field had energy `393675/28`.
These are values for this input, not estimates of a sharp uniform constant.

The API then reused an explicitly prepared n=1 assembly for the six means
`[1/3,-2/3,1,-4/3,5/3,-1]`, P5, origin `(2/7,-3,5/2)`
and cell size `2/3`. It returned all 210 pressure coefficients,
matched all six means, and integrated energy `40480/45927`,
with the exact energy-to-data ratio `1265/504`.
Its reduced system had one coordinate.

A further actual CLI call supplied a nonzero total mean. It returned
exit code 1 with the exact sum residual 1 and created no output file.
The complete wrapper took 0.614435 seconds; the largest child peak RSS was
17,880 KiB. The three imported runtime files and all materialized source
bytes remained unchanged. No earlier mean solve or proof artifact was
recomputed.

## Place in the complete divergence construction

For a pressure in the actual divergence image, first take its cell means
and subtract the divergence of this mean lift. The residual still belongs
to that image, because the field just constructed lies in the continuous
degree-k velocity space. Every residual cell mean is zero.

The accepted vertex and edge operators preserve those means, and the
element-bubble operator handles the remaining cell-local residual. A
complete global construction also requires the geometric patch embeddings,
target-coordinate maps and bounded-overlap argument for those stages.
The present result supplies the initial stable mean component, including
n=1, without asserting that those other assembly obligations have already
been discharged.

## Primary references

[Duran]: https://arxiv.org/pdf/1103.3718
[SZ]: https://www.researchgate.net/publication/242922462_Finite_element_interpolation_of_nonsmooth_functions_satisfying_boundary_conditions
[GN]: https://www.dam.brown.edu/people/jguzman/documents/paperrevisionv3r_000.pdf

1. Ricardo G. Durán, *An elementary proof of the continuity from L2 to H1 of
   Bogovskii's right inverse of the divergence*, arXiv:1103.3718.
   Use the mean-zero and zero-trace spaces in the paper's full title and
   statement; equations (1.1)–(1.3), Theorem 3.2.
2. L. Ridgway Scott and Shangyou Zhang, *Finite element interpolation of
   nonsmooth functions satisfying boundary conditions*, Mathematics of
   Computation 54 (1990), 483–493,
   DOI [10.1090/S0025-5718-1990-1011446-7](https://doi.org/10.1090/S0025-5718-1990-1011446-7).
   The linked author copy supplies Theorem 2.1 and equation (4.3).
3. Johnny Guzmán and Michael Neilan, author manuscript linked above,
   §5.1, for the normal face-bubble definition. The comparison and
   minimum-energy argument here use the plain polynomial enriched space
   defined in this guide.
