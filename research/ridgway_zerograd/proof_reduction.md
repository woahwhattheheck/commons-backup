# Proof reduction: where the `h_Gamma^(3/2)` term comes from

Status: **rigorous reduction under stated assumptions; not a complete Scott–Vogelius prize proof.**

This note isolates the curved-boundary consistency mechanism from the mixed Scott–Vogelius stability problem. The purpose is to make the remaining theorem small enough that a reviewer can attack the actual missing lemmas rather than re-derive the geometry term.

## 1. Geometry and corrected weak-boundary space

Let `Omega` be a smooth two-dimensional domain with a smooth no-slip component `Gamma`. Let `Omega_h` be a polygonal approximation whose vertices on the curved component lie on `Gamma`, with polygonal component `Gamma_h`. Write `h_Gamma` for the largest boundary-edge scale and `h_Omega` for the interior mesh scale.

Assume a closest-point map `pi: Gamma_h -> Gamma` exists and

- `||x-pi(x)||_{L_inf(Gamma_h)} <= C_geo h_Gamma^2`,
- the mesh family is shape regular at boundary elements.

For degree `k >= 2`, the Nitsche velocity space intended by the numerical experiment must be a space of continuous piecewise `[P_k]^2` functions **not constrained to vanish on `Gamma_h`**. Strong conditions may remain on unrelated polygonal outer-boundary pieces. Denote this corrected space by `X_h` and its exactly divergence-free kernel by

`Z_h = {v_h in X_h : div v_h = 0}`.

This definition is intentionally distinct from the preprint's earlier `V_h` symbol, which is stated there with zero trace on `Gamma_h`. Reusing that strongly constrained space in a Nitsche theorem would make the curved-boundary Nitsche terms identically zero.

## 2. Nitsche energy and coercivity gate

For the velocity-only kernel discussion, consider the symmetric paper-style form on `Gamma_h`

`A_h(w,v) = 1/2 (D w, D v)_Omega_h
              - <partial_nh w, v>_Gamma_h
              - <w, partial_nh v>_Gamma_h
              + <mu h_e^{-1} w, v>_Gamma_h`,

with a local boundary scale `h_e` on each boundary edge. A stress-consistent mixed Stokes theorem must separately settle the pressure/traction term; see Section 6.

A standard sufficient coercivity route is the discrete inverse-trace/Korn bound

`|| h_e^(1/2) partial_nh v_h ||_Gamma_h <= C_T ||D v_h||_Omega_h`.

Then

`A_h(v_h,v_h) >= 1/2 X^2 - 2 C_T X Y + mu Y^2`,

where `X=||D v_h||` and `Y=||h_e^(-1/2)v_h||_Gamma_h`. The two-by-two quadratic is positive definite whenever

`mu > 2 C_T^2`.

Thus a mesh-uniform proof needs a mesh-uniform trace/Korn constant and a penalty scale tied to boundary elements.

### Two-scale warning

If the implementation instead uses `mu/h_Omega` while boundary elements have scale `h_Gamma`, the local penalty coefficient is smaller by approximately `h_Gamma/h_Omega`. A local threshold `mu_* / h_Gamma` becomes the global-parameter condition

`mu_global >= mu_* (h_Omega/h_Gamma)`.

Therefore a theorem allowing `h_Gamma/h_Omega -> 0` cannot keep a fixed global `mu` without additional structure. Either:

1. use `mu/h_e` locally; or
2. assume `h_Omega/h_Gamma` is uniformly bounded; or
3. scale the global dimensionless `mu` with `h_Omega/h_Gamma`.

This is independent of the convergence-order argument and is exactly why a penalty study matters in the sponsor's two-scale statement.

## 3. Boundary mismatch is order `h_Gamma^2`

Let `(u,p)` be a sufficiently smooth exact Stokes solution on `Omega` with homogeneous no-slip data `u=0` on `Gamma`. Extend `u` smoothly to a tubular neighborhood containing `Gamma_h`; call the extension `u^e`.

For `x in Gamma_h`, Taylor expansion along the closest-point segment gives

`u^e(x) = u(pi(x)) + grad u(pi(x)) (x-pi(x)) + O(|x-pi(x)|^2)`.

Since `u(pi(x))=0` and `|x-pi(x)|=O(h_Gamma^2)`, smoothness gives

`||u^e||_{L_inf(Gamma_h)} <= C h_Gamma^2 ||u||_{W^{1,inf}(U)}`,

and hence, because the boundary length stays uniformly bounded,

`||u^e||_{L2(Gamma_h)} <= C h_Gamma^2 ||u||_{W^{1,inf}(U)}`.

This is the geometric datum mismatch introduced by imposing zero on the polygon instead of the true curved boundary.

## 4. Nitsche dual norm turns `h_Gamma^2` into `h_Gamma^(3/2)`

Suppose the volume PDE is extended consistently to `Omega_h` and use a boundary-consistent Nitsche integration-by-parts form. The residual caused solely by imposing homogeneous data on `Gamma_h` instead of the actual extension trace `g_h=u^e|Gamma_h` contains the adjoint and penalty terms

