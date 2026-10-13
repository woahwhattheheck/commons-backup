# Ridgway–Freudenthal Scott–Vogelius lane

Issue: https://github.com/woahwhattheheck/commons/issues/14999

This is the isolated research surface for the Freudenthal/Kuhn divergence problem. It does not submit anything to the Ridgway Scott Foundation or claim a prize.

## Global construction

[The composed constructor and usage](GLOBAL_DIVERGENCE_LIFT.md) apply the
minimum-energy mean, protected vertex, protected edge and element-bubble
stages on every uniform n-by-n-by-n grid with n at least two, for degrees
four and five. It consumes retained reference matrices, uses the exact
[global patch planner](GLOBAL_PATCH_PLAN.md), and returns shared physical
velocity coefficients whose complete divergence is reconstructed exactly.

Run `global_divergence_lift.py pressure.json --energy --output velocity.json`.
The input is a complete native-order pressure array; `--from-velocity`
instead derives that input from supplied shared Dirichlet coefficients.
The reusable API retains geometry, local maps and the mean factorization.
No local vertex or edge constructor is rerun.

[The global bound](GLOBAL_DIVERGENCE_BOUND.md) composes the local estimates
on the actual divergence image, including the complete class census,
source compatibility, pressure coefficient extraction and overlap counts.
It establishes a mesh-independent right-inverse constant for degrees four
and five and treats n=1 separately by finite-dimensional existence.
The executable's dense exact mean solver is intended for small grids.
The sections below retain the local construction history and its numerical
operator data; their former references to remaining assembly work describe
the state before this global composition.

## Exact pressure and kernel dimensions

[The dimension derivation](DIVERGENCE_DIMENSION.md) proves that the mean,
vertex, edge and element-residual coordinates form a linear isomorphism
onto the actual divergence image for n at least two. The pressure
dimensions are \(108n^3-12n^2-24n+5\) at degree four and
\(195n^3-15n^2-30n+5\) at degree five. Subtracting these from
\(3(kn-1)^3\) gives the continuous Dirichlet divergence-kernel dimensions.

The note proves independence and spanning from the protected component
maps, gives exact size tables, and derives the projector
\(I-\mathcal L\operatorname{div}\) from the existing right inverse.
It preserves the current complete-pressure runtime format.

[The separate single-cube calculation](SINGLE_CUBE_DIMENSION.md) gives
the exact n=1 image/kernel pairs **76/5** at degree four and **155/37**
at degree five. The quartic case is an exception to substituting n=1
into the n>=2 formulas. `single_cube_dimension.cjs` constructs the full
integer divergence matrix and returns a nonzero-minor/kernel-basis
certificate for either degree.

## Usable two-cube quartic mean repair

[The constructed operator and derivation](P4_MEAN_REPAIR.md) realize any twelve zero-sum cell-average divergences with a continuous piecewise-quartic velocity, zero boundary trace, and zero divergence on every tetrahedral edge.

```sh
python research/ridgway_freudenthal/p4_mean_repair.py \
  --means 1 0 0 0 0 0 0 0 0 0 0 -1
```

Python 3.10+, standard library only. The reusable sparse rational operator is `p4_mean_repair_basis.json`. Its tetrahedra and Bernstein coefficient ordering are explicit. The exact construction has 189 unknowns, edge rank 122, combined edge/mean rank 133, and 202 nonzero operator coefficients. It establishes the local mean-repair image, not the full mesh-uniform theorem.

## Rectangular-grid composition

[The grid solver and derivation](P4_GRID_MEAN_REPAIR.md) extend the local operator to any rectangular Kuhn grid with at least two cubes, including exact translation and isotropic scale. Use `p4_grid_mean_repair.py input.json --output velocity.json`. It matches all zero-sum cell means, preserves zero edge divergence and boundary trace, and returns shared sparse Bernstein coefficients. The guide also gives an explicit fixed-patch bound and explains how to preserve a raw lift's edge traces while removing its cell means. The whole-domain bound depends on the cube count; it is not the mesh-uniform theorem.

