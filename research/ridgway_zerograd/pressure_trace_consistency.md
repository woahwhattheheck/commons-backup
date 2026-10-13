# Pressure-trace consistency blocker for the zero-gradient Nitsche prize

Status: **rigorous discrete consistency counterexample and repair boundary; not a complete prize proof.**

Issue: #14998  
Operation: `RIDGWAY-ZEROGRAD-PRESSURE-TRACE-COUNTEREXAMPLE-ZSOL-20260917`

This note closes one ambiguity left by `proof_reduction.md`: for general nonconstant pressure, the pressure-free velocity Nitsche kernel written in Gjerde–Scott Eq. (27)/(28) is not the full mixed Stokes consistency identity on exactly divergence-free tests when normal velocity is weakly enforced.

The strongest witness below is already degree 3 in velocity, hence contained in the full degree-4 velocity space used by the reported Scott–Vogelius experiment. It is local to a single weak-boundary triangle and extends by zero across its other two edges. The result therefore does not depend on a degree-8 global polynomial construction.

It still does **not** prove the full Scott–Vogelius–Nitsche convergence theorem, the sponsor's curved-domain asymptotic lower bound, publication, or prize entitlement.

## 1. Source-level mismatch

Gjerde–Scott Eq. (5) contains the full Cauchy traction. With viscosity normalized to one, its divergence-free structure is

`(f,v) = a(u,v) - (p,div v) - <D(u)n,v> + <p,v·n>`.

If `div v=0`, the *volume* pressure term disappears but the boundary pressure trace remains:

`(f,v) = a(u,v) - <D(u)n,v> + <p,v·n>`.

By contrast, Eq. (27) uses a velocity normal-derivative Nitsche flux, its adjoint term, and the penalty; Eq. (28) couples that velocity form to the usual volume pressure-divergence form. The displayed weak-boundary form contains no explicit pressure-normal boundary work.

Thus exact divergence freedom alone does not remove pressure from the weak-boundary consistency relation whenever the test space permits `v·n != 0` on that boundary.

## 2. Exact quartic-compatible boundary-triangle witness

Take the reference triangle

`K = {(x,y): x>=0, y>=0, x+y<=1}`.

Treat the legs `x=0` and `y=0` as zero-extension/interior edges and the hypotenuse `x+y=1` as the weak boundary edge. Define

`psi=x^2 y^2`,

`v=curl psi=(2 x^2 y, -2 x y^2)`.

Then:

- `v` is degree 3, so `v in [P_4(K)]^2`;
- `div v = 0` identically;
- both components of `v` vanish identically on `x=0` and `y=0`, because `psi` has a double zero there;
- therefore `v` can be extended by zero to all neighboring elements across those two edges while remaining continuous and exactly divergence-free elementwise;
- on the weak edge `x+y=1`, its normal component is nonzero although its total flux is zero.

Now choose the no-flow Stokes solution

`u=0`, `p=x`, `f=grad p=(1,0)`.

Exact rational integration gives

`(f,v)_K = integral_K 2 x^2 y = 1/30`,

`(p,div v)_K = 0`.

On `x+y=1`, outward `n=(1,1)/sqrt(2)` and `ds=sqrt(2) dx`, hence

`<p,v·n>_e = integral_0^1 x [v_x(x,1-x)+v_y(x,1-x)] dx = 1/30`.

At `u=0`, all velocity-only Nitsche terms vanish. The displayed pressure-free kernel therefore has LHS zero while the forcing functional equals `1/30`: exact consistency defect `-1/30` in the certificate's `lhs-rhs` convention.

This is not merely a continuum or high-degree witness. It is a compactly supported `P3` test inside a full `P4` weak-boundary velocity space. Any conforming triangulation containing a weak boundary edge with one adjacent triangle permits the same barycentric construction `psi=lambda_A^2 lambda_B^2` on that triangle and zero extension across its other two edges (after affine transport).

The conclusion is formulation-level but degree-relevant: the general claim that exact Scott–Vogelius divergence freedom deletes pressure from the weak-normal consistency equation is false without an additional boundary-pressure mechanism or cancellation theorem.

## 3. Fully weak low-degree sanity check

On `Omega=[0,1]^2`, take `u=0`, `p=x`, `f=(1,0)`, `v=(1,0)`. Then `v` is degree zero and exactly divergence free,

`(f,v)=1`, `(p,div v)=0`, `<p,v·n>=1`,

while the velocity-only Nitsche kernel at `u=0` is zero. This is the same defect in its simplest form.

## 4. Strong-outer / weak-inner topology sanity check

The retained square-annulus certificate independently shows the mechanism survives the sponsor-style boundary topology. On

`Omega=[-2,2]^2 \ [-1,1]^2`,

use outer square strong, inner square weak, and

`psi=(4-x^2)^2(4-y^2)^2(1+y)`, `v=curl psi`.

The exact certificate proves `div v=0`, both velocity components vanish on the whole outer boundary, and for `p=x`, `f=(1,0)`:

