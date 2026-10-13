# Hopf route and missing hypotheses

Standard abstract Hopf (Crandall-Rabinowitz / Iooss / Kielhofer) for
an evolution u_t = F(u, Re) needs:

H1. A C^k branch of steady states u_s(Re) on an interval around Re_c.
H2. The linearized operator L(Re) = D_u F(u_s(Re), Re) generates a
    suitable analytic or C0 semigroup on the chosen function space.
H3. A pair of simple isolated conjugate eigenvalues crosses the
    imaginary axis at Re_c with nonzero speed (transversality).
H4. No other spectrum on the imaginary axis (nonresonance).
H5. The center-manifold or Lyapunov-Schmidt reduction is justified
    (compact resolvent, or Hopf-Iooss when 0 is in essential spectrum).

What is available for 2D cylinder flow:

- Steady exterior NSE solutions exist in a large Re range (Finn and
  later exterior-flow literature). That supports H1 at the level of
  existence of some steady branch, not uniqueness of the computational
  wake branch.
- 2D NSE is globally regular on bounded smooth domains. Exterior
  2D theory is subtler. Function-space choice is not free.
- Exterior linearized Oseen / NSE operators have 0 in the essential
  spectrum. Ordinary compact-resolvent Hopf on a bounded cavity does
  not transfer. Sazonov and later exterior Hopf-Iooss work address
  this for some exterior problems; they do not publish a complete
  verified crossing for the circular-cylinder uniform-flow branch
  at Re ~ 50.
- Computational linear stability reports a complex pair crossing near
  Re 46-47 on truncated domains. That is evidence for H3 on a surrogate
  operator, not a proof of H3 on the physical exterior operator.
- Arioli-Koch prove a Hopf for planar NSE on a square with Navier
  boundary conditions and a designed body force, by computer-assisted
  estimates. Different domain, different BC, different force.

Named closed partial results in this carrier:

P1. Steady solutions are excluded prize objects (sponsor text).
P2. Abstract finite-dimensional Hopf crossing is executable and tested
    (hopf_crossing.py). This closes only the bookkeeping of H3-H4 in
    R^2, not NSE.
P3. The truncated-channel numerical orbit is a different equation;
    treating it as the prize theorem is a falsified route.

Still open for the prize:

O1. Isolated simple crossing of the physical exterior linearized
    operator at a named Re_c, with a function space that handles
    essential spectrum.
O2. Transversality and nonresonance on that operator.
O3. Persistence of the periodic orbit as an exact NSE solution on
    the exterior of the disk with the sponsor far-field.
O4. Or a nonexistence obstruction in a named regime.