## Protected body-diagonal lift

[The degree-four body-diagonal operator](P4_BODY_DIAGONAL_LIFT.md) now accepts any
twelve interior cubic edge coefficients and returns a continuous quartic field
with those traces, zero divergence on every other edge, zero patch boundary trace,
and zero cell means. It composes the existing local mean repair on a fixed two-cube
patch. Run `p4_body_diagonal_lift.py --trace 1 -1 2 -2 3 -3 4 -4 5 -5 6 -6`.
The exact 189×12 map has 270 nonzeros and a reference seminorm-squared bound of
1728 times the trace-coefficient norm squared.

[The degree-five companion](P5_BODY_DIAGONAL_LIFT.md) accepts eighteen coefficients
and degree-elevates the same quartic mean correction. Its exact 432×18 map has
1,763 nonzeros and seminorm-squared bound `39744/49` in trace-coefficient norm.
Use `p5_body_diagonal_lift.py --trace` with eighteen values, three per cell.
[The six-neighbor transport and derivation](BODY_DIAGONAL_TRANSPORT.md) extend
both operators to `+x`, `-x`, `+y`, `-y`, `+z`, and `-z`, with exact rational
translation and positive isotropic scaling. Use
`body_diagonal_transport.py --degree 4 --all-neighbors` (or degree 5).
The origin is the central cube's lower corner; negative directions retain
the reference endpoint order and relabel local vertices consistently.
One retained mean-repair basis supplies all six transports without another
mean solve. Other classes, general patch selection and the global theorem
remain separate work.

## Singular interior face-diagonal lift

[The face-diagonal operator](FACE_DIAGONAL_LIFT.md) supplies both degrees on the
fixed shared face of two Kuhn cubes. It reconstructs the actual checkerboard
source relation `y1-y2-y3+y4=0` per mode, then builds a protected, zero-cell-mean
lift for every compatible trace. Use `face_diagonal_lift.py --degree 4` or
`--degree 5`, with eight or twelve trace coefficients. Admissible dimensions are
six and nine; final maps have 34 and 174 nonzero coefficients.

[The coordinate transport and proof](FACE_DIAGONAL_TRANSPORT.md) extend this same
interior class to the three coordinate-normal orientations, with exact rational
translation and positive isotropic scaling. Other edge classes, the full census
and global assembly remain separate.

## Interior axial-edge lift

[The axial-edge operator and derivation](AXIAL_EDGE_LIFT.md) construct protected
lifts for all twelve quartic or eighteen quintic endpoint-zero target
coefficients on a four-cube patch. The target source image is full. All other
edge divergence traces, all 24 cell means, and the patch-boundary velocity trace
are zero. Use `axial_edge_lift.py --all-axes` with `--degree 4` or `--degree 5`
for the three cyclic axial directions with exact translation and isotropic scale.
The final reference maps have 381 and 2,298 nonzeros, with conservative
seminorm-squared bounds `5248` and `98136/49` in complete trace-coefficient norm;
physical scaling multiplies these bounds by `h³`. The full census and
mesh-uniform theorem remain separate.

## Boundary face-diagonal lift

[The boundary face-diagonal operator and derivation](BOUNDARY_FACE_DIAGONAL_LIFT.md)
construct quartic and quintic protected lifts under the Dirichlet condition.
The two incident traces must agree in every interior mode: four complete
quartic coordinates have two free coordinates, and six quintic coordinates
have three. The final reference maps use only four and five nonzero scalar
coefficients. They set all other-edge and endpoint divergence traces, all twelve
cell means, and the entire patch-boundary velocity trace to zero. Both degrees have
a conservative seminorm-squared bound of `72` in complete compatible
trace-coordinate norm. Use `boundary_face_diagonal_lift.py --all-faces` with
`--degree 4` or `--degree 5` for all six lower/upper coordinate-face directions;
exact translation and positive isotropic scaling multiply the bound by `h³`.
The derivation records the vertex and Bernstein-index relabelling for upper
faces. This is one boundary class; the full census and global theorem remain
separate.

