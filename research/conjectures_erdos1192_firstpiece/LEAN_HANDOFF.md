# Lean handoff for Erdős 1192

Exact target captured from the sponsor page:

```lean
import FormalConjectures.ErdosProblems.«1192»
import TaskSupport

namespace Bounty

theorem target : fcTypeOfName% "Erdos1192.erdos_1192" := by
  sorry

end Bounty
```

Task id: `fc-8432eac9-erdos1192-erdos-1192-abb86bc29e-formalized-v1`  
Commitment: `sha256:547f9ccecbebe2ce47b3e937020f6e36536a8c24ede2201b1c051a689d0c90cd`  
Source-type hash: `sha256:deb84e4a73cad6e9d9b6f934a99d436ba2a0ba545694e0d16cca0f266636f5a8`

## Proposed first-piece lemmas

The useful formal target is a source-level version of the finite energy bound. A Lean-enabled executor should prefer small lemmas that do not bake in Python-specific enumeration.

1. For a finite `B : Finset ℕ`, show that the sum of its ordered `r`-representation counts over all possible sums equals `B.card ^ r`.
2. Bound the support of those counts by `Finset.range (r * m + 1)` when every `b ∈ B` satisfies `b ≤ m`.
3. Apply finite Cauchy-Schwarz to obtain

```text
(B.card ^ (2*r) : ℕ) ≤ (r*m + 1) * ∑ n in range (r*m+1), count_B(r,n)^2.
```

4. Transfer `count_B(r,n) ≤ Erdos1192.f_r A r n` for `B = A ∩ [0,m]`.
5. Package the resulting lower bound as a reusable lemma about `Erdos1192.f_r`.

A later asymptotic lemma can combine that lower bound with the target's `=O[atTop]` hypothesis to deduce the necessary upper-density bound `|A ∩ [0,m]| = O(m^(1/r))` (phrased in a Mathlib-friendly power form if real roots are awkward).

## Base-case reduction

The imported source already exposes the solved theorem `Erdos1192.erdos_1192.variants.ruzsa` for `r=2`. A separate logical reduction can record that proving the target for every `r ≥ 3` is sufficient for the full `r ≥ 2` statement, using Ruzsa only for the `r=2` branch. This is useful plumbing but should not be the only submitted content; the finite energy lemma above is the substantive first-piece target.

## Verification requirement

This file is a handoff, not an executed Lean artifact. Do not promote it to a sponsor contribution until the exact source-pinned environment elaborates the lemmas and the current `contrib check`/submission policy accepts the package.