`(f,v)=<p,v·n>_inner=-2436/5`, `(p,div v)=0`.

The exact inner-edge partition is `-162`, `-162`, `-816/5`, `0`. This velocity is degree 8, so this annulus construction is retained as a topology sanity check; the degree-relevant result is Section 2.

## 5. Why this is not automatically an `h_Gamma^(3/2)` remainder

The landed geometry reduction concerns the exact no-slip velocity trace on the displaced polygonal boundary: `u^e|Gamma_h=O(h_Gamma^2)`, which becomes `O(h_Gamma^(3/2))` after the Nitsche half-order weight.

The pressure trace is different. A generic bound is

`|<p-c,v_h·n>| <= ||h_e^(1/2)(p-c)|| ||h_e^(-1/2)v_h||`.

Divergence freedom and zero flux on the remaining strong boundary allow subtraction of a *global* constant `c`; they do not allow independent edgewise constants without extra orthogonality. For smooth nonconstant pressure on an `O(1)` boundary and `h_e~h_Gamma`, the first weighted factor is generically only `O(h_Gamma^(1/2))` for global `c`.

This is an **upper-bound scaling warning**, not an asserted asymptotic lower bound for the sponsor's curved mesh. The exact `P3/P4` witness establishes nonzero consistency; any sharper decay on the actual mesh family would have to come from a separately proved normal-trace/pressure cancellation.

## 6. Why the published manufactured test can hide the defect

The manufactured test immediately preceding the Nitsche experiment uses constant pressure. For `p=c`,

`<p,v_h·n>_Gamma_h = c int_Gamma_h v_h·n`.

If `v_h` is exactly divergence free and has zero normal flux on the remaining strong boundary, the divergence theorem makes this zero. Constant pressure therefore lies in a special cancellation class. A successful constant-pressure experiment cannot establish general pressure robustness of the displayed weak-normal method.

## 7. Independent 2026 corroboration

Neilan, Olshanskii, and von Wahl, *An unfitted divergence-free higher order finite element method for the Stokes problem* (arXiv:2512.12050v2, 22 July 2026), analyze a different method and are not proof of this prize theorem. Their result is nevertheless mechanistically aligned: they identify loss of pressure robustness when normal velocity is imposed weakly and introduce a boundary multiplier with

`c_h(lambda_h,v_h)=int_Gamma_h lambda_h n_h·v_h`.

Their no-flow, nonconstant-pressure experiment probes exactly the pressure-to-velocity leakage that the algebraic witnesses here expose.

## 8. Minimum theorem repairs

A prize-ready theorem must explicitly choose and analyze one of these routes:

1. **Stress-consistent Nitsche:** retain the full Stokes traction, including pressure-normal work.
2. **Pressure-trace / normal multiplier:** carry the missing normal-traction information in a stable boundary variable or constraint while retaining weak boundary velocity freedom.
3. **Discrete cancellation theorem:** prove the actual Scott–Vogelius weak-boundary normal-trace space is orthogonal to the relevant pressure trace to the required order. The `P3` boundary-triangle witness shows this is not automatic for the full weak-boundary `P4` space.
4. **Restricted theorem:** constant-pressure manufactured solutions may exploit total-flux cancellation, but that is not a general mixed Stokes theorem.

Even after this blocker is repaired, #14998 still needs curved-to-polygonal divergence-compatible approximation/transfer, weak-boundary inf-sup and pressure recovery, complete geometry residual closure, a PDE penalty sweep, independent theorem review, and publication.

## 9. Reproducibility and truth ceiling

`pressure_trace_counterexample.py` uses only the Python standard library and exact `fractions.Fraction` arithmetic. The retained tests cover:

- fully weak degree-0 defect;
- the `P3`/full-`P4` boundary-triangle witness, exact zero-extension traces, and `1/30` equality;
- strong-outer/weak-inner annulus trace and `-2436/5` equality;
- exact annulus edge partition;
- explicit runtime certification of divergence, zero/strong trace, polynomial degree, pressure-volume pairing, and forcing/boundary-flux identities;
- negative local witnesses that are either non-divergence-free or divergence-free with a bad zero-extension trace, both of which must raise `CertificateError`;
- a real `python -O` subprocess hostile proving those negative witnesses cannot mint a positive certificate when interpreter assertions are disabled;
- an explicit theorem ceiling.

The successful machine-readable certificate shape remains `results/pressure_trace_counterexample.json`, but its truth fields are now derived from the actual exact polynomials and protected by explicit runtime checks rather than Python `assert`.

**Proved here:** a nonzero pressure-normal consistency defect exists in the displayed general weak-normal formulation, including an exact `P3` test contained in a full `P4` velocity space.

**Not proved here:** the repaired full convergence theorem, a sponsor-specific curved-domain error lower bound, publication, prize eligibility/award, receivable, or cash.

No sponsor or author contact is performed by this carrier.