## Boundary axial-edge lift

[The boundary axial-edge operator and derivation](BOUNDARY_AXIAL_EDGE_LIFT.md)
realize every six-coordinate quartic or nine-coordinate quintic endpoint-zero
trace on the three-cell Dirichlet source star. The protected two-cube outputs
have zero other-edge and endpoint divergence, all twelve means zero, and zero
patch-boundary velocity trace. Their final reference maps have 150 and 916
nonzeros, with seminorm-squared bounds `1500` and `25632/49` in complete
trace-coefficient norm. Use `boundary_axial_edge_lift.py --all-orientations`
with `--degree 4` or `--degree 5` for all twelve ordered tangent/normal
lower/upper choices; translation and positive isotropic scale are exact,
with squared seminorm bounds multiplied by `h³`. The construction retains the
full source image and corrects vertex order according to permutation parity
and boundary side. Intersections of boundary planes, the full census, and
global assembly remain separate work.

## Boundary crease-edge classes

[The box-edge constructor and derivation](BOUNDARY_CREASE_EDGE_LIFT.md)
characterize the two source stars where two coordinate Dirichlet faces meet.
The same-side two-cell star admits all four quartic or six quintic complete
interior trace coordinates; its protected zero-mean maps have 78 and 524
nonzeros, with squared-seminorm bounds `1440` and `23328/49`.
The mixed-side one-cell star forces every source trace coefficient to zero,
and the output is the zero lift. This follows from its actual source rows.
Use `boundary_crease_edge_lift.py --all-edges` with `--degree 4` or
`--degree 5` for twelve tangent-axis and two-face-side choices. The batch
accepts separate `--same-trace` and `--mixed-trace` vectors, preserving
the different source dimensions. Exact coordinate transport preserves the
source images, all protected edge and endpoint traces, zero cell means,
and zero patch-boundary velocity; squared-seminorm bounds scale by `h³`.
These finite edge classes are complemented by the boundary-vertex construction below; global assembly remains.

## Interior-vertex lift

[The interior-vertex constructor and derivation](INTERIOR_VERTEX_LIFT.md)
characterize the complete 24-cell vertex source image on an eight-cube patch:
18 independent values and six explicit compatibility relations. Both degrees
match every compatible tuple while setting all other vertex divergence,
all edge-interior divergence coefficients, all 48 cell means and the entire
outer velocity trace to zero. The construction combines an explicit
first-derivative inverse with the existing fourteen incident-edge lifts and
retained grid mean repair.

Use `interior_vertex_lift.py --degree 4` or `--degree 5`, optionally with
`--trace` for the complete 24-coordinate tuple or `--free-trace` for its
18 independent values. Exact `--vertex` and positive `--scale` place the
patch around a physical central vertex. The maps have 1,319 and 4,977
nonzero entries; conservative reference squared-seminorm bounds are `30080`
and `700416/49` in complete compatible vertex-trace norm, multiplied by
`scale³` after transport. Boundary-vertex operators are described below;
global assembly and the theorem remain separate.

## Boundary-vertex lifts

[The Dirichlet boundary-vertex constructor and derivation](BOUNDARY_VERTEX_LIFT.md)
complete the local vertex classes on the displayed Kuhn box patches.
Face vertices have an eight-dimensional source image, same-side creases
have dimension five, and same-side corners have dimension three.
Mixed-side creases and corners force the complete vertex tuple to zero.
The explicit inverses compose existing edge lifts and retained grid mean
repair, preserving the central targets while clearing every other vertex,
all edge-interior divergence and all 24 or 12 cell means.

