# A curved-hole lower bound for the pressure-free weak-boundary form

Status: **analytic partial result for an explicitly specified pressure-free method; not a full Nitsche theorem or prize claim.**

Issue: [14998](https://github.com/woahwhattheheck/commons/issues/14998)  
Operation: RIDGWAY-PRESSURE-TRACE-CURVED-LOWER-BOUND-20261005-7CA6

The existing Z-Sol recovery, Sol-Z strong-space extension, and pressure-trace counterexample remain credited to their original authors. [pressure_trace_consistency.md](pressure_trace_consistency.md) already proves a nonzero pressure-normal consistency defect, including a local P3 witness in a full P4 space. This note does not repeat its certificates. It adds an asymptotic statement absent from that note: on an explicitly defined circular-hole geometry, **every solution of the stated pressure-free discrete equations has velocity-gradient error at least c h** for a smooth no-flow Stokes datum.

This is a lower bound for the form below, with a fixed degree k>=8. It does not establish a lower bound for the constant-pressure manufactured example, for all degrees, or for a stress-consistent/multiplier-repaired method.

## 1. Geometry, space and exact scope

Let Q=(-2,2)^2, let B be the open unit disk, and let the true fluid domain be Omega=Q \ closure(B). Its outer square is a strong homogeneous velocity boundary; its inner circle is the boundary to be approximated.

For m divisible by 4 and m>=8, let P_m be the regular closed m-gon inscribed in the unit circle, with vertices at the four coordinate-axis points. Set Omega_m=Q \ P_m and Gamma_m=boundary(P_m), with normal outward from the fluid (into the hole). Put h=h_m=2 sin(pi/m), the common inner boundary-edge length.

The polygon is symmetric in both coordinate axes. It contains the disk of radius cos(pi/m); its boundary length is m h<=2 pi. Its radial distance from the circle is at most

1-cos(pi/m) = h^2/[4(1+cos(pi/m))] = O(h^2).

Let T_m be any conforming triangular mesh of Omega_m with a mesh-uniform shape-regularity constant, using the sides of P_m as boundary edges. Fix k>=8 independently of m. Let X_m be the full space of continuous piecewise [P_k]^2 velocities with zero trace on the outer square and **no essential constraint on Gamma_m**. Define Z_m={w in X_m : div w=0 elementwise}.

No existence construction for an additional special mesh property, Fortin operator, or mixed inf-sup estimate is used. The conclusion applies to any such mesh family and any solution of the equations below. For comparison with a two-scale rate, an additional relation on its maximum element diameter h_Omega is stated explicitly in Section 6.

Use exactly the velocity-only boundary form isolated in proof_reduction.md, with viscosity normalized to one:

A_m(w,z) =
  (1/2) integral_Omega_m D(w):D(z)
  - integral_Gamma_m partial_n w . z
  - integral_Gamma_m w . partial_n z
  + (mu/h) integral_Gamma_m w . z.

Here D(w)=grad w+(grad w)^T, and partial_n w=(grad w)n on each polygon edge. The dimensionless penalty mu>0 is fixed as m varies. The estimates also hold uniformly for 0<mu<=mu_max. No assertion of coercivity or solvability is required.

The precise discrete equation under consideration is

A_m(u_m,z) = integral_Omega_m f . z for every z in Z_m.              (1)

A mixed method with only the usual volume pressure-divergence coupling has the same equation on this kernel. A method with additional pressure-normal boundary terms, boundary multipliers, nonzero boundary loads, or a smaller normal-trace space need not satisfy (1) and is outside this result.

## 2. A fixed admissible test and a smooth no-flow datum

Put F(t)=(4-t^2)^2 and define the fixed polynomial

psi(x,y)=F(x) F(y) (1+y),   v=(partial_y psi,-partial_x psi).

Its degree is 8. Equality of mixed derivatives gives div v=0. Both F and F' vanish at t=+2 and t=-2, so both components of v vanish on all four sides of the outer square. Therefore v belongs to Z_m on every mesh above: it is one global polynomial, continuous across every element, and its membership requires no interpolant or discrete approximation argument.

Choose u=0, p=x, f=grad p=(1,0). These fields are smooth on a neighborhood of Q and solve the no-flow Stokes equations on the true domain and every polygonal domain. There is no curved-to-polygonal extension residual to estimate. Symmetry gives zero mean for p if the pressure normalization requires it.

The test polynomial is the same degree-8 construction already recorded for the square-annulus sanity check in pressure_trace_consistency.md. Its use here on a refining circular-hole family and the resulting asymptotic estimate are new; the old certificate is neither rerun nor needed by this proof.

## 3. The forcing functional stays bounded away from zero

Since psi=0 on the outer square,

integral_Q v_1 = integral_Q partial_y psi = 0.

Consequently

integral_Omega_m f.v = -integral_P_m partial_y psi.                 (2)

Write a vertical section of the polygon as [-s_m(x),s_m(x)] for -1<=x<=1. Symmetry and the fundamental theorem of calculus give

integral_P_m partial_y psi
 = integral_{-1}^1 [psi(x,s_m(x))-psi(x,-s_m(x))] dx
 = 2 integral_{-1}^1 F(x) F(s_m(x)) s_m(x) dx.                      (3)

The integrand is nonnegative. The polygon contains a disk of radius at least 1/sqrt(2). Thus, for |x|<=1/2,

1/2<=s_m(x)<=1,   F(x)>=225/16,   F(s_m(x))>=9.

Restricting (3) to this interval of length one proves the uniform bound

abs(integral_Omega_m f.v) >= 2025/16 =: b_0 > 0.                   (4)

Only analytic identities and inequalities are used. No limiting contour argument, quadrature, numerical polynomial evaluation or PDE run is involved.

## 4. Uniform trace control comes from the strong outer boundary

The outer essential condition is indispensable to the seminorm estimate below; constants are not silently discarded.

In polar coordinates let rho_m(theta) be the polygon radius and R(theta)=2/max(|cos theta|,|sin theta|) the outer square radius. Uniformly,

1/sqrt(2)<=rho_m<=1,   2<=R<=2 sqrt(2).

Except at finitely many vertices, the inner boundary arclength satisfies

ds/dtheta = rho_m sec(delta) <= sqrt(2),

where |delta|<=pi/m is the angle from the normal to the polygon side. If w is in H1(Omega_m) with zero trace on the outer square, the radial fundamental theorem and weighted Cauchy-Schwarz give, for almost every theta,

|w(rho_m,theta)|^2
 <= log(R/rho_m) integral_{rho_m}^{R} |partial_r w|^2 r dr
 <= log(4) integral_{rho_m}^{R} |grad w|^2 r dr.

Integration with respect to boundary arclength yields

||w||_{L2(Gamma_m)}^2 <= sqrt(2) log(4) |w|_{H1(Omega_m)}^2.         (5)

For general H1 functions the same inequality follows by density/one-dimensional Sobolev representatives in these uniformly bounded radial coordinates. It applies componentwise. Thus (5) supplies the uniform trace bound directly; no unexplained mesh-dependent Poincare constant is assumed. This argument does not apply unchanged when the outer boundary is also weakly imposed.

## 5. Testing the discrete equation yields an H1 lower bound

For fixed degree and shape-regular boundary triangles, the polynomial inverse-trace estimate is uniform:

||partial_n w_m||_{L2(Gamma_m)}
 <= C_I h^(-1/2) |w_m|_{H1(Omega_m)}.                              (6)

To see the scaling, on the finite-dimensional reference polynomial space the squared gradient trace norm is bounded by a constant times its squared volume norm. An affine map to a boundary triangle gives a factor comparable to its inverse diameter. Shape regularity and the boundary side length h make that diameter comparable to h. Summing counts each triangle at most three times. This proves (6) without interior quasi-uniformity; C_I depends on fixed k and shape regularity, not m.

The fixed polynomial v and its first derivatives are bounded on Q, and |Gamma_m|<=2 pi. Hence ||v||_Gamma_m, ||partial_n v||_Gamma_m and ||D(v)||_Omega_m have bounds independent of m.

Apply Cauchy-Schwarz, (5), and (6) to the four terms of A_m. For every w_m in X_m,

|A_m(w_m,v)|
 <= [C_0+C_1 h^(-1/2)+C_2 mu h^(-1)] |w_m|_H1
 <= C h^(-1) |w_m|_H1,                                          (7)

because 0<h<1 and mu is fixed/bounded above. Constants depend only on the fixed polynomial, degree, penalty bound, outer square and uniform shape-regularity constant, not m. The volume term uses ||D(w_m)||<=2||grad w_m||; the adjoint boundary term uses (5); the normal-derivative term uses (6); the penalty term uses (5) and its explicit factor mu/h.

Let u_m be any solution of (1). Insert the admissible v and combine (4) with (7):

b_0 <= |A_m(u_m,v)| <= C h^(-1) |u_m|_H1.

Since the exact velocity is zero, this proves

**|u-u_m|_{H1(Omega_m)} = |u_m|_{H1(Omega_m)} >= c h,**

where c=b_0/C>0 is independent of m.                              (8)

The result is conditional only on a solution satisfying (1). If a chosen penalty yields no discrete solution, this note does not manufacture one or turn failure of solvability into a numerical observation.

## 6. Consequence and limits

Suppose additionally that the chosen mesh family has h_Omega<=C_mesh h, or more generally h_Omega^k=o(h). Then h^(3/2)+h_Omega^k=o(h). For the fixed smooth datum above, (8) rules out a mesh-uniform estimate

|u-u_m|_H1 <= C_data [h^(3/2)+h_Omega^k]

for the explicitly pressure-free equation (1), with fixed k>=8. The same contradiction applies if the left side is the full H1 norm, since that norm dominates the seminorm. No lower bound for k=2,...,7 is claimed by this fixed-polynomial argument.

This advances the previous nonzero-consistency result to a curved-hole velocity-gradient lower bound, but does not settle the sponsor problem for every interpretation:

- The datum has nonconstant pressure. Constant pressure can cancel by total flux, as the existing note explains.
- The outer square is strongly zero; the circular component is weakly imposed on its polygonal approximation.
- The velocity space is the full weak-boundary polynomial space stated above.
- The penalty is fixed/bounded above. A penalty growing with refinement changes (7).
- The conclusion concerns equation (1), not a stress-consistent correction or boundary-multiplier method.
- No full mixed stability theorem, corrected-method upper rate, PDE penalty sweep, independent publication, prize acceptance or payment is established.

## Source custody and attribution

The mathematical inputs are the actual retained Commons formulation and prior pressure-trace result:

- proof_reduction.md, blob 969275a711090ea962f49d04a1f8a5c57fc5b8d2;
- pressure_trace_consistency.md, blob 3ad36c3715a4888d892d4ec948669e734b00c5df;
- README.md before this addition, blob bfa1b175884546651064314d95196cc67d3b2d6f.

The original recovery and additive result are documented in issue14998 comments5708243061 and5710717006; the intervening mathematical review is comment5708400144. This note does not revise their accepted computations or claim their work as new.

During this continuation, the sponsor PDF request returned HTTP502 and the arXiv HTML request returned DisabledError. Those routes were not retried or replaced. Accordingly, the new theorem is bound to the explicitly reproduced Commons form, not to a newly verified reading of the sponsor statement or paper. The advertised prize is not treated as a current entitlement.

No executable file, test, fixture, simulation, certificate rerun or sponsor communication accompanies this analytic result.
