# A mean-preserving quartic body-diagonal edge lift

`p4_body_diagonal_lift.py` constructs a usable local operator for the body diagonal
from `(0,0,0)` to `(1,1,1)`. For **any twelve** interior cubic Bernstein trace
coefficients, it returns a continuous piecewise-quartic vector field on
`[0,2] × [0,1] × [0,1]` that reproduces those coefficients, vanishes on the patch
boundary, has zero divergence on every other tetrahedral edge (and at the target
endpoints), and has zero divergence mean on every tetrahedron.

This resolves one degree-four local class in #14999. It is not the other edge
classes, the degree-five catalogue, a global assembly, or the mesh-uniform theorem.
There is no prize, publication acceptance, sponsor contact, or payment assertion.

## Use the operator

Python 3.10+, standard library only, from the repository root:

```sh
python research/ridgway_freudenthal/p4_body_diagonal_lift.py \
  --trace 1 -1 2 -2 3 -3 4 -4 5 -5 6 -6 \
  --output /tmp/body-diagonal-velocity.json
```

Choose a new output path. Omit `--output` to print JSON; omit `--trace` to obtain
the reusable exact operator alone. For in-process use, call `construct()` once,
then `apply(operator, trace)` for successive right-hand sides. Values are integers
or exact rational strings; floating-point JSON numbers and booleans are not inputs
to `apply`.

The twelve trace values are ordered by the six tetrahedra from the unchanged
`kuhn.py`, then by high-endpoint barycentric power `j=1,2`. On each cell they are
the coefficients of the cubic Bernstein modes with endpoint powers `(3-j,j)`.
The returned `target_coordinates` includes each exact cell/barycentric index;
these values are **coefficients, not samples at two points**.

`nodes_times_four` gives shared reference Bernstein-node coordinates. The
corresponding `velocity_coefficients` are vector quartic Bernstein coefficients,
not nodal point values. Boundary nodes are omitted and carry zero coefficients.
`basis` stores triples `[row, target_column, rational_value]`; rows run through
node coordinates with x/y/z vector components consecutively. All twelve target
columns are built and checked over rational arithmetic before output publication.

## Geometry-to-function argument

For degree four, the scalar coefficient attached to a tetrahedral multi-index
`alpha` has geometric key `sum_i alpha_i a_i`, four times its Bernstein node.
Sharing keys across incident tetrahedra identifies the entire Bernstein trace on
their shared faces. It therefore gives a continuous finite-element field.
Removing nodes on the cube boundary sets every boundary-face coefficient to zero.

There are 27 interior scalar nodes and 81 vector unknowns on the first cube.
With cubic `beta`, the divergence coefficient is

```
d[K,beta] = 4 * sum_i grad(lambda_i) · v[beta + e_i].
```

The code reconstructs this formula directly from the six exact tetrahedra and
their barycentric gradients. A cubic polynomial's restriction to an edge consists
exactly of its Bernstein coefficients supported on that edge's endpoint pair.
Thus the 84 non-target rows include all other edge coefficients and both target
endpoints. The remaining twelve rows are the target coordinates.

Let these matrices be `P` and `T`. Exact row elimination gives rank `P=42` and
rank `[P;T]=54`, and constructs an 81×12 rational matrix `R` satisfying

```
P R = 0,                 T R = I_12.
```

The implementation checks these identities on every column, rather than treating
a floating-point rank as evidence of surjectivity. The columns represent actual
continuous zero-boundary quartics, so `w=Ry` is the raw protected lift for every
`y ∈ R^12`. This also establishes source compatibility for this class: there is no
missing relation to assume on the twelve coordinates. Any endpoint-zero trace
arising from a global quartic divergence is a vector in this same full space.
Additional physical boundary constraints on the original source only restrict its
possible vectors; the output already vanishes on every cube boundary face.

## Preserve all cell means

Extend `w` by zero to the adjacent cube `[1,2] × [0,1]²`. Its cell means `m_K` sum
to zero by the divergence theorem and equal tetrahedral volumes. The unchanged
`p4_mean_repair.py` operator supplies a continuous patch-boundary-zero correction
`b` having those means and zero divergence on every edge. Therefore

```
L y = w - b
```

has the prescribed target, all protected edge traces, and zero mean on every
cell. The code assembles the actual combined coefficient matrix and checks all
192 edge rows and all twelve mean rows for each of its twelve columns. It returns
an 189×12 matrix with 270 nonzero rational entries. No stored external certificate
is trusted or required; the existing local mean-repair implementation is reused.

The construction fixes the neighbor in positive x. Its two-cube patch must fit in
the domain. Selecting or transporting a different neighbor is not an implemented
interface here. The raw one-cube result itself has zero cube-boundary trace.

## Explicit bound and scale

For the returned combined matrix, the largest squared Euclidean row norm is
`M = 3/4`. Hence each scalar velocity coefficient has absolute value at most
`sqrt(M) ||y||_2`. Cubic Bernstein basis functions are nonnegative and sum to one.
On every unit Kuhn tetrahedron, `sum_i |grad(lambda_i)|² = 6`. Jensen's inequality
and Cauchy–Schwarz applied to the derivative formula give, for each scalar vector
component,

```
|grad(v_component)|² <= 4² * 6 * 4 M ||y||_2².
```

Sum three components and integrate over patch volume two:

```
|L y|_H1² <= 2 * 3 * 16 * 6 * 4 M ||y||_2² = 1728 ||y||_2².
```

This is a conservative reference-patch seminorm bound in **trace coefficient
norm**, not the manuscript's optimized pressure-L2 constant. For an isotropically
scaled translated patch, set `v_h(x)=h L y((x-a)/h)`: divergence traces are unchanged
and both the bound and volume scale by `h³`. A pressure-L2 estimate can then use
the bounded coefficient-extraction functional on the fixed cubic reference space;
its numerical constant is not calculated here. This local scaling statement does
not supply the other edge classes or a global inf-sup theorem.

## Sources and actual execution

The construction consumes the existing Kuhn geometry and ALDER-731's two-cube
mean-repair operator without changing either. The earlier source audit remains
unchanged. The target/protection formulation and body-diagonal class are described
in Alfyorov's September 2, 2026 preprint, sections 3–4 and Table 1:
https://doi.org/10.21203/rs.3.rs-10887173/v1

This is an independently reconstructed operator, not a replay of that author's
certificate package or endorsement of the complete manuscript.

The CLI command above ran on Python 3.12.14/Linux with exit 0 and returned
`CONSTRUCTED: target dimension 12, 189 unknowns, 270 nonzero coefficients`.
All algebraic output identities are checked within construction. No new test
framework, fixtures, workflow, benchmark campaign or third-party dependency was
added; the runnable lift is the deliverable.