Run `boundary_vertex_lift.py --degree 4 --all-orientations` or degree 5
for all 26 lower/upper coordinate boundary orientations. A single
`--orientation` accepts complete or independent trace data. Rational
`--vertex` and positive `--scale` give the physical placement; the
returned cells show the four-cube face or two-cube crease/corner patch.
The guide records the exact source relations, sparse maps, sign/permutation
relabelling and conservative local bounds. The corner construction uses
an explicit two-cube extension. Global compatibility/assembly and the
mesh-uniform theorem remain open.

## Element-bubble residual lift

[The element-local constructor and derivation](CELL_BUBBLE_LIFT.md)
invert the complete mean-zero pressure residual after its vertex and edge
coefficients vanish. Degree four has three independent pressure values;
degree five has twelve. The returned velocity vanishes on every tetrahedron
face, so its zero extension preserves neighboring elements. The explicit
formulas cover all six positive Kuhn shapes without another mean solve.

Run `cell_bubble_lift.py --degree 4 --all-cells` or degree five.
A single `--cell` accepts a complete native-order pressure array or its
independent coordinates. Rational translation and positive scaling are
exact. The output reconstructs every pressure row and includes its exact
pressure Gram matrix and a scale-independent local bound. The guide
records the coefficient conventions and residual-subspace scope.
Complete global assembly and the uniform inf-sup theorem remain separate.

## Minimum-energy cell-mean lift

[The exact constructor and uniform-bound derivation](MEAN_ENERGY_LIFT.md)
supply the initial mean stage on every positive n-by-n-by-n grid.
The field minimizes H1 energy in the full continuous P1 vector plus
normal cubic face-bubble space while matching every prescribed zero-sum
cell mean. Its bound is independent of mesh size by comparison with a
bounded continuous right inverse, a boundary-preserving interpolant and
local face flux corrections.

Run `mean_energy_lift.py --subdivisions 2 --both-degrees` to solve once
and embed that same cubic field in degrees four and five. The exact
two-by-two-by-two solve has 28 free coordinates after eliminating
47 independent mean constraints. Output includes every physical pressure
coefficient, sparse shared velocity coefficients and independently
integrated energy. The API can reuse its geometry and factorization.
Rational translation and positive cube size are supported, including n=1.
This mean stage may change vertex and edge divergence and precedes their
protected lifts. The current dense reduced solver is intended for small
exact grids; complete global assembly remains separate.

## Original problem

On a Freudenthal tetrahedral mesh of a cubical domain, let `V_h^k` be the continuous vector degree-k polynomial space with zero boundary trace, and let `Q_h^k = div V_h^k`.

The sponsor's original question asks for an inf-sup constant independent of mesh size for every fixed `k ≥ 4`; Zhang established the higher-degree `k ≥ 6` case. The September 2026 Alfyorov preprint proposes a proof for the two lower degrees. Its complete argument and sponsor disposition are not certified here.

Sponsor and original research sources:
- https://people.cs.uchicago.edu/~ridg/prizes/kuhnprize.pdf
- https://people.cs.uchicago.edu/~ridg/prizes/prizes.html
- Farrell–Mitchell–Scott, arXiv:2211.05494
- Alfyorov, Research Square DOI `10.21203/rs.3.rs-10887173/v1`

## Existing results retained

The original `kuhn.py` supplies the six exact positively oriented tetrahedra, with each six-times-volume equal to one. The earlier local divergence calculation covers a single unrestricted polynomial cell and does not encode inter-cell continuity or boundary conditions.

[The earlier Zhang-import audit](verification_alfyorov/ZHANG_IMPORT_AUDIT.md) distinguishes raw edge matching, already available at degree four, from the degree-six element-mean correction used in Zhang's construction. The new two-cube operator supplies a degree-four local mean correction; it does not by itself establish the separate protected edge-star lifting.

The local constructions are now connected by the global planner, executable and mesh-uniform bound linked above. Scientific attribution and sponsor disposition remain separate questions. No prize, payment, or submission is asserted.
