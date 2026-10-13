# Sponsor statement pin

Source: https://people.cs.uchicago.edu/~ridg/prizes/strouhalprize.pdf
(L. Ridgway Scott, The Strouhal Prize, 16 March 2025)
Index: https://people.cs.uchicago.edu/~ridg/prizes/prizes.html

The prize is offered for publication of a mathematical proof of existence
of a non-constant, periodic-in-time solution of the 2D incompressible
Navier-Stokes equations for flow around a cylinder at the Reynolds
numbers indicated in the experimental and computational literature cited
there (onset near Re ~ 50, believed periodic through Re ~ 1000), or a
proof that no such periodic solutions exist.

Pinned distinctions:

1. Domain. Physical problem is exterior flow past a circular cylinder.
   A truncated computational channel with artificial inflow and outflow is
   a different PDE problem. A proof on a box with body force
   (Arioli-Koch square) is not the prize geometry.
2. Boundary data. No-slip on the cylinder. Far-field uniform flow in
   the physical statement. Inflow and outflow closures are extra assumptions.
3. Reynolds number. Re = U D / nu with D the diameter (or the
   equivalent used by a cited paper). Prize text points at the regime
   near the believed Hopf onset ~50 and the periodic window to ~1000.
   Talk slides sometimes say any Reynolds number; the dated PDF
   points at the indicated experimental and computational regime.
4. Periodicity. Exact time-periodicity: there exists T>0 such that
   u(x,t+T)=u(x,t) and p differs at most by a gauge, for all t.
   Approximate numerical periodicity of drag or lift is not this object.
5. Regularity. A classical or strong NSE solution on the exterior
   domain, or a precisely stated weak class that still yields a
   classical periodic orbit after bootstrap.
6. Non-constant. Steady solutions exist above Re 50 and are trivially
   T-periodic for every T. The prize excludes them.

This land does not invent a missing official function-space sentence
the PDF does not write. That missing sentence is itself a named gap
in HYPOTHESES.md.
