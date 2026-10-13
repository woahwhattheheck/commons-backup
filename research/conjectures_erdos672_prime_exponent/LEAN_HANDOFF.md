# Lean handoff — Erdős 672 prime-exponent reduction

Target source is the sponsor-pinned `DIRECT_PROP` task, not current upstream main. Build against task `fc-8432eac9-erdos672-erdos-672-713e8186eb-formalized-v1` / source type SHA `c445617c…`.

The first lemma should isolate the elementary exponent factorization:

```lean
import FormalConjectures.ErdosProblems.«672»

namespace Contribution.Erdos672PrimeExponent

lemma reduce_pow_exponent_to_prime {q l : ℕ} (hl : 1 < l) :
    ∃ p m : ℕ, p.Prime ∧ 0 < m ∧ l = p * m ∧ q ^ l = (q ^ m) ^ p := by
  obtain ⟨p, hp, hpd⟩ := Nat.exists_prime_and_dvd (by omega : l ≠ 1)
  obtain ⟨m, hm⟩ := hpd
  refine ⟨p, m, hp, ?_, hm, ?_⟩
  · omega
  · rw [hm, mul_comm, pow_mul]

end Contribution.Erdos672PrimeExponent
```

This candidate is **unexecuted** in the present runtime. `Nat.exists_prime_and_dvd` is known to be used by current Formal Conjectures sources with a proof of `n ≠ 1`; the final `pow_mul` orientation still needs exact pinned-environment elaboration.

The useful follow-on theorem is the logical reduction:

```text
(∀ p, p.Prime → Erdos672With k p)
  → ∀ l, 1 < l → Erdos672With k l.
```

Proof plan: unfold `Erdos672With`; assume a forbidden equality `∏ i∈s, i = q^l`; obtain prime `p|l` and `l=p*m`; rewrite the same product as `(q^m)^p`; contradict the prime-exponent hypothesis for `p`. This composes directly with the task's outer `∀ k l` quantifiers.

Before sponsor contribution or solve submission:

1. bootstrap the sponsor-derived source commit exactly (do not substitute public upstream main);
2. elaborate a self-contained contribution file against the pinned environment;
3. run the sponsor's current contribution/check path and retain the exact receipt;
4. submit only if the kernel/checker passes.
