# A constructive two-cube quartic mean-repair operator

The implementation in `p4_mean_repair.py` constructs a continuous piecewise-quartic vector field on `[0,2] × [0,1]²`, with zero boundary trace, zero divergence on every tetrahedral edge, and any prescribed twelve cell-average divergences whose sum is zero. `p4_mean_repair_basis.json` is the resulting sparse rational operator, not an execution receipt.

This closes the local two-cube item left unresolved in the [earlier Zhang-import audit](verification_alfyorov/ZHANG_IMPORT_AUDIT.md). It does **not** certify the protected edge-star maps, the complete 37/117 catalogue, the full mesh-uniform theorem, or any prize entitlement.

## Use the actual operator

From the repository root, with Python 3.10 or later and no third-party dependencies:

```sh
python research/ridgway_freudenthal/p4_mean_repair.py \
  --means 1 0 0 0 0 0 0 0 0 0 0 -1 \
  --output /tmp/p4-repair.json
```

The output must be a new pathname. Omit `--output` to print JSON. Supply integers or exact rational strings, including quoted fractions. The twelve means must sum to zero. The output contains the tetrahedra, physical nodes multiplied by four, sparse operator, and three velocity Bernstein coefficients per node. These are **not nodal point values**. Boundary coefficients are zero and omitted.

For repeated application, load `p4_mean_repair_basis.json` and call `apply(operator, means)` from `p4_mean_repair.py`; construction need not be repeated. The JSON's `basis` triples are `[row, column, rational_value]`. Row `3*i+c` is component `c` at `nodes_times_four[i]/4`. Column `j` realizes `e_j-e_11`, with zero-based cell numbering. For a zero-sum mean vector `m`, multiply column `j` by `m[j]`, for `j=0,…,10`.

The actual construction and the command above completed once in Python 3.13.5: exit 0, 0.93 seconds, with `CONSTRUCTED: 189 unknowns, 192 edge rows`. No test suite or optimized-mode rerun was used.

## Geometry and exact finite system

The existing `kuhn.py` generator is retained unchanged. It supplies positively oriented tetrahedra for the six coordinate permutations. Translate these by `(0,0,0)` and `(1,0,0)` to obtain twelve cells. Their complete order is recorded in the operator JSON. Relative to the preprint's cell sets, each cube is ordered `K1,K3,K2,K4,K5,K6`; local vertex order is chosen for positive determinant.

For each cell `K` and degree-four barycentric multi-index `α`, its physical Bernstein node is `p=(Σ_i α_i v_i)/4`. Identify equal nodes across shared faces and set every boundary coefficient to zero. The interior nodes are the 63 lattice points `(i,j,l)/4` with `1≤i≤7`, `1≤j,l≤3`, giving 189 scalar velocity coefficients. Shared-face Bernstein bases agree under vertex permutation, so this is the full continuous zero-boundary quartic space, not a discontinuous surrogate.

Write the field on a cell as `b=Σ_|α|=4 c_α B⁴_α`. For `|β|=3`, the cubic Bernstein coefficient of its divergence is

```
(div b)_β = 4 Σ_i ∇λ_i · c_(β+e_i).
```

The code reconstructs each `∇λ_i` by integer cross products; all tetrahedra have determinant +1. No matrices or coefficient lists from the external author's package are imported.

Define `E` using the expression on the right **without** its factor 4, for every `β` supported on at most two vertices. There are four vertex coefficients plus two interior coefficients for each of six edges: 16 rows per cell, 192 total. Their vanishing is equivalent to zero divergence polynomial on every cell edge, including endpoints.

Define `S` by summing the same factor-4-removed expression over all twenty degree-three multi-indices on each cell. Each cubic Bernstein polynomial has cell average `1/20`, so the actual twelve mean values are `S c / 5`.

## Constructed result and local proof

Sparse elimination over rational numbers gives:

| Quantity | Exact value |
|---|---:|
| Velocity unknowns | 189 |
| `rank(E)` | 122 |
| `rank([E;S])` | 133 |
| Dimension of the edge-zero velocity space | 67 |
| Dimension also having zero cell means | 56 |
| Mean-image dimension | 11 |
| Nonzero coefficients in the constructed `189 × 11` operator `C` | 202 |

The calculation constructs all eleven columns together, then checks, entry by entry, the identities

```
E C = 0,
S C = 5 [e_0-e_11, …, e_10-e_11].
```

Consequently `c=C(m_0,…,m_10)ᵀ` realizes every zero-sum mean vector and has zero edge divergence. Conversely every represented field has zero boundary trace. The divergence theorem, and the equal volume `1/6` of all twelve cells, imply that its cell means sum to zero. Thus the image is **exactly** the eleven-dimensional zero-sum hyperplane.

This is a new reconstruction and a valid alternative witness, not a byte-for-byte replay of the external paper's 208-entry witness. Its 202 nonzeros do not establish a performance or sparsity optimum. Row/cell ordering and the chosen free variables differ.

## An explicit, conservative norm bound

The stored basis has `||C||_F² = 6425/3`. For a Kuhn tetrahedron, each coordinate derivative has two nonzero barycentric gradient entries, of magnitude one and opposite sign. Positivity and partition of unity of the cubic Bernstein basis imply that each scalar derivative of `b` is bounded pointwise by `8||c||₂`. Summing the nine squared derivatives and integrating over patch volume two gives

```
|b|²_H¹ ≤ 1152 ||c||₂²
         ≤ 1152 ||C||_F² ||m||₂²
         = 2,467,200 ||m||₂².
```

This deliberately loose bound requires no floating-point eigenvalues or claimed external norm certificate. In particular, it supplies a bounded linear right inverse on the reference patch.

On a translated/scaled patch, set `b_h(x)=h b((x-a)/h)`. Divergence means are unchanged and the squared H¹ seminorm gains `h³`. Coordinate permutations transport the tetrahedral set and velocity components together, so the same construction applies to a pair sharing a face normal to either of the other axes, after consistently permuting the recorded cell order. These are mathematical transport statements; the current CLI emits the reference x-adjacent pair only.

## Research boundary and next useful implementation

The local mean-repair assertion in Alfyorov's Lemma 7.1 now has an independent constructive realization. Its fixed-size scaling also supplies the local ingredient for a bounded-patch repair. This does not verify the preprint's 74 protected raw edge maps or their compatibility with the actual global divergence image. A useful next implementation is to consume one of those maps from exact geometry and compose its output with this mean repair; another summary of Zhang's already-audited stages would not close that remaining gap.

Sources and attribution:

- David Alfyorov, *Uniform inf-sup stability of quartic and quintic Scott-Vogelius elements on Freudenthal meshes: a protected raw edge-star lifting*, Research Square v1, posted September 2, 2026, DOI `10.21203/rs.3.rs-10887173/v1`, Lemma 7.1 / equation (19), manuscript page 8. The preprint is the target statement, not the source of our coefficients.
- The existing Commons `kuhn.py` and earlier Zhang-import audit retain their authorship. The reconstructed copy of `kuhn.py` used here matches existing Git blob `d977af1865b03f9af0ff0262d19fc6deadcc09e6`.
- Shangyou Zhang, *Divergence-free finite elements on tetrahedral grids for k ≥ 6*, Mathematics of Computation 80 (2011), 669–695, DOI `10.1090/S0025-5718-2010-02412-3`, remains the cited source for the earlier analytic stages. They were not rerun or re-audited here.

No sponsor/author contact, submission, award, payment, or full-theorem certification follows from this delivery. Work item: Commons #14999; operation `yz-alder731-freudenthal-p4-mean-repair-20260923`.
