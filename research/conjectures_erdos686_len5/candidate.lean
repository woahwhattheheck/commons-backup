import FormalConjectures.ErdosProblems.«686»

/-!
# Erdős 686/four: the k=5 centered-quintic reduction

UNEXECUTED HANDOFF: this file was prepared in a runtime without `lean`/`lake`.
It must be elaborated against the sponsor-pinned environment before promotion
as a Conjectures.io contribution.
-/

namespace Contribution.Erdos686LenFive

/-- Five consecutive factors become an odd centered quintic. -/
theorem five_window_centered (x : ℤ) :
    (x + 1) * (x + 2) * (x + 3) * (x + 4) * (x + 5)
      = (x + 3)^5 - 5 * (x + 3)^3 + 4 * (x + 3) := by
  ring

/-- The k=5 product identity is equivalent to the centered quintic equation. -/
theorem len_five_iff_quintic (n m : ℕ) :
    (m + 1) * ((m + 2) * ((m + 3) * ((m + 4) * (m + 5))))
        = 4 * ((n + 1) * ((n + 2) * ((n + 3) * ((n + 4) * (n + 5))))) ↔
      ((m : ℤ) + 3)^5 - 5 * ((m : ℤ) + 3)^3 + 4 * ((m : ℤ) + 3)
        = 4 * (((n : ℤ) + 3)^5 - 5 * ((n : ℤ) + 3)^3 + 4 * ((n : ℤ) + 3)) := by
  constructor
  · intro h
    have hz :
        ((m : ℤ) + 1) * (((m : ℤ) + 2) * (((m : ℤ) + 3) *
          (((m : ℤ) + 4) * ((m : ℤ) + 5))))
          = 4 * (((n : ℤ) + 1) * (((n : ℤ) + 2) * (((n : ℤ) + 3) *
            (((n : ℤ) + 4) * ((n : ℤ) + 5))))) := by
      exact_mod_cast h
    linear_combination hz
  · intro h
    have hz :
        ((m : ℤ) + 1) * (((m : ℤ) + 2) * (((m : ℤ) + 3) *
          (((m : ℤ) + 4) * ((m : ℤ) + 5))))
          = 4 * (((n : ℤ) + 1) * (((n : ℤ) + 2) * (((n : ℤ) + 3) *
            (((n : ℤ) + 4) * ((n : ℤ) + 5))))) := by
      linear_combination h
    exact_mod_cast hz

end Contribution.Erdos686LenFive