`R_Gamma(v_h) = - <g_h, partial_nh v_h>_Gamma_h
                 + <mu h_e^{-1} g_h, v_h>_Gamma_h`

(up to the corresponding traction convention).

Using the inverse-trace bound and the Nitsche energy norm,

`|<g_h, partial_nh v_h>|`
` <= ||h_e^(-1/2) g_h|| ||h_e^(1/2) partial_nh v_h||`
` <= C h_Gamma^(3/2) ||v_h||_E`,

and similarly

`|<mu h_e^{-1}g_h,v_h>|`
` <= mu ||h_e^(-1/2)g_h|| ||h_e^(-1/2)v_h||`
` <= C mu h_Gamma^(3/2) ||v_h||_E`,

provided boundary elements are uniformly comparable to `h_Gamma`.

Thus for fixed admissible `mu`,

`sup_{v_h != 0} |R_Gamma(v_h)| / ||v_h||_E <= C (1+mu) h_Gamma^(3/2)`.

This gives the sponsor's boundary exponent directly: **distance error `h_Gamma^2` times the Nitsche half-order trace factor `h_Gamma^(-1/2)`**.

## 5. Conditional kernel estimate

Assume, in addition to the geometry and coercivity hypotheses above, that the mesh family admits an exactly divergence-preserving Scott–Vogelius approximant `I_h^SV u in Z_h` satisfying the Nitsche-energy approximation bound

`||u^e-I_h^SV u||_E <= C h_Omega^k ||u||_{H^{k+1}(U)}`.

Assume also that the Stokes/Nitsche consistency residual on divergence-free tests is exactly the geometry residual in Section 4 (or is bounded by the same order).

Then the usual coercive Strang/Cea argument on `Z_h` gives

`||u^e-u_h||_E <= C [ h_Omega^k ||u||_{H^{k+1}(U)}
                       + h_Gamma^(3/2) ||u||_{W^{1,inf}(U)} ]`.

Since the energy norm controls the `H1` seminorm under the same Korn/coercivity assumptions,

`|u^e-u_h|_{H1(Omega_h)} <= C (h_Omega^k + h_Gamma^(3/2))`

with solution norms restored in the constant.

This is the advertised rate, **conditionally**. The reduction shows that the `3/2` exponent itself is not mysterious; the prize-level work is to discharge the Scott–Vogelius/mixed-consistency assumptions uniformly for the intended formulation.

## 6. The remaining non-cosmetic theorem gaps

### A. Mixed traction / pressure consistency

The preprint reports a symmetric-gradient volume form but writes a Nitsche boundary flux in terms of `partial_n u`. A general Stokes integration by parts with weak Dirichlet data naturally involves the **traction**, including the pressure-normal term. In the manufactured test, pressure is constant, which can hide some pressure-boundary effects on exactly divergence-free tests. A general theorem must do one of the following explicitly:

- analyze the exact published boundary form and bound its additional consistency residual;
- use a stress-consistent Nitsche form and state that correction;
- restrict the theorem to a setting (such as the constant-pressure manufactured problem) in which the omitted pressure contribution is rigorously harmless.

Calling the mixed method pressure robust does not by itself remove a pressure boundary term created by weak Dirichlet enforcement.

### B. Scott–Vogelius approximation on the exact claimed mesh family

The conditional approximant above must be bound to the actual stable Scott–Vogelius mesh class (for example, the appropriate refined/non-singular triangulations) and to the modified weak-boundary space. The usual strong-zero-trace interpolant is not the same object.

### C. Inf-sup / pressure recovery

A kernel velocity estimate is not a complete mixed theorem. The pressure space, compatibility conditions, and a mesh-uniform inf-sup/right-inverse statement must be proved for the weak-boundary velocity space or derived from an established result without changing the method.

### D. Domain-extension terms

For a general smooth solution, extending `(u,p)` and the forcing into the narrow `Omega_h triangle Omega` strip must preserve the residual order claimed. If the computational polygon lies alternately inside/outside the true domain, the proof must state the extension operator and geometric hypotheses rather than assume exact PDE validity off-domain.

### E. Actual PDE penalty sweep

`penalty_threshold.py` studies local algebraic coercivity only. The sponsor asks for the influence of the penalty parameter in the PDE computation. A prize-ready paper still needs the manufactured Scott–Vogelius run over mesh refinements and a penalty sweep, recording instability/conditioning and asymptotic error behavior.

## 7. Current strongest conclusion

The source record supports a precise **proof program**, not a prize claim:

- the strong-boundary zero-gradient pathology is real and numerically severe;
- weak Nitsche enforcement removes the literal vertex gradient constraint;
- `h_Gamma^(3/2)` follows naturally from `O(h_Gamma^2)` geometric trace mismatch in the Nitsche dual norm;
- fixed global penalty and independently refined boundary scales require an explicit scaling condition;
- the published notation/form must be repaired or interpreted before a general mixed proof can be valid.

The next proof owner should attack Sections 6A–6C first. Those are the blockers between this reduction and a publishable theorem.
