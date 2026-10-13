# Literature delta — what changed the zero-gradient proof plan

This note records the newest results that materially constrain the Scott–Vogelius–Nitsche prize proof. It is not a literature survey.

## 1. The weak-boundary divergence-preserving approximation gap is no longer a blank page

Eickmann, Guzmán, Neilan, Scott and Tscherpel, **A local Fortin projection for the Scott–Vogelius elements on general meshes**, arXiv:2512.18033; Journal of Numerical Mathematics (2026), DOI `10.1515/jnma-2025-0178`, construct a local Fortin projection for Scott–Vogelius degree `k >= 4` on general shape-regular two-dimensional triangulations, including singular vertices. The abstract specifically states that the projection

- preserves divergence in the dual of the pressure space,
- preserves discrete boundary data,
- and satisfies local stability estimates.

That is substantially closer to the prize problem than older strong-zero-trace stability results. It supplies a concrete candidate operator for the `proof_reduction.md` approximation hypothesis.

It does **not** automatically close the prize theorem. The proof owner still has to verify that the boundary-data notion preserved by that projection matches the unconstrained-on-`Gamma_h` Nitsche space and the exact compatibility demanded by the curved-boundary trace used in the prize formulation.

## 2. Exact divergence makes boundary compatibility a real theorem condition

Eickmann, Scott and Tscherpel, **Scott–Vogelius element and iterated penalty method for inhomogeneous Dirichlet boundary conditions**, arXiv:2509.17899 (2025), give quasi-optimal estimates for inhomogeneous Dirichlet Stokes problems and pressure-robust Scott–Vogelius estimates. Their abstract emphasizes that exact divergence requires a compatibility condition on the boundary data and that a modified Fortin operator is used to preserve it.

For the prize problem this matters because the exact solution vanishes on the true curved boundary but its smooth extension has a small, nonzero trace on the polygonal boundary `Gamma_h`. A proof cannot simply call that trace an arbitrary inhomogeneous datum: it must verify the required net-flux/compatibility condition or quantify the correction needed to place it in the divergence-compatible trace class.

This sharpens the conditional reduction:

1. geometry gives `g_h = u^e|Gamma_h = O(h_Gamma^2)`;
2. Nitsche trace scaling gives the `h_Gamma^(3/2)` residual size;
3. but a divergence-preserving Fortin lift must also respect the compatibility condition of `g_h` (or a corrected trace differing by no more than the target order).

## 3. Why this supports a bounded theorem instead of a generic one

The Gjerde–Scott manufactured field has constant pressure and is exactly divergence free. That is materially easier than a completely general mixed Stokes theorem. A publishable first target can therefore be scoped to the sponsor's manufactured/constant-pressure setting, provided the paper says so explicitly and proves that every omitted mixed-boundary term is harmless in that setting.

A broader theorem with variable pressure should instead use a stress-consistent Nitsche boundary form or explicitly bound the difference between the paper's `partial_n u` flux notation and the mixed Stokes traction. The current carrier does not assert that this general-pressure step is done.

## 4. Next theorem-level checks

The shortest route from the current carrier to a credible proof is now:

1. instantiate the 2026 local Fortin projection on the exact `k=4` mesh family and record the weak-boundary trace it preserves;
2. verify/correct the polygonal extension trace to satisfy the divergence-compatible boundary condition, with correction no larger than `O(h_Gamma^2)` in the boundary norm that feeds Nitsche;
3. close local-to-global coercivity with `mu/h_e`, or state and prove the required `mu_global >= C (h_Omega/h_Gamma)` rule if the denominator is global;
4. prove the manufactured constant-pressure consistency residual, including the symmetric-gradient/normal-derivative relation on `Gamma_h`;
5. only then widen to variable pressure / full traction.

Until those checks are discharged, the new Fortin literature upgrades the proof route from speculative to concrete but does not upgrade `PARTIAL_RIGOROUS` to `PROOF_COMPLETE`.
