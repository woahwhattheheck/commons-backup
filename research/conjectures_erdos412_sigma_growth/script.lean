import FormalConjectures.ErdosProblems.«412»
import Mathlib.NumberTheory.ArithmeticFunction.Misc

namespace Contribution.Erdos412SigmaGrowth

open Finset Nat
open scoped ArithmeticFunction.sigma

/-- For every input in the range of Erdős 412, one application of the
sum-of-divisors map strictly increases the value. -/
theorem sigma_one_gt_self {n : ℕ} (hn : 2 ≤ n) :
    n < ArithmeticFunction.sigma 1 n := by
  have hn0 : n ≠ 0 := by omega
  have hsub : ({1, n} : Finset ℕ) ⊆ n.divisors := by
    intro x hx
    simp only [mem_insert, mem_singleton] at hx
    rcases hx with rfl | rfl
    · exact one_mem_divisors.mpr hn0
    · exact n.mem_divisors_self hn0
  rw [ArithmeticFunction.sigma_one_apply]
  have hle :
      ∑ x ∈ ({1, n} : Finset ℕ), x ≤ ∑ x ∈ n.divisors, x := by
    exact sum_le_sum_of_subset_of_nonneg hsub (by
      intro i hi hi'
      exact Nat.zero_le i)
  have hne : n ≠ 1 := by omega
  have hsmall : n < ∑ x ∈ ({1, n} : Finset ℕ), x := by
    simp [hne]
  exact hsmall.trans_le hle

end Contribution.Erdos412SigmaGrowth
