# Protected interior face-diagonal lifts in degrees four and five

`face_diagonal_lift.py` constructs a continuous piecewise-polynomial velocity on
the two-cube patch `[0,2] × [0,1]²`, targeting the diagonal from `(1,0,0)` to
`(1,1,1)` of the shared cube face. It reproduces every compatible endpoint-zero
edge divergence trace, keeps all other edges and both target endpoints at zero,
has zero patch boundary trace, and has zero divergence mean on every tetrahedron.

Unlike the body-diagonal class, arbitrary independent traces on the four incident
tetrahedra are not possible. For each interior Bernstein mode the exact relation is

```
y_1 - y_2 - y_3 + y_4 = 0.
```

The implementation reconstructs that relation from unrestricted continuous source
coefficients before constructing an operator on its kernel. This resolves one
singular interior face-diagonal geometry in both degrees under #14999; other edge
classes/orientations, the complete census and the global theorem remain open.

## Run or reuse

```sh
python research/ridgway_freudenthal/face_diagonal_lift.py --degree 4 \
  --trace 1 1 1 1 1 1 1 1 --output /tmp/quartic-face-lift.json
python research/ridgway_freudenthal/face_diagonal_lift.py --degree 5 \
  --trace 1 1 1 1 1 1 1 1 1 1 1 1 --output /tmp/quintic-face-lift.json
```

Python 3.10+, standard library. Use new output paths. Without `--trace`, the CLI
returns the reusable operator. In process, cache `construct(degree)` and call
`apply(operator, trace)` for each requested trace. Inputs are exact integers or
rational strings. Incompatible traces raise `ValueError`; the CLI exits nonzero
before writing output, with the exact mode and residual.

Targets are cell-major for incident cells **0, 1, 9, 11** in the unchanged two-cube
Kuhn ordering. Within each cell, the high-endpoint powers are `1,2` for degree four
and `1,2,3` for degree five. These are degree-`k-1` Bernstein **coefficients**, not
point values. The output records every cell and barycentric index explicitly.

There are eight input coordinates with six free coordinates at degree four, and
twelve input coordinates with nine free coordinates at degree five. The first
three cells supply the free coordinates; the fourth is determined by the relation.
`source_basis` embeds those free coordinates into the complete target vector.
The sparse velocity `basis` acts on the free coordinates, not on the full input.
`free_coordinate_indices` specifies their positions for consumers.

`nodes_times_degree` contains reference Bernstein node coordinates multiplied by
the velocity degree. Divide by that degree for geometric locations. Vector values
are Bernstein coefficients; boundary coefficients are omitted and equal zero.

## Actual source-space characterization

Let `S` map continuous degree-`k` vector coefficients on the four-tetrahedron source
star to the target edge's interior divergence coefficients. All coefficients are
included, including those on the star's outer boundary. The source therefore
contains every possible restriction of a global continuous velocity field.

The program reconstructs `S` from physical node sharing and the exact formula

```
d[K,beta] = k * sum_i grad(lambda_i) · v[beta+e_i].
```

For each mode it checks over the integers that the signed sum of all four source
rows is zero. If `H` contains these checkerboard relations, then **`H S = 0`** on
the full unrestricted continuous star. Endpoint-zero and physical Dirichlet
restrictions cannot invalidate this necessary relation. No floating-point null
mode or assumed discontinuous-pressure source space enters this calculation.

Conversely, write the first three cell traces as `z`. The explicit matrix `B`
copies them and sets each fourth-cell coefficient to `-z_1+z_2+z_3`; thus
`range B = ker H`. Let `P` be all protected divergence-edge rows of a continuous
patch-boundary-zero velocity and `T` the target rows. Exact rational elimination
constructs `R` with

```
P R = 0,                T R = B.
```

Each returned column is a genuine finite-element field, so every vector in
`ker H` is realized by a source velocity as well as by a protected output.
Together with `H S=0`, this proves that the source image is **exactly** `ker H`;
no unrecorded compatibility relation remains for this fixed geometry.

The raw means are then removed by the existing quartic two-cube mean operator.
For degree five, the existing exact degree-elevation routine represents that same
quartic correction as a quintic. All correction edge traces remain zero.
The final combined field is checked on every edge coefficient and cell mean.

| Quantity | Degree four | Degree five |
|---|---:|---:|
| Full source-star vector coefficients | 255 | 438 |
| Target coordinates / admissible dimension | 8 / 6 | 12 / 9 |
| Protected rows / rank | 184 / 116 | 252 / 166 |
| Combined protected+target rank | 122 | 175 |
| Final operator shape | 189 × 6 | 432 × 9 |
| Nonzero final coefficients | 34 | 174 |
| Checked final edge rows | 192 | 264 |
| Checked zero-mean rows | 12 | 12 |

These identities establish one local singular class, not the full finite catalogue.
The two cubes and face orientation are fixed. No general patch selection or global
assembly algorithm is implemented by this command.

## Bound and execution

The maximum squared row norms of the final coefficient matrices are `1/4` and
`7/25`, respectively. The Bernstein/Jensen/Cauchy–Schwarz argument in
[the body-diagonal derivation](P4_BODY_DIAGONAL_LIFT.md) gives

```
|L_4 y|_H1² <= 576 ||y||_2²,
|L_5 y|_H1² <= 1008 ||y||_2².
```

Here `y` is the complete compatible trace vector: extracting its first three
cell blocks does not increase its Euclidean norm. These are conservative
reference-patch bounds in trace-coefficient norm, not optimized pressure-L2
constants. Translation and isotropic scaling `v_h(x)=h L y((x-a)/h)` preserve
divergence traces and multiply the squared seminorm bound by `h³`.

Both commands above ran on Python 3.12.14/Linux with exit 0. Each constructor
checked all final identities on every free target column. An actual incompatible
quartic input `[1,0,0,0,0,0,0,0]` exited 1 with checkerboard mode-one residual 1.
The shared solver's original body-diagonal CLI outputs remained byte-identical.
No new test suite, fixtures, workflow or external dependency was introduced.

Existing Kuhn geometry, local mean repair, degree elevation and protected-map
solver are reused with their attribution. Background singular-edge formulation:
Alfyorov, September 2, 2026, sections 3–4/Table 1,
https://doi.org/10.21203/rs.3.rs-10887173/v1. The source relation and operators here
are reconstructed independently, not copied from that certificate package. No
full-theorem certification, sponsor contact or prize/payment claim follows.
