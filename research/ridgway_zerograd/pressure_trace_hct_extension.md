# HCT extension of the pressure-free lower bound to quadratic velocity

Status: **conditional analytic extension on an explicit macro-refined mesh family; not a full mixed-method theorem or prize claim.**

Issue: [14998](https://github.com/woahwhattheheck/commons/issues/14998)  
Operation: RIDGWAY-HCT-QUADRATIC-EXTENSION-20261005-7CA6

[pressure_trace_curved_lower_bound.md](pressure_trace_curved_lower_bound.md), delivered in [31719](https://github.com/woahwhattheheck/commons/pull/31719), proves a curved-hole velocity-gradient lower bound using a fixed degree-eight test. This note extends that conclusion to every fixed velocity degree k>=2 on the specific Clough–Tocher/Alfeld macro refinements below. It takes the earlier forcing and uniform trace inequalities as proved inputs; it does not rerun or revalidate their certificates.

The existing Z-Sol recovery, Sol-Z strong-space extension and pressure-trace work retain their original attribution. The classical HCT construction is due to Hsieh, Clough and Tocher; Ciarlet and Percell supply the element literature cited below. The new contribution here is its application, with explicit uniform constants and boundary conditions, to the retained pressure-free equation.

## 1. Precise mesh, velocity space and equation

Use the geometry and datum of 31719: Q=(-2,2)^2, P_m the regular inscribed unit-circle polygon with cardinal vertices, m>=8 divisible by four, Omega_m=Q minus P_m, Gamma_m=boundary(P_m), and h=2 sin(pi/m). The outer square is strongly constrained; no velocity trace is imposed essentially on Gamma_m. The exact velocity is u=0, pressure p=x, and force f=(1,0).

Let M_m be a conforming macrotriangulation of Omega_m with the following properties:

- its triangles have a uniform shape-regularity bound;
- each inner polygon side, of length h, is one entire macrotriangle boundary edge;
- its maximum diameter H_m tends to zero.

Split each macrotriangle by joining its **barycenter to its three vertices**, making three triangles. Let T_m be this fine triangulation. This is the three-triangle Clough–Tocher/Alfeld split, not a six-triangle subdivision through edge midpoints. The barycenter choice keeps all fine triangles uniformly shape regular and leaves each macroboundary edge intact. A fine triangle incident to Gamma_m has diameter comparable to h, with constants independent of m. The maximum fine diameter equals H_m, since each macrotriangle's longest edge is retained by a fine triangle.

Fix k>=2 independently of m. Define X_m to be the full space of continuous, piecewise [P_k]^2 fields on T_m with zero outer-square trace, and Z_m={w in X_m: div w=0 on every fine triangle}. The word full matters: a smaller constrained normal-trace space is not covered.

For a fixed penalty mu>0, use exactly the previous pressure-free form, with normal directed outward from the fluid:

A_m(w,z) =
  (1/2) integral_Omega_m D(w):D(z)
  - integral_Gamma_m partial_n w . z
  - integral_Gamma_m w . partial_n z
  + (mu/h) integral_Gamma_m w . z,

where D(w)=grad w+(grad w)^T and partial_n w=(grad w)n. Consider **any** u_m in Z_m satisfying

A_m(u_m,z_m) = integral_Omega_m f.z_m for all z_m in Z_m.          (1)

No existence, coercivity, pressure recovery or discrete inf-sup conclusion is assumed or proved. The theorem is conditional on a solution of (1). A mixed method with additional pressure-normal boundary terms or multipliers need not reduce to (1).

## 2. Classical HCT input and the selected interpolant

On each macrotriangle K, the full cubic HCT space consists of C1 functions whose restrictions to its three subtriangles are cubic. Its twelve degrees of freedom are the value and two first derivatives at each vertex, and the physical normal derivative at each edge midpoint. Use one consistent normal orientation on each shared macroedge. This is the classical element described in Ciarlet's lectures, Exercise 4.8 [C], with unisolvence established in the literature summarized by Percell [P]. The reduced nine-degree-of-freedom element is not being substituted.

Let I_m psi match those degrees of freedom. Global C1 conformity follows directly: along a shared macroedge the two cubic value traces have the same endpoint values and tangential derivatives, so they agree; their quadratic normal-derivative traces agree at both endpoints and the midpoint, so they also agree.

Ciarlet explicitly notes that HCT normal derivatives require treatment beyond ordinary affine-equivalent interpolation and that an uncontrolled interior split point is problematic [C, end of Chapter 10]. We fix that point at the barycenter and give the needed estimate for our smooth input below. No unavailable general interpolation theorem is presumed.

## 3. Uniform interpolation estimate for this smooth polynomial

Use the same globally defined polynomial as 31719:

F(t)=(4-t^2)^2,   psi(x,y)=F(x) F(y) (1+y),   v=curl psi,

with curl psi=(partial_y psi,-partial_x psi). Thus psi has degree nine and v degree eight. Only a uniform C4 bound for psi on the fixed square is needed in this section.

Here is a finite-dimensional scaling argument that accounts for the physical normal degrees of freedom. Normalize a macrotriangle by translation and its diameter H_K, then orient a longest edge horizontally and label the vertices counterclockwise. Uniform shape regularity puts the resulting triangles in a compact set of nondegenerate shapes. The split point remains their barycenter.

The C1 piecewise-cubic space on any such normalized split is the affine image of the fixed reference split space. Choose a fixed basis of that reference space. Evaluation of the twelve **actual normalized physical** degrees of freedom on the transported basis gives a continuous matrix depending on the normalized vertices and edge normals. Classical HCT unisolvence makes every such matrix invertible. Compactness therefore bounds its inverse uniformly. Polynomial differentiation and the affine maps on this compact shape set likewise have uniform bounds.

In particular, the interpolating basis functions and their derivatives through order two are uniformly bounded in the maximum norm on the normalized subtriangles. This argument does not identify physical normal derivatives with reference normal derivatives; their shape-dependent matrices are exactly what is bounded.

Subtract from psi a total-degree-three Taylor polynomial T_K at a macrovertex. HCT reproduces T_K because it lies in the local space and has its own degrees of freedom. Taylor's theorem on the convex triangle, using the fixed C4 bound, gives for R_K=psi-T_K:

||D^j R_K||_Linf(K) <= C H_K^(4-j),   j=0,1,2.

The value degrees of freedom of R_K are O(H_K^4), and its physical first-derivative degrees of freedom are O(H_K^3). After scaling to the normalized triangle, first derivatives gain a factor H_K, so **all normalized interpolation data are O(H_K^4)**. The uniform basis bound above and rescaling imply, on each subtriangle,

||D^j (psi-I_m psi)||_Linf <= C H_K^(4-j),   j=0,1,2.             (2)

The constant depends on the fixed polynomial and macro shape bound, not on m, K or the number of triangles. Both functions are globally C1, so their piecewise second derivatives are their weak second derivatives, without edge distributions. Squaring (2), integrating, summing the triangle areas, and using |Omega_m|<=|Q| gives

||grad(psi-I_m psi)||_L2(Omega_m) <= C H_m^3,
||D^2(psi-I_m psi)||_L2(Omega_m) <= C H_m^2.                      (3)

Thus this particular interpolant converges in H2 uniformly over the varying polygonal domains. No interpolation software, basis table, numerical evaluation or convergence experiment is used.

## 4. Exact boundary condition and velocity-space membership

Set v_m=curl(I_m psi). It is continuous and piecewise quadratic on T_m. Mixed derivatives commute within every fine polynomial piece; global continuity rules out normal-jump distributions. Hence div v_m=0, both elementwise and distributionally.

The fixed psi and its full gradient vanish on the outer square. Consequently every outer-boundary HCT vertex value/gradient and midpoint normal derivative is zero. On any outer macroedge:

- the cubic scalar trace has zero endpoint values and tangential derivatives, hence is identically zero;
- the quadratic normal-derivative trace has zero endpoint and midpoint values, hence is identically zero.

The full gradient of I_m psi therefore vanishes there. It follows that v_m=0 on the entire outer boundary, not just at interpolation nodes. There is no analogous zero condition on the inner polygon.

We have proved v_m in Z_m for every fixed k>=2. This is a direct inclusion in the actual full [P_k]^2 velocity space from Section 1; it requires no Fortin map, pressure-space assumption, low-degree inf-sup result or discrete streamfunction exactness theorem.

Equation (3) now gives

||v_m-v||_L2 <= C H_m^3,   |v_m-v|_H1 <= C H_m^2,
|v_m|_H1 <= M,                                                    (4)

with a mesh-uniform M, since v is a fixed polynomial on Q.

## 5. Preserve the forcing and control the new normal derivative

Two previously established inequalities are used as inputs from 31719, Sections 3–4:

abs(integral_Omega_m f.v) >= b_0=2025/16,                          (5)
||w||_L2(Gamma_m) <= C_T |w|_H1(Omega_m),                         (6)

where (6) holds for all outer-zero H1 fields, uniformly in m. The strong outer boundary is essential to this seminorm estimate.

Since ||f||_L2(Omega_m)<=|Q|^(1/2), (4) implies

abs(integral_Omega_m f.v_m) >= b_0-C H_m^3 >= b_0/2               (7)

for all sufficiently fine meshes. This is convergence of a newly constructed test, not a new computation of the old forcing certificate.

Unlike the fixed test v, the normal derivative of v_m need not have a mesh-independent boundary norm. Use the fixed-degree polynomial inverse trace estimate on the fine boundary triangles instead:

||partial_n w_m||_L2(Gamma_m) <= C_I h^(-1/2) |w_m|_H1.           (8)

Their uniform shape regularity and boundary diameter comparability established in Section 1 give the same reference-polynomial scaling as in 31719. Applying (6) and (8) also to v_m, together with (4), gives

||v_m||_Gamma_m <= C_T M,
||partial_n v_m||_Gamma_m <= C_I M h^(-1/2).                     (9)

This h^(-1/2) factor is retained; it is not replaced by the stronger fixed-polynomial bound.

Cauchy–Schwarz in each of the four terms of A_m, (6), (8) and (9) now give, for all w_m in X_m,

|A_m(w_m,v_m)|
 <= [C_0+C_1 h^(-1/2)+C_2 h^(-1/2)+C_3 mu h^(-1)] |w_m|_H1
 <= C h^(-1) |w_m|_H1.                                          (10)

Here 0<h<1 and mu is fixed; the same constant choice is uniform for 0<mu<=mu_max. Constants may depend on fixed k, the macro shape bound, mu_max and psi, but not m, refinement level or polygon count.

## 6. Conditional lower bound and rate consequence

Insert the admissible v_m in (1), then combine (7) and (10). For all sufficiently large m, **every solution** of (1) obeys

|u-u_m|_H1(Omega_m)=|u_m|_H1(Omega_m) >= c h,   c=b_0/(2C)>0.     (11)

This extends the earlier result to every fixed k>=2 on the explicit barycentrically refined family, while retaining the precise pressure-free form, strongly zero outer boundary and fixed penalty.

For the two-scale comparison add the condition H_m^k=o(h). Uniform global comparability H_m<=C_mesh h is one sufficient choice for every fixed k>=2. Then h^(3/2)+H_m^k=o(h), so (11) rules out a mesh-uniform estimate of that order for this datum and this method. Without that additional scale relation, (11) still holds but does not by itself contradict the stated two-scale upper rate.

The conclusion is not an all-mesh or all-formulation theorem. It does not cover a growing penalty, a smaller normal-trace velocity space, all-weak outer boundary conditions, a stress-consistent/multiplier-repaired method, or a constant-pressure datum. It does not establish solvability, mixed stability, the corrected method's convergence, a PDE penalty study, independent publication or sponsor acceptance.

## Primary references and custody

[C] P. G. Ciarlet, *Lectures on the Finite Element Method*, TIFR, 1975, Exercise 4.8, printed pp.49–50, and the end of Chapter 10, printed p.111. [Official TIFR PDF](https://mathweb.tifr.res.in/Documents/Publications/Lectures/tifr49.pdf). The exact element definition and the normal-derivative/interior-point caution were read. Exercise 4.8 leaves unisolvence as an exercise; its coefficient count is not treated as a proof.

[P] Peter Percell, *On Cubic and Quartic Clough–Tocher Finite Elements*, SIAM Journal on Numerical Analysis 13(1), 100–103 (1976), [DOI 10.1137/0713011](https://epubs.siam.org/doi/10.1137/0713011). The official abstract explicitly reports a proof of cubic Clough–Tocher unisolvence. The full paywalled article was not read; no detailed interpolation estimate is attributed to it. Section 3 above supplies the needed restricted estimate.

The retained mathematical input is pressure_trace_curved_lower_bound.md, blob dbcf211674842328f46fa563268d36179352e9fc, merged in 31719 at cd0840433ad799dd12767c99bbeaeb04e879ad6a. Its formulation remains pinned to proof_reduction.md (969275a711090ea962f49d04a1f8a5c57fc5b8d2) and pressure_trace_consistency.md (3ad36c3715a4888d892d4ec948669e734b00c5df). Those accepted files are not modified or re-executed.

The original Ciarlet 1974 journal-PDF route returned HTTP403; two other explored primary routes returned HTTP400 timeout and HTTP429. They were not retried or replaced. The earlier sponsor-PDF HTTP502 and arXiv DisabledError holds also remain. These failures confer no interpretation of the sponsor statement. This note is an attributed conditional theorem for the explicitly stated Commons formulation, with no prize, payment, publication-acceptance or runtime claim.
