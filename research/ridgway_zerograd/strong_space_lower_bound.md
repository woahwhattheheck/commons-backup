# Quantified strong-boundary obstruction: an `H1 >= C h_Gamma^(1/2)` lower bound

Status: **rigorous partial result under stated mesh hypotheses; not a Zero Gradient Prize proof.**

This note complements `proof_reduction.md`. That file explains why the corrected weak-boundary/Nitsche formulation can produce an `O(h_Gamma^(3/2))` geometry residual, conditional on the remaining Scott–Vogelius stability and consistency lemmas. Here the opposite side is made quantitative: the **strongly imposed** exactly-divergence-free space has a local first-jet defect that, under a standard boundary-mesh counting hypothesis, forces a global `H1` best-approximation lower bound of order `h_Gamma^(1/2)`.

Nothing below proves the desired Nitsche upper bound. It proves why the strong method cannot generally have that bound on the two-triangle boundary-star meshes identified in the sponsor problem.

## 1. Exact two-triangle first-jet theorem

Let `z` be a boundary vertex of a conforming planar triangulation at which exactly two triangles `K1,K2` meet. Let

- `t1` be a nonzero tangent vector of the boundary edge of `K1` issuing from `z`,
- `t2` be the corresponding boundary-edge tangent of `K2`, and
- `s` be a tangent vector of the common interior edge `K1 intersect K2` issuing from `z`.

Assume the three edge directions are pairwise nonparallel. Let `v_h` be continuous across the common edge, polynomial on each triangle, exactly divergence-free on each triangle, and strongly zero on both boundary edges. Define one-sided first jets

`A_i = grad(v_h|K_i)(z)`, `i=1,2`.

### Theorem 1

Under these assumptions,

`A_1 = A_2 = 0`.

### Proof

Strong zero trace on each boundary edge gives the tangential derivative conditions

`A_1 t1 = 0`, `A_2 t2 = 0`.

Continuity of the polynomial traces on the common interior edge gives equality of tangential derivatives there:

`A_1 s = A_2 s`.

Exact elementwise incompressibility gives

`tr(A_1)=tr(A_2)=0`.

Write

`A_1=[[a,b],[c,d]]`, `A_2=[[e,f],[g,h]]`,
`t1=(u,v)`, `t2=(p,q)`, `s=(r,w)`.

These are eight homogeneous scalar equations for the eight jet entries. With the row ordering implemented by `jet_obstruction.py`, direct exact elimination gives

`det M = cross(t2,s) cross(t2,t1) cross(s,t1)`.

Every factor is nonzero precisely when the three directions are pairwise nonparallel. Hence `M` is invertible and its only null vector is the zero jet. QED.

The executable certificate checks the identity with rational arithmetic on several non-axis-aligned stars. It also contains a deliberately degenerate case with `s` parallel to `t1`; the determinant vanishes and full rank is correctly lost.

### Weak-boundary comparison

If the strong trace equations `A_1 t1=0` and `A_2 t2=0` are removed, only the two trace-free equations and the two continuity-vector equations remain. For `s != 0` this system has rank four, leaving a four-dimensional first-jet space. In particular every common traceless jet `A_1=A_2=A`, `tr A=0`, survives at this local algebraic level.

Thus weak boundary imposition removes a specific four-scalar local constraint; it does not merely perturb a constant in the strong space.

## 2. The sponsor manufactured solution has nonzero boundary gradient everywhere

For

`u(x,y) = (1 - 1/(x^2+y^2)) (-y,x)`,

on the unit circle `x^2+y^2=1`, direct differentiation gives

```
grad u = [[-2xy, -2y^2],
          [ 2x^2,  2xy]].
```

Therefore

`tr(grad u)=0`

and

`|grad u|_F^2 = 4(x^2+y^2)^2 = 4`,

so `|grad u|_F=2` at every point of the circular boundary. `jet_obstruction.py` checks the identity exactly at rational unit-circle points including `(3/5,4/5)`.

## 3. Conditional global `H1` lower bound

