# Exact quartic cell-mean repair on rectangular grids

`p4_grid_mean_repair.py` turns prescribed cell-average divergences into a continuous piecewise-quartic vector field on any rectangular, uniformly spaced Kuhn grid containing at least two cubes. The field has zero boundary trace and zero divergence on every tetrahedral edge. It consumes the existing [two-cube operator](P4_MEAN_REPAIR.md); no new elimination or third-party dependency is needed.

The means must sum to zero. The construction matches **cell means**, not an arbitrary prescribed cubic divergence polynomial. Its bound depends on the number of cubes. Consequently this is not a proof of the mesh-uniform Scott–Vogelius theorem.

## Run or call the solver

Create a JSON input containing `shape` and `cell_means`. Cubes are ordered lexicographically as `(x,y,z)`, with z changing fastest. Each cube contributes the six cells in the unchanged `kuhn.py` order. The full ordered cell geometry is also returned, so consumers need not infer numbering.

The following reproduces the actual 72-cell input, including a translation and scale:

```sh
python - <<'PY'
import json
from fractions import Fraction
from pathlib import Path
Path('/tmp/grid-means.json').write_text(json.dumps({
    'shape': [3, 2, 2],
    'origin': ['-1/3', '2/5', 0],
    'cell_size': '1/2',
    'cell_means': [str(Fraction(2*i-71, 14)) for i in range(72)]
}))
PY
python research/ridgway_freudenthal/p4_grid_mean_repair.py \
  /tmp/grid-means.json --output /tmp/grid-velocity.json
```

The output pathname must be new. Omit `--output` to print JSON. Python 3.10 or later is required. For programmatic use, import `repair` from the module and pass the same input dictionary.

Input contract:

- `shape`: three positive integers, with product at least two.
- `cell_means`: exactly `6 * product(shape)` integers or exact rational strings, summing to zero. JSON floats and booleans are rejected; decimal strings are exact and accepted by `Fraction`.
- `origin`: optional three exact coordinates, default `[0,0,0]`.
- `cell_size`: optional positive exact isotropic scale, default `1`.

Output `nodes_times_four[i]` is four times a reference-grid node. Its physical location is `origin + cell_size * nodes_times_four[i] / 4`. The corresponding `velocity_coefficients[i]` contains its **physical quartic Bernstein coefficients**, not point samples. All omitted nodes have zero coefficients. The vector coefficients have already been multiplied by `cell_size`; do not scale them a second time. `cells_grid_coordinates` records integer reference-grid vertices; apply the same translation and scale without dividing those vertices by four.

Shared faces and edges use the same physical Bernstein node keys, so the sparse output directly represents a continuous field. All output numbers are rational strings, except integer geometry and counts.

## Construction and correctness

Let the grid contain `N` cubes and let `m` denote the `6N` requested means. The existing local operator repairs any zero-sum mean vector on two face-adjacent cubes, with zero boundary trace and zero edge divergence.

**Fix a face-adjacency tree.** The root is `(0,0,0)`. A nonroot cube's parent is obtained by decrementing its first nonzero coordinate. The parent is always lexicographically smaller, so decreasing lexicographic order processes every child before its parent.

**Eliminate one cube.** Initially each cube stores its six requested means. At a nonroot cube `c`, let `r_c` be its current six residual means and let `F_c` be their sum. Apply a local repair prescribing `r_c` on the child and `(-F_c,0,0,0,0,0)` on its parent. Those twelve means sum to zero. Subtracting the constructed field leaves zero residual on the child and adds `F_c` to the parent's first residual entry. All other cubes' means are unchanged.

**Finish the root.** After all nonroot cubes are eliminated, the root's six residuals sum to the original global sum, which is zero. Repair these six values using any adjacent cube with all six neighbor targets zero. The neighbor's already-correct means are preserved. Zero steps are skipped; at most `N` two-cube repairs are used.

**Transport correctly.** For a face normal to axis `j`, permute reference x to `j` and map reference y/z to the other axes. Transform the tetrahedral vertex sets, node coordinates, and vector components together. Match transformed cells by their unordered vertex sets to the canonical global geometry; do not assume that their list indices are unchanged by the permutation. This is why the same operator applies to all three face directions, including the orientation-reversing permutation.

**Assemble by addition.** Each local field vanishes on its patch boundary and extends by zero to the whole grid. Its divergence vanishes on every edge of every cell. Summing the transported Bernstein coefficients therefore preserves continuity, zero exterior trace, and zero edge divergence. The elimination invariant proves that the sum realizes every requested mean.

Conversely, the divergence theorem forces the sum of cell means to be zero, because the grid cells have equal volume and the field has zero exterior trace. Thus the cell-mean image of this edge-zero quartic space is exactly the zero-sum hyperplane, for every supported finite grid.

The implementation checks the assembled output itself: all exterior coefficients, all sixteen edge-supported cubic divergence coefficients per cell, and all cell averages. These checks use the actual combined field, not the list of local repair requests. A nonzero residual raises an error before output publication. Translation and scaling then use the exact affine chain rule: `b_h(x) = h b((x-a)/h)` preserves divergence means.

## Explicit fixed-patch bound

The local derivation supplies the reference-patch bound

```
|b_pair|_H1^2 <= A ||t||_2^2,       A = 2,467,200,
```

for the twelve means `t` used on that pair. At any elimination step, `r_c` consists of the cube's original six means plus the sum of all proper-descendant means in its first entry. Also, `F_c` is the sum of all means in the cube's subtree. Cauchy–Schwarz therefore gives

```
||t||_2 <= (1 + 2 sqrt(6N)) ||m||_2 <= 3 sqrt(6N) ||m||_2.
```

The root correction obeys the same conservative bound. There are at most `N` patches, so the Hilbert-space inequality for their sum yields

```
|b_grid|_H1^2 <= 54 A N^3 ||m||_2^2
              = 133,228,800 N^3 ||m||_2^2.
```

A physical cube size `h` multiplies the right-hand side by `h^3`. This is useful for a patch whose cube count is bounded independently of mesh refinement: its repair bound is then independent of `h` in the appropriately scaled norm. It is **not** a mesh-uniform bound for the whole domain as `N` grows. No optimality of the tree, sparsity, or constant is asserted.

## Use in the protected-edge work

Given a continuous quartic raw local lift `w` with zero boundary trace on a supported rectangular patch, compute its cell-mean divergences `m`. They sum to zero. Let `b_grid` be this solver's correction. Then `w - b_grid` has zero mean divergence on every cell and exactly the same edge divergence as `w`.

This provides an implementable mean-preserving correction for a future raw edge-star map, including a bound on every fixed-size patch. The missing work is still to supply the actual raw map and prove that its source relations cover the intended global divergence image; this solver does not invent those relations or certify the complete edge-star catalogue.

## Execution scope

One actual end-to-end run used the 3×2×2 input above. It produced 72 tetrahedra, 218 nonzero shared nodes, and twelve pair repairs: nine in x, two in y, one in z. All 1,152 edge coefficients and 72 means had exact zero residual. Python 3.13.5 completed in 0.84 seconds with exit code 0. The checked reference field was then exactly translated/scaled as described above.

This was the specifically justified additional run for the new transport and assembly path. The completed two-cube construction was not rerun. No new test files, test suite, workflow, dependency, or benchmark bundle was added. The runnable solver is the deliverable; the example output is not checked into the repository.

The unchanged geometry, existing local basis, and earlier Zhang-import audit retain their attribution. Related work: Commons #14999 and the local operator in #19247. No prize, sponsor acceptance, payment, or full-theorem certification is claimed.
