# Ridgway zero-gradient prize — Scott–Vogelius–Nitsche recovery

Operation: `RIDGWAY-ZEROGRAD-NITSCHE-ZSOL-RECOVERY-20260916`

Advertised prize: **$1,000** for a **published proof** that Scott–Vogelius–Nitsche converges, including a computational study of the Nitsche penalty parameter. The sponsor states the expected velocity-gradient error shape as

\[
\|u-u_h\|_{H^1}\;\lesssim\; h_\Gamma^{3/2}+h_\Omega^k,\qquad k\ge 2,
\]

where `h_Gamma` is the curved-boundary mesh scale and `h_Omega` the interior mesh scale. If that estimate fails, the prize statement explicitly asks for an explanation.

Official prize PDF: `https://people.cs.uchicago.edu/~ridg/prizes/zerogradprize.pdf`

## Current state

**`PARTIAL_RIGOROUS / NOT_PRIZE_READY / NO_SPONSOR_CONTACT`**

This carrier does not claim a finished prize proof. It establishes three things that materially narrow the remaining theorem.

1. **The published weak-boundary formulation needs to be stated carefully before it can be proved.** The 2023 preprint defines its Scott–Vogelius velocity space with zero trace on the polygonal boundary and later reuses that symbol in the Nitsche section. Taken literally, the Nitsche boundary terms vanish. The numerical tables plainly intend an unconstrained-on-`Gamma_h` velocity space, so a proof must repair the notation explicitly rather than prove the literal contradictory statement.

2. **The sponsor's `h_Gamma^(3/2)` term has a direct Nitsche trace mechanism.** For an inscribed polygon with boundary-distance error `delta_Gamma = O(h_Gamma^2)` and a smooth exact no-slip solution, the extension satisfies `u^e|Gamma_h = O(h_Gamma^2)`. In the Nitsche energy dual norm, multiplying this boundary mismatch by `h_Gamma^(-1/2)` produces `O(h_Gamma^(3/2))`. `proof_reduction.md` writes this reduction precisely and lists the additional assumptions needed to turn it into a full Scott–Vogelius theorem.

3. **Penalty scaling is genuinely two-scale.** `penalty_threshold.py` assembles the paper-style symmetric Nitsche quadratic exactly on a reference boundary triangle over the complete divergence-free vector-polynomial space `[P_k]^2 cap ker(div)`. For quartic velocity (`k=4`) the first loss-of-positivity threshold is about `21.6438984049` when the penalty is written `mu/h_e` with the reference boundary edge length `h_e=1`, or `30.6090946668` if the denominator is the reference triangle diameter `sqrt(2)`. This is a local diagnostic, not a global convergence theorem. In particular, a paper using `mu/h_Omega` while independently refining the boundary requires `mu` to compensate for `h_Omega/h_Gamma`, unless boundary and interior scales remain comparable. A local `mu/h_e` formulation avoids that hidden scaling problem.

## Reproducible commands

Requires Python 3. SciPy + NumPy are required only for generalized-eigenvalue extraction; exact matrix assembly itself uses `fractions.Fraction`.

```bash
python research/ridgway_zerograd/penalty_threshold.py --min-k 1 --max-k 5
python -m unittest discover -s research/ridgway_zerograd/tests -v
python -O -m unittest discover -s research/ridgway_zerograd/tests -v
```

The regression suite checks the exact divergence-free basis, exact rational symmetry, quartic threshold, sign change across the threshold, and the two-scale conversion rule.

## What remains before a prize claim

A publishable proof still needs all of the following, with no silent substitutions:

- define the Nitsche velocity space without strong zero trace on the curved polygonal boundary;
- settle the **consistent Stokes traction/pressure boundary form** (the preprint writes a symmetric-gradient volume form but a `partial_n u` Nitsche flux; a general-pressure proof must account for the corresponding traction/pressure term rather than relying on the constant-pressure manufactured test);
- prove mesh-uniform coercivity with an explicit local-scale penalty or an explicit `h_Omega/h_Gamma` condition;
- bind a Scott–Vogelius divergence-preserving approximation/Fortin result for the exact mesh family being claimed;
- prove the geometry residual estimate on polygonal curved-boundary approximation, including normal/trace terms and any domain-extension terms;
- prove mixed well-posedness / pressure recovery, not only a kernel estimate;
- reproduce a full PDE penalty sweep on the sponsor's manufactured problem, not only the local polynomial spectrum;
- independent mathematical review;
- publication satisfying the sponsor's published-proof condition.

Until those are complete, the strongest truthful state is **partial rigorous reduction plus penalty evidence**, not `PROOF_COMPLETE`, `PRIZE_EARNED`, `RECEIVABLE`, or cash.

## Analytic continuation: pressure-free curved-hole lower bound

[pressure_trace_curved_lower_bound.md](pressure_trace_curved_lower_bound.md) adds a new analytic result over the retained formulation and prior pressure-trace witness. For a strongly constrained outer square, a regularly inscribed circular hole, the full weak-boundary velocity space with fixed degree k>=8, and fixed penalty, any solution of the explicitly pressure-free kernel equation has velocity-gradient error at least c h for the smooth no-flow datum u=0, p=x. Thus that particular method cannot have the proposed h^(3/2)+h_Omega^k rate when h_Omega^k=o(h).

The proof gives the uniform forcing and radial trace bounds explicitly; it performs no PDE run or accepted-certificate replay. It does not apply automatically to the constant-pressure manufactured problem, lower degrees, a growing penalty, or a stress-consistent/multiplier-repaired method. The full sponsor problem, corrected-method convergence and publication/prize conditions remain open.

## HCT continuation: degrees k>=2 on an explicit macro family

[pressure_trace_hct_extension.md](pressure_trace_hct_extension.md) extends the preceding conditional lower bound to every fixed k>=2 on uniformly shape-regular three-triangle barycentric/Clough–Tocher macro refinements. A full cubic HCT interpolant of the same smooth clamped streamfunction has a continuous piecewise-quadratic curl in the actual velocity kernel, with exact outer zero trace. A uniform scaling/Taylor argument preserves the nonzero forcing; the prior radial trace bound and inverse trace control the new test's boundary derivative.

The result remains conditional on a solution of the same pressure-free equation with fixed penalty. The rate contradiction additionally requires h_Omega^k=o(h_Gamma), for example globally comparable scales. It is not an all-mesh, mixed-solvability, corrected-method, computational-study or prize-acceptance result. The classical HCT element and unisolvence sources are credited explicitly; no earlier certificate is replayed.