Let a positive-length curved boundary arc be approximated by a shape-regular, quasi-uniform polygonal boundary mesh of size `h_Gamma`. Assume there is a set `B_h` of **pairwise distinct boundary triangles** such that:

1. `#B_h >= c_B / h_Gamma`;
2. each `K in B_h` contains a boundary vertex `z_K` satisfying Theorem 1;
3. `diam(K) ~= h_Gamma` with a uniform shape-regularity constant;
4. the finite-element degree `k` is fixed as `h_Gamma -> 0`;
5. `u in W^{2,infinity}` in a fixed neighborhood of the boundary arc; and
6. `|grad u(z_K)|_F >= g_0 > 0`.

Let `P_K` be the first-order Taylor polynomial of `u` at `z_K`. For any strongly constrained exactly-divergence-free discrete velocity `v_h`, Theorem 1 gives `grad v_h(z_K)=0`. Hence

`q_K := grad(P_K-v_h)`

is a fixed-degree polynomial matrix on `K` with

`|q_K(z_K)|_F = |grad u(z_K)|_F >= g_0`.

By finite-dimensional norm equivalence after mapping `K` to a shape-regular reference triangle, there is `c_inv>0`, depending only on degree and shape regularity, such that

`||q_K||_{L2(K)} >= c_inv h_Gamma |q_K(z_K)|_F >= c_inv g_0 h_Gamma`.

Taylor's theorem gives

`||grad(u-P_K)||_{L2(K)} <= C_u h_Gamma^2`.

Therefore, for sufficiently small `h_Gamma`,

`||grad(u-v_h)||_{L2(K)} >= c_* h_Gamma`

with `c_*>0` independent of `h_Gamma`. Summing squares over the distinct cells in `B_h`,

```
|u-v_h|_{H1}^2
  >= sum_{K in B_h} ||grad(u-v_h)||_{L2(K)}^2
  >= (#B_h) c_*^2 h_Gamma^2
  >= c_B c_*^2 h_Gamma.
```

Thus

`|u-v_h|_{H1} >= C h_Gamma^(1/2)`.

### Corollary for the manufactured cylinder field

For the sponsor field, `g_0=2` on the unit circle. Under the six mesh/regularity hypotheses above, no fixed-degree strongly imposed exactly-divergence-free approximation in this two-triangle-star family can converge in the `H1` seminorm faster than order `h_Gamma^(1/2)`, regardless of how small the interior scale `h_Omega` is made.

This is a **best-approximation obstruction**, not just an observed method error rate.

## 4. Relation to the existing Nitsche proof reduction

The two results are intentionally asymmetric and compatible:

- this note proves an `Omega(h_Gamma^(1/2))` lower bound for the **strong-boundary space**, under explicit mesh hypotheses;
- `proof_reduction.md` derives an `O(h_Gamma^(3/2))` **conditional Nitsche geometry residual** after the strong trace is removed.

The local rank calculation proves that Nitsche clears a necessary algebraic obstruction. It does **not** prove the remaining ingredients in `proof_reduction.md`: mesh-uniform coercivity, the exact mixed traction/pressure consistency, a divergence-preserving weak-boundary Scott–Vogelius approximation/Fortin result, inf-sup/pressure recovery, domain-extension estimates, or the sponsor-requested full PDE penalty sweep.

## 5. Evidence ceiling

**Proved here:**

- exact generic determinant formula for the two-triangle first-jet constraint matrix;
- strong-space first-jet nullity zero for nondegenerate stars;
- weak-boundary first-jet nullity four;
- exact boundary gradient norm `2` for the sponsor manufactured velocity;
- conditional global strong-space `H1 >= C h_Gamma^(1/2)` best-approximation lower bound.

**Not proved here:**

- the full Scott–Vogelius–Nitsche `O(h_Gamma^(3/2)+h_Omega^k)` theorem;
- any particular global Nitsche penalty threshold;
- prize eligibility, sponsor acceptance, publication, award, receivable, payment, or revenue.